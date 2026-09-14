import tempfile,threading,unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import Mock
from factory.models import *
from factory.models.workflow import Workflow
from factory.repositories.connection import Database
from factory.repositories.test_repository import TestRepository
from factory.repositories.rule_repository import RuleRepository
from factory.repositories.approval_repository import ApprovalRepository
from factory.services.workflow_service import WorkflowService
from factory.services.approval_service import ApprovalService
from factory.services.evidence_service import EvidenceService
from factory.providers.sut.mock import MockSUTAdapter
from factory.engines.insurance_engine import InsuranceEngine
from factory.exceptions import ConflictError,ValidationError
from tests.fixtures.engine_cases import scenario

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="rule2test-workflow-")
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"workflow.db"
        self.db=Database(self.path);self.service=WorkflowService(self.db)
        self.review=ApprovalService(self.db);self.evidence=EvidenceService(self.db)
        self.table,self.rules=scenario("eligibility")
    def create(self):
        return self.service.create(self.table,self.rules,self.table,self.rules,actor="BA")
    def reviewing(self):
        w=self.create()
        w=self.service.analyze(w.workflow_id,w.revision,actor="BA")
        return self.service.start_review(w.workflow_id,w.revision,actor="QA")
    def reviewed(self,reject_first=False):
        w=self.reviewing()
        for i,test in enumerate(w.tests):
            w=self.review.review(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,
                decision=ApprovalDecision.REJECTED if reject_first and i==0 else ApprovalDecision.APPROVED,
                reviewer="QA",reason="Reviewed synthetic test")
        return self.review.finalize(w.workflow_id,w.revision,reviewer="QA",reason="Review complete")
    def adapter(self):return MockSUTAdapter(InsuranceEngine(profile="eligibility"))
    def test_migrations_repeat_and_legacy_table_is_preserved(self):
        with self.db.transaction() as c:
            c.execute("CREATE TABLE records(id TEXT PRIMARY KEY,payload TEXT)")
            c.execute("INSERT INTO records VALUES('old','legacy')")
        Database(self.path)
        with self.db.read() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM wf_schema_migrations").fetchone()[0],3)
            self.assertEqual(c.execute("SELECT payload FROM records").fetchone()[0],"legacy")
    def test_restart_roundtrip_and_complete_evidence(self):
        w=self.reviewed()
        reopened=WorkflowService(Database(self.path))
        self.assertEqual(reopened.get(w.workflow_id),w)
        run=reopened.execute(w.workflow_id,w.revision,self.adapter(),actor="QA")
        self.assertEqual(run.status,"completed")
        self.assertTrue(all(e.status is ExecutionStatus.PASS for e in run.executions))
        current=reopened.get(w.workflow_id)
        evidence=EvidenceService(Database(self.path)).create(current.workflow_id,current.revision,actor="QA")
        self.assertEqual(Evidence.from_json(evidence.to_json()),evidence)
        saved=EvidenceService(Database(self.path)).get_evidence(w.workflow_id,evidence.evidence_id)
        self.assertEqual(saved.fingerprint,evidence.fingerprint)
        self.assertEqual(reopened.get(w.workflow_id).status,WorkflowStatus.EVIDENCED)
    def test_unreviewed_execution_is_blocked_before_adapter(self):
        w=self.reviewing();adapter=Mock()
        with self.assertRaises(ConflictError):self.service.execute(w.workflow_id,w.revision,adapter,actor="QA")
        adapter.execute.assert_not_called()
        with self.assertRaises(ConflictError):self.review.finalize(w.workflow_id,w.revision,reviewer="QA",reason="Pending")
    def test_rejected_tests_are_excluded(self):
        w=self.reviewed(reject_first=True)
        run=self.service.execute(w.workflow_id,w.revision,self.adapter(),actor="QA")
        rejected={a.subject_id for a in w.approvals if a.decision is ApprovalDecision.REJECTED}
        self.assertFalse(rejected&{e.test_id for e in run.executions})
        self.assertEqual(len(run.executions),len(w.tests)-1)
    def test_changes_requested_blocks_finalization(self):
        w=self.reviewing()
        for i,test in enumerate(w.tests):
            w=self.review.review(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,
                decision=ApprovalDecision.CHANGES_REQUESTED if i==0 else ApprovalDecision.APPROVED,reviewer="QA",reason="Check boundary")
        with self.assertRaises(ConflictError):self.review.finalize(w.workflow_id,w.revision,reviewer="QA",reason="Not ready")
    def test_all_rejected_cannot_run(self):
        w=self.reviewing()
        for test in w.tests:
            w=self.review.review(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,
                decision=ApprovalDecision.REJECTED,reviewer="QA",reason="Excluded")
        with self.assertRaises(ConflictError):self.review.finalize(w.workflow_id,w.revision,reviewer="QA",reason="No tests")
    def test_stale_client_and_test_revisions(self):
        w=self.reviewing();test=w.tests[0]
        updated=self.review.review(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,
            decision=ApprovalDecision.APPROVED,reviewer="QA",reason="Correct")
        with self.assertRaises(ConflictError):
            self.review.review(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,
                decision=ApprovalDecision.REJECTED,reviewer="Other QA",reason="Stale browser")
        with self.assertRaises(ConflictError):
            self.service.edit_test(updated.workflow_id,updated.revision,test_id=test.test_id,test_revision=999,
                inputs=test.inputs,expected=test.expected,actor="QA",reason="Stale test")
    def test_edit_revokes_approval_and_preserves_history(self):
        w=self.reviewed();test=w.tests[0]
        edited=self.service.edit_test(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,
            inputs=test.inputs,expected=test.expected,actor="QA",reason="Improve explanation")
        current=next(t for t in edited.tests if t.test_id==test.test_id)
        self.assertEqual(current.revision,test.revision+1)
        self.assertEqual(edited.status,WorkflowStatus.IN_REVIEW)
        self.assertFalse(any(a.subject_id==test.test_id for a in edited.approvals))
        with self.db.read() as c:
            self.assertEqual(TestRepository().get(c,w.workflow_id,test.test_id,test.revision),test)
            self.assertEqual(len(TestRepository().history(c,w.workflow_id,test.test_id)),2)
            self.assertTrue(ApprovalRepository().list_for_workflow(c,w.workflow_id))
        with self.assertRaises(ConflictError):self.review.finalize(edited.workflow_id,edited.revision,reviewer="QA",reason="Missing new approval")
    def test_rule_revision_invalidates_all_reviews(self):
        w=self.reviewed()
        new_rule=replace(self.rules[0],version=2,conditions=(self.rules[0].conditions[0],
            replace(self.rules[0].conditions[1],value=Value(kind=ValueKind.INTEGER,data=66))))
        new_ref=RuleReference(rule_id=new_rule.rule_id,version=2,rule_hash=content_hash(new_rule))
        table=replace(self.table,version=2,rows=(replace(self.table.rows[0],rule=new_ref,conditions=new_rule.conditions),))
        w=self.service.revise_rules(w.workflow_id,w.revision,table=table,rules=(new_rule,),actor="BA",reason="New maximum age")
        self.assertEqual(w.status,WorkflowStatus.DRAFT);self.assertEqual(w.approvals,())
        next_revision=self.service.analyze(w.workflow_id,w.revision,actor="BA")
        self.assertTrue(all(t.rules[0].version==2 for t in next_revision.tests))
        self.assertEqual(next_revision.approvals,())
    def test_wrong_expected_cannot_be_approved(self):
        w=self.reviewing();test=w.tests[0]
        bad=Action(outcome=Outcome.REVIEW if test.expected.outcome is not Outcome.REVIEW else Outcome.DENY)
        w=self.service.edit_test(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,
            inputs=test.inputs,expected=bad,actor="QA",reason="Incorrect expected")
        edited=next(t for t in w.tests if t.test_id==test.test_id)
        with self.assertRaises(ConflictError):self.review.review(w.workflow_id,w.revision,test_id=edited.test_id,
            test_revision=edited.revision,decision=ApprovalDecision.APPROVED,reviewer="QA",reason="Should fail")
    def test_immutable_snapshot_conflict_rolls_back(self):
        w=self.create();before=len(self.service.events(w.workflow_id))
        with self.assertRaises(ConflictError):
            with self.db.transaction() as c:
                c.execute("INSERT INTO wf_events(workflow_id,revision,actor,event,detail,created_at) VALUES(?,?,?,?,?,?)",
                    (w.workflow_id,1,"QA","rolled_back","Must roll back","2020-01-01"))
                RuleRepository().put(c,w.workflow_id,replace(self.rules[0],title="Changed without version"))
        self.assertEqual(len(self.service.events(w.workflow_id)),before)
    def test_duplicate_execution_and_edits_blocked_while_running(self):
        w=self.reviewed();entered=threading.Event();release=threading.Event();errors=[]
        delegate=self.adapter()
        class Blocking:
            name="blocking-test"
            def execute(self,inputs,*,timeout_seconds):
                entered.set()
                if not release.wait(5):raise TimeoutError()
                return delegate.execute(inputs,timeout_seconds=timeout_seconds)
        def worker():
            try:self.service.execute(w.workflow_id,w.revision,Blocking(),actor="QA")
            except Exception as exc:errors.append(exc)
        thread=threading.Thread(target=worker);thread.start()
        try:
            self.assertTrue(entered.wait(5))
            current=self.service.get(w.workflow_id);spy=Mock()
            with self.assertRaises(ConflictError):self.service.execute(current.workflow_id,current.revision,spy,actor="QA")
            with self.assertRaises(ConflictError):self.service.reopen_review(current.workflow_id,current.revision,actor="QA",reason="During run")
            spy.execute.assert_not_called()
        finally:release.set();thread.join(10)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
    def test_crash_journal_survives_restart_without_automatic_replay(self):
        w=self.reviewed();delegate=self.adapter()
        class Crash:
            name="crash-after-one"
            calls=0
            def execute(self,inputs,*,timeout_seconds):
                self.calls+=1
                if self.calls==2:raise KeyboardInterrupt()
                return delegate.execute(inputs,timeout_seconds=timeout_seconds)
        adapter=Crash()
        with self.assertRaises(KeyboardInterrupt):self.service.execute(w.workflow_id,w.revision,adapter,actor="QA")
        reopened=WorkflowService(Database(self.path));current=reopened.get(w.workflow_id)
        self.assertEqual(current.status,WorkflowStatus.EXECUTING)
        run=reopened.run(w.workflow_id,current.active_run_id)
        self.assertEqual(len(run.executions),1);self.assertEqual(adapter.calls,2)
        recovered=reopened.recover_interrupted_run(current.workflow_id,current.revision,actor="Operator",
            reason="Old process stopped; external effects reconciled")
        self.assertEqual(recovered.status,WorkflowStatus.IN_REVIEW);self.assertEqual(recovered.approvals,())
        self.assertEqual(reopened.run(w.workflow_id,run.run_id).status,"interrupted")
    def test_unexpected_adapter_error_is_durable_interruption(self):
        w=self.reviewed();adapter=Mock();adapter.name="broken";adapter.execute.side_effect=RuntimeError("secret-token")
        with self.assertRaises(RuntimeError):self.service.execute(w.workflow_id,w.revision,adapter,actor="QA")
        current=self.service.get(w.workflow_id)
        self.assertEqual(current.status,WorkflowStatus.INTERRUPTED)
        self.assertNotIn("secret-token",self.service.run(w.workflow_id,current.active_run_id).error)
    def test_evidence_not_allowed_before_completed_run_and_is_idempotent(self):
        w=self.reviewed()
        with self.assertRaises(ConflictError):self.evidence.create(w.workflow_id,w.revision,actor="QA")
        self.service.execute(w.workflow_id,w.revision,self.adapter(),actor="QA")
        w=self.service.get(w.workflow_id);e=self.evidence.create(w.workflow_id,w.revision,actor="QA")
        w=self.service.get(w.workflow_id)
        self.assertEqual(self.evidence.create(w.workflow_id,w.revision,actor="QA"),e)
        self.assertEqual(self.service.get(w.workflow_id).revision,w.revision)
    def test_old_evidence_survives_new_test_revision(self):
        w=self.reviewed();self.service.execute(w.workflow_id,w.revision,self.adapter(),actor="QA")
        w=self.service.get(w.workflow_id);e=self.evidence.create(w.workflow_id,w.revision,actor="QA")
        w=self.service.get(w.workflow_id);test=w.tests[0]
        edited=self.service.edit_test(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,
            inputs=test.inputs,expected=test.expected,actor="QA",reason="New revision")
        self.assertIsNone(edited.evidence_id)
        self.assertEqual(self.evidence.get_evidence(w.workflow_id,e.evidence_id).fingerprint,e.fingerprint)
    def test_tampered_workflow_hash_is_detected(self):
        w=self.create()
        with self.db.transaction() as c:
            c.execute("UPDATE wf_objects SET hash=? WHERE scope=? AND kind='workflow'",("0"*64,w.workflow_id))
        with self.assertRaises(ValidationError):self.service.get(w.workflow_id)
    def test_workflows_have_separate_snapshot_namespaces(self):
        one=self.reviewed();two=self.reviewing()
        self.assertNotEqual(one.workflow_id,two.workflow_id);self.assertEqual(two.approvals,())
        self.assertTrue(set(t.test_id for t in one.tests)&set(t.test_id for t in two.tests))
        with self.assertRaises(ConflictError):self.review.finalize(two.workflow_id,two.revision,reviewer="QA",reason="Cannot reuse another workflow approvals")

    def test_model_rejects_inconsistent_run_state(self):
        w=self.create()
        with self.assertRaises(ValidationError):replace(w,active_run_id="fake-run")
        with self.assertRaises(ValidationError):replace(w,status=WorkflowStatus.EXECUTED)

    def test_reopen_requires_new_reviews_and_keeps_previous_run(self):
        w=self.reviewed()
        run=self.service.execute(w.workflow_id,w.revision,self.adapter(),actor="QA")
        w=self.service.get(w.workflow_id)
        w=self.service.reopen_review(w.workflow_id,w.revision,actor="QA",reason="Explicit rerun requested")
        self.assertEqual(w.approvals,())
        self.assertEqual(self.service.run(w.workflow_id,run.run_id).status,"completed")
        with self.assertRaises(ConflictError):self.review.finalize(w.workflow_id,w.revision,reviewer="QA",reason="Must review again")

    def test_workflow_cli_explicit_review_and_stale_revision(self):
        import io,json
        from contextlib import redirect_stdout,redirect_stderr
        from scripts.workflow_cli import main
        def call(args,expected=0):
            output=io.StringIO();errors=io.StringIO()
            with redirect_stdout(output),redirect_stderr(errors):
                result=main(["--db",str(self.path)]+args)
            self.assertEqual(result,expected,errors.getvalue())
            return json.loads(output.getvalue()) if expected==0 else errors.getvalue()
        w=call(["create-demo","--actor","BA"])
        w=call(["analyze","--workflow",w["workflow_id"],"--revision",str(w["revision"]),"--actor","BA"])
        w=call(["start-review","--workflow",w["workflow_id"],"--revision",str(w["revision"]),"--actor","QA"])
        self.assertTrue(all(t["review"]=="pending" for t in w["tests"]))
        test=w["tests"][0]
        args=["review","--workflow",w["workflow_id"],"--revision",str(w["revision"]),"--actor","QA",
              "--test-id",test["test_id"],"--test-revision",str(test["revision"]),"--decision","approved","--reason","Checked"]
        updated=call(args)
        self.assertEqual(sum(t["review"]=="approved" for t in updated["tests"]),1)
        self.assertIn("Stale workflow revision",call(args,expected=2))
