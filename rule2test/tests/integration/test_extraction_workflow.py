import json,tempfile,unittest,io
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
from contextlib import redirect_stdout,redirect_stderr
from factory.models import content_hash,WorkflowStatus,ApprovalDecision,ExecutionStatus
from factory.repositories.connection import Database
from factory.repositories.document_repository import DocumentRepository
from factory.services.extraction_service import ExtractionService
from factory.services.workflow_service import WorkflowService
from factory.services.import_service import ImportService
from factory.services.approval_service import ApprovalService
from factory.services.evidence_service import EvidenceService
from factory.providers.llm.mock import MockLLMProvider
from factory.providers.sut.mock import MockSUTAdapter
from factory.engines.insurance_engine import InsuranceEngine
from factory.validators.extraction_validator import compile_proposal
from factory.exceptions import ConflictError,ValidationError
from tests.unit.test_extraction import request,response

class ExtractionWorkflowTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="rule2test-extraction-");self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.path=self.root/"test.db";self.db=Database(self.path)
        self.service=ExtractionService(self.db,MockLLMProvider())
    def proposed(self):return self.service.propose(request(),actor="BA")
    def approved(self):
        p=self.proposed()
        self.service.review(p.proposal_id,content_hash(p),decision="approved",reviewer="SME",reason="Checked each source line and interpretation")
        return p
    def test_proposal_survives_restart_and_never_creates_workflow(self):
        p=self.proposed()
        self.assertEqual(p.status,"pending_review");self.assertTrue(p.simulated)
        self.assertEqual(ExtractionService(Database(self.path)).get(p.proposal_id),p)
        with self.db.read() as c:self.assertEqual(c.execute("SELECT count(*) FROM wf_heads").fetchone()[0],0)
        with self.assertRaises(ConflictError):self.service.promote(p.proposal_id,content_hash(p),actor="BA")
    def test_review_requires_exact_hash_and_is_immutable(self):
        p=self.proposed()
        with self.assertRaises(ConflictError):self.service.review(p.proposal_id,"0"*64,decision="approved",reviewer="SME",reason="stale")
        r=self.service.review(p.proposal_id,content_hash(p),decision="rejected",reviewer="SME",reason="Incorrect interpretation")
        self.assertEqual(self.service.review(p.proposal_id,content_hash(p),decision="rejected",reviewer="SME",reason="Incorrect interpretation"),r)
        with self.assertRaises(ConflictError):self.service.review(p.proposal_id,content_hash(p),decision="approved",reviewer="SME",reason="Changed my mind")
        with self.assertRaises(ConflictError):self.service.promote(p.proposal_id,content_hash(p),actor="BA")
    def test_promote_is_atomic_idempotent_and_archives_originals(self):
        p=self.approved();w=self.service.promote(p.proposal_id,content_hash(p),actor="BA")
        self.assertEqual(w.status,WorkflowStatus.DRAFT);self.assertEqual(w.approvals,())
        self.assertEqual(self.service.promote(p.proposal_id,content_hash(p),actor="BA"),w)
        imports=ImportService(WorkflowService(self.db))
        for source in p.request.sources:
            _,data=imports.source(w.workflow_id,source.document_hash)
            self.assertEqual(data,source.text.encode())
        self.assertEqual(len(w.documents),5)
        self.assertEqual(w.new_rules[0].sources[0].line_start,2)
        self.assertEqual(w.new_rules[0].sources[1].line_start,3)
        with self.db.read() as c:self.assertEqual(c.execute("SELECT count(*) FROM wf_heads").fetchone()[0],1)
    def test_archive_failure_rolls_back_promotion_and_can_retry(self):
        p=self.approved()
        with patch.object(DocumentRepository,"put",side_effect=RuntimeError("disk failure")):
            with self.assertRaises(RuntimeError):self.service.promote(p.proposal_id,content_hash(p),actor="BA")
        with self.db.read() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM wf_heads").fetchone()[0],0)
            self.assertEqual(c.execute("SELECT count(*) FROM wf_objects WHERE kind='extraction_promotion'").fetchone()[0],0)
        self.assertEqual(self.service.promote(p.proposal_id,content_hash(p),actor="BA").status,WorkflowStatus.DRAFT)
    def test_tampered_proposal_hash_is_detected(self):
        p=self.proposed()
        with self.db.transaction() as c:c.execute("UPDATE wf_objects SET hash=? WHERE kind='extraction_proposal'",("0"*64,))
        with self.assertRaises(ValidationError):self.service.get(p.proposal_id)
    def test_provider_failure_and_invalid_output_persist_without_approval(self):
        class BadProvider(MockLLMProvider):
            def extract(self,*args,**kwargs):raise TimeoutError("secret-key")
        p=ExtractionService(self.db,BadProvider()).propose(request(),actor="BA")
        self.assertEqual(p.status,"provider_error");self.assertNotIn("secret-key",p.to_json())
        for bad in ("invalid",'{"approved":true}',"x"*262145):
            class BadOutput(MockLLMProvider):
                def extract(self,*args,**kwargs):return bad
            p=ExtractionService(self.db,BadOutput()).propose(request(),actor="BA")
            self.assertEqual(p.status,"invalid_output")
            with self.assertRaises(ConflictError):self.service.review(p.proposal_id,content_hash(p),decision="approved",reviewer="QA",reason="invalid")
    def test_invalid_business_rule_is_blocked_after_citation_validation(self):
        class BadDomain(MockLLMProvider):
            def extract(self,req,**kwargs):
                data=response(req);data["rules_v2"][1]["value"]=999
                return json.dumps(data)
        p=ExtractionService(self.db,BadDomain()).propose(request(),actor="BA")
        self.assertEqual(p.status,"invalid_output");self.assertIn("Domain validation",p.issues[0])
    def test_valid_quote_does_not_prove_semantics_or_autoapprove(self):
        class WrongOperator(MockLLMProvider):
            def extract(self,req,**kwargs):
                data=response(req);data["rules_v2"][1]["operator"]="lt"
                return json.dumps(data)
        p=ExtractionService(self.db,WrongOperator()).propose(request(),actor="BA")
        self.assertEqual(p.status,"pending_review")  # SME must detect the incorrect interpretation.
        with self.assertRaises(ConflictError):self.service.promote(p.proposal_id,content_hash(p),actor="BA")
    def test_clarification_cannot_be_approved(self):
        req=request();req=replace(req,sources=(req.sources[0],replace(req.sources[1],text="Conditions are not decided")))
        p=self.service.propose(req,actor="BA")
        self.assertEqual(p.status,"needs_clarification")
        with self.assertRaises(ConflictError):self.service.review(p.proposal_id,content_hash(p),decision="approved",reviewer="SME",reason="guess")
    def test_existing_tests_preserved_and_not_overridden_by_model(self):
        from factory.parsers.templates import demo_payload
        original=demo_payload()["tests"];req=request(tests=json.dumps(original))
        p=self.service.propose(req,actor="BA");bundle,_=compile_proposal(p)
        self.assertEqual(len(bundle.existing_tests),3)
        self.assertEqual(bundle.existing_tests[-1].expected.outcome.value,"deny")
        self.assertEqual(bundle.existing_tests[-1].rules[0].rule_hash,content_hash(bundle.old_rules[0]))
    def test_full_review_execution_evidence_retains_japanese_source(self):
        p=self.approved();w=self.service.promote(p.proposal_id,content_hash(p),actor="BA")
        workflow=WorkflowService(self.db);qa=ApprovalService(self.db)
        w=workflow.analyze(w.workflow_id,w.revision,actor="BA")
        w=workflow.start_review(w.workflow_id,w.revision,actor="QA")
        self.assertFalse(w.approvals)
        for test in w.tests:
            w=qa.review(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,
                decision=ApprovalDecision.APPROVED,reviewer="Synthetic QA test",reason="Unit fixture review")
        w=qa.finalize(w.workflow_id,w.revision,reviewer="Synthetic QA test",reason="Fixture only")
        run=workflow.execute(w.workflow_id,w.revision,MockSUTAdapter(InsuranceEngine(profile="eligibility")),actor="QA")
        self.assertTrue(all(e.status is ExecutionStatus.PASS for e in run.executions))
        w=workflow.get(w.workflow_id);e=EvidenceService(self.db).create(w.workflow_id,w.revision,actor="QA")
        self.assertTrue(any(s.line_start==2 and "加入年齢" in s.quote for r in e.rules for s in r.sources))
    def test_cli_review_and_promotion(self):
        from scripts.seed_ai_samples import seed
        from scripts.extraction_cli import main
        folder=self.root/"samples";seed(folder);sample=folder/"eligibility"
        def call(args):
            out=io.StringIO();err=io.StringIO()
            with redirect_stdout(out),redirect_stderr(err),patch.dict("os.environ",{"RULE2TEST_EXTRACTION_PROVIDER":"mock"}):
                code=main(["--db",str(self.path)]+args)
            self.assertEqual(code,0,err.getvalue());return json.loads(out.getvalue())
        p=call(["extract","--v1",str(sample/"rules_v1.txt"),"--v2",str(sample/"rules_v2.txt"),"--actor","BA"])
        shown=call(["show","--proposal",p["proposal_id"],"--full"])
        self.assertIsNone(shown["review"]);self.assertTrue(shown["output"]["citations"])
        call(["review","--proposal",p["proposal_id"],"--hash",p["proposal_hash"],"--actor","SME","--decision","approved","--reason","Fixture check"])
        w=call(["promote","--proposal",p["proposal_id"],"--hash",p["proposal_hash"],"--actor","BA"])
        self.assertEqual(w["status"],"draft")
    def test_replay_evaluation_is_labeled_simulated(self):
        from scripts.seed_ai_samples import seed
        from scripts.evaluate_extraction import evaluate
        folder=self.root/"samples";seed(folder)
        report=evaluate(self.service,folder)
        self.assertEqual(report["matched"],4);self.assertEqual(report["total"],4)
        self.assertEqual(report["metric"],"mock_fixture_replay_checks");self.assertTrue(report["simulated"])
