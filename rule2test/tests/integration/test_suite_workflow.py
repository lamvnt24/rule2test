"""A plain test-case file plus typed rule sentences become reviewed, executed, evidenced tests.

This is the flow the workspace guides a person through: import the file on its own, enter the
current and new rule as sentences, link the two, review the keep / change / add proposals,
execute and produce evidence. No rule identifiers ever appear in the file.
"""
import base64,json,tempfile,threading,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from factory.api.dependencies import Application
from factory.models import content_hash,WorkflowStatus,ApprovalDecision,ExecutionStatus
from factory.models.extraction import SourceText,ExtractionRequest
from factory.parsers.testcase_samples import sample_file,csv_bytes,RULE_SENTENCES
from factory.providers.llm.patterns import PatternRuleProvider
from factory.providers.sut.mock import MockSUTAdapter
from factory.engines.insurance_engine import InsuranceEngine
from factory.repositories.connection import Database
from factory.services.approval_service import ApprovalService
from factory.services.change_proposal_service import build,suggest_sut
from factory.services.evidence_service import EvidenceService
from factory.services.extraction_service import ExtractionService
from factory.services.knowledge_service import KnowledgeService
from factory.services.link_service import LinkService
from factory.services.suite_service import SuiteService,summary
from factory.services.workflow_service import WorkflowService
from factory.server import WorkspaceServer
from factory.exceptions import ConflictError,ValidationError

def proposal_for(db,current,new,provider=None):
    sources=([SourceText(document_id="current-rule.txt",label="v1",text=current)] if current else [])+[SourceText(document_id="new-rule.txt",label="v2",text=new)]
    return ExtractionService(db,provider or PatternRuleProvider()).propose(ExtractionRequest(sources=tuple(sources)),actor="BA")

class SuiteServiceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="rule2test-suite-");self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/"suite.db";self.db=Database(self.path);self.suites=SuiteService(self.db)
        self.name,self.data=sample_file("eligibility")
        self.sheet=self.suites.inspect(self.data,self.name)["sheets"][0]
    def create(self,resolutions=()):
        return self.suites.create(self.data,self.name,self.sheet["name"],self.sheet["suggested"],actor="QA",resolutions=list(resolutions),header_row=self.sheet["header_row"])
    def test_preview_flags_the_unclear_row_without_persisting(self):
        rows,columns=self.suites.preview(self.data,self.name,self.sheet["name"],self.sheet["suggested"])
        self.assertEqual([r.status for r in rows],["ready"]*4+["needs_confirmation"])
        self.assertEqual(rows[4].questions[0][:31],"Could not read a number after t")
        self.assertEqual(rows[1].cell("test_data").cell,"E3");self.assertEqual(self.suites.list(),[])
    def test_save_keeps_original_bytes_and_survives_restart(self):
        suite=self.create([dict(row_number=6,skip=True)])
        self.assertEqual(summary(suite)["skipped"],1);self.assertEqual(summary(suite)["ready"],4)
        reopened=SuiteService(Database(self.path))
        self.assertEqual(reopened.get(suite.suite_id),suite);self.assertEqual(reopened.source(suite.suite_id)[1],self.data)
        self.assertEqual([s.suite_id for s in reopened.list()],[suite.suite_id])
    def test_a_person_can_answer_the_question_or_correct_a_reading(self):
        suite=self.create([dict(row_number=6,inputs=[dict(field="age",value="70")],expected=dict(outcome="deny")),
                           dict(row_number=2,inputs=[dict(field="age",value="empty")],expected=dict(outcome="invalid"))])
        by_id={r.row_id:r for r in suite.rows}
        self.assertEqual((by_id["TC005"].status,by_id["TC005"].interpretation,by_id["TC005"].inputs[0].value.data),("ready","human",70))
        self.assertEqual(by_id["TC001"].inputs[0].value.kind.value,"null");self.assertIn("Confirmed by the reviewer",by_id["TC001"].notes[-1])
    def test_unresolved_rows_are_saved_as_unconfirmed_not_guessed(self):
        suite=self.create()
        self.assertEqual(suite.counts()["needs_confirmation"],1);self.assertEqual(suite.rows[4].inputs,())
    def test_bad_resolutions_are_rejected_before_anything_is_saved(self):
        for resolution in (dict(row_number=99,skip=True),dict(row_number=6,inputs=[dict(field="height",value="1")],expected=dict(outcome="allow")),
                           dict(row_number=6,inputs=[dict(field="age",value="abc")],expected=dict(outcome="allow")),
                           dict(row_number=6,inputs=[dict(field="claim_amount",value="10")],expected=dict(outcome="allow")),
                           dict(row_number=6,inputs=[dict(field="age",value="1")],expected=dict(outcome="payout"))):
            with self.subTest(resolution=resolution),self.assertRaises((ValueError,ValidationError)):self.create([resolution])
        self.assertEqual(self.suites.list(),[])
    def test_csv_is_first_class(self):
        data=csv_bytes("claim_review");sheet=self.suites.inspect(data,"cases.csv")["sheets"][0]
        suite=self.suites.create(data,"cases.csv",sheet["name"],sheet["suggested"],actor="QA")
        self.assertEqual(suite.document.media_type,"text/csv");self.assertEqual(suite.rows[0].inputs[0].field,"claim_amount")

class LinkTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="rule2test-link-");self.addCleanup(temp.cleanup)
        self.db=Database(Path(temp.name)/"link.db");self.suites=SuiteService(self.db);self.links=LinkService(self.db)
        self.workflow=WorkflowService(self.db);self.review=ApprovalService(self.db);self.extraction=ExtractionService(self.db)
    def suite(self,profile="eligibility",resolutions=()):
        name,data=sample_file(profile);sheet=self.suites.inspect(data,name)["sheets"][0]
        return self.suites.create(data,name,sheet["name"],sheet["suggested"],actor="QA",resolutions=list(resolutions))
    def approved(self,current,new):
        p=proposal_for(self.db,current,new)
        self.assertEqual(p.status,"pending_review",p.issues)
        self.extraction.review(p.proposal_id,content_hash(p),decision="approved",reviewer="BA",reason="Matches the policy memo")
        return p
    def rows(self,w,suite,link,baseline=True):
        return {r["test_id"]:r for r in build(w,link=link,suite=suite,baseline_known=baseline)["rows"]}
    def test_link_needs_confirmed_rules(self):
        suite=self.suite();p=proposal_for(self.db,*RULE_SENTENCES["eligibility"])
        with self.assertRaises(ConflictError):self.links.link(suite.suite_id,p.proposal_id,content_hash(p),actor="QA")
        with self.assertRaises(ConflictError):self.links.link(suite.suite_id,p.proposal_id,"0"*64,actor="QA")
        with self.db.read() as c:self.assertEqual(c.execute("SELECT count(*) FROM wf_heads").fetchone()[0],0)
    def test_the_example_from_the_specification(self):
        # TC001 age 60 keep; TC002 age 61 deny -> allow; add 65 and 66; the unreadable row is listed, not guessed.
        suite=self.suite();p=self.approved(*RULE_SENTENCES["eligibility"])
        w,link=self.links.link(suite.suite_id,p.proposal_id,content_hash(p),actor="QA")
        self.assertEqual(w.status,WorkflowStatus.IN_REVIEW);self.assertEqual(len(w.existing_tests),4);self.assertEqual(w.approvals,())
        self.assertEqual([e.row_id for e in link.excluded],["TC005"]);self.assertIn("Not confirmed at import",link.excluded[0].reason)
        proposal=build(w,link=link,suite=suite)
        self.assertEqual(proposal["changes"],["Age ≤ 60 became Age ≤ 65"]);self.assertTrue(proposal["baseline_known"])
        rows=self.rows(w,suite,link)
        self.assertEqual((rows["TC001"]["kind"],rows["TC001"]["before_text"],rows["TC001"]["after_text"]),("keep","ALLOW","ALLOW"))
        self.assertEqual((rows["TC002"]["kind"],rows["TC002"]["before_text"],rows["TC002"]["after_text"],rows["TC002"]["group"]),("change","DENY","ALLOW","affected"))
        self.assertIn("Age ≤ 60 became Age ≤ 65",rows["TC002"]["reason"]);self.assertEqual(rows["TC002"]["source"]["cell"],"E3")
        self.assertEqual(rows["TC002"]["original"][4]["text"],"Tuổi: 61");self.assertEqual(rows["TC002"]["rule"]["title"],"Age eligibility")
        added={r["inputs_text"]:r for r in rows.values() if r["kind"]=="add"}
        self.assertIn("exactly at the new limit",added["Age = 65"]["reason"]);self.assertEqual(added["Age = 65"]["after_text"],"ALLOW")
        self.assertIn("just above the new limit",added["Age = 66"]["reason"]);self.assertEqual(added["Age = 66"]["after_text"],"DENY")
        self.assertEqual(added["Age = 65"]["group"],"affected");self.assertEqual(added["Age = 19"]["group"],"boundary")
        self.assertEqual(added["Age = empty"]["group"],"robustness")
        self.assertEqual(proposal["excluded"][0]["row_id"],"TC005");self.assertEqual(proposal["summary"]["change"],1)
        self.assertEqual([r["kind"] for r in proposal["rows"]][:1],["change"],"affected rows come first")
        self.assertEqual(suggest_sut(w)["max_age"],65)
    def test_review_execute_and_evidence_carry_the_spreadsheet_cell(self):
        suite=self.suite();p=self.approved(*RULE_SENTENCES["eligibility"])
        w,_=self.links.link(suite.suite_id,p.proposal_id,content_hash(p),actor="QA")
        for test in w.tests:
            w=self.review.review(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,decision=ApprovalDecision.APPROVED,reviewer="QA",reason="Checked against the memo")
        w=self.review.finalize(w.workflow_id,w.revision,reviewer="QA",reason="All proposals inspected")
        from decimal import Decimal
        settings={k:v for k,v in suggest_sut(w).items() if k!="note"}
        # UI suggestions are JSON-safe strings; the engine constructor requires Decimal.
        for key in ('claim_threshold','deductible'):settings[key]=Decimal(settings[key])
        run=self.workflow.execute(w.workflow_id,w.revision,MockSUTAdapter(InsuranceEngine(**settings)),actor="QA")
        self.assertTrue(all(e.status is ExecutionStatus.PASS for e in run.executions))
        w=self.workflow.get(w.workflow_id);evidence=EvidenceService(self.db).create(w.workflow_id,w.revision,actor="QA")
        tc002=next(t for t in evidence.tests if t.test_id=="TC002")
        self.assertEqual((tc002.sources[0].sheet,tc002.sources[0].cell,tc002.sources[0].quote),("TestCases","E3","Tuổi: 61"))
        self.assertEqual(tc002.expected.outcome.value,"allow")
        archived=self.workflow.get(w.workflow_id).documents
        self.assertIn(suite.document.document_hash,{d.document_hash for d in archived})
    def test_rows_outside_the_rule_fields_are_kept_apart(self):
        suite=self.suite("claim_review",[dict(row_number=6,skip=True)]);p=self.approved(*RULE_SENTENCES["eligibility"])
        w,link=self.links.link(suite.suite_id,p.proposal_id,content_hash(p),actor="QA")
        self.assertEqual(w.existing_tests,());self.assertEqual(len(link.excluded),5)
        self.assertIn("these rules only decide on Age",link.excluded[0].reason)
    def test_new_rule_alone_checks_consistency_without_claiming_a_change(self):
        suite=self.suite("claim_review",[dict(row_number=6,skip=True)]);p=self.approved(None,RULE_SENTENCES["claim_review"][1])
        self.assertFalse(p.request.baseline_known)
        w,link=self.links.link(suite.suite_id,p.proposal_id,content_hash(p),actor="QA")
        proposal=build(w,link=link,suite=suite,baseline_known=False)
        self.assertFalse(proposal["baseline_known"]);self.assertEqual(proposal["changes"],[]);self.assertFalse(proposal["changed"])
        rows=self.rows(w,suite,link,baseline=False)
        self.assertEqual(rows["TC003"]["kind"],"change");self.assertIn("but the file expects REVIEW",rows["TC003"]["reason"])
        self.assertNotIn("new limit"," ".join(r["reason"] for r in rows.values()))
        self.assertEqual(rows["TC001"]["kind"],"keep")
    def test_deductible_suite_reads_payouts_and_the_mock_follows_the_rule(self):
        suite=self.suite("deductible",[dict(row_number=6,skip=True)]);p=self.approved(*RULE_SENTENCES["deductible"])
        w,link=self.links.link(suite.suite_id,p.proposal_id,content_hash(p),actor="QA")
        rows=self.rows(w,suite,link)
        self.assertEqual((rows["TC003"]["kind"],rows["TC003"]["before_text"],rows["TC003"]["after_text"]),("change","PAYOUT 15,000,000 VND","PAYOUT 10,000,000 VND"))
        self.assertIn("deductible 5,000,000 VND became 10,000,000 VND",rows["TC003"]["reason"])
        self.assertEqual(suggest_sut(w)["profile"],"deductible");self.assertEqual(suggest_sut(w)["deductible"],"10000000")
    def test_one_rule_proposal_can_serve_several_suites_and_feed_the_knowledge_corpus(self):
        p=self.approved(*RULE_SENTENCES["eligibility"])
        first,_=self.links.link(self.suite().suite_id,p.proposal_id,content_hash(p),actor="QA")
        second,_=self.links.link(self.suite().suite_id,p.proposal_id,content_hash(p),actor="QA")
        self.assertNotEqual(first.workflow_id,second.workflow_id)
        w=first
        for test in w.tests:
            w=self.review.review(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,decision=ApprovalDecision.APPROVED,reviewer="QA",reason="Checked")
        index=KnowledgeService(self.db).build((w.workflow_id,),actor="QA")
        self.assertIn("rule",{r.kind for r in index.records},"the link records the rule approval proof")
    def test_link_failure_leaves_nothing_behind(self):
        from unittest.mock import patch
        from factory.repositories.document_repository import DocumentRepository
        suite=self.suite();p=self.approved(*RULE_SENTENCES["eligibility"])
        with patch.object(DocumentRepository,"put",side_effect=RuntimeError("disk failure")):
            with self.assertRaises(RuntimeError):self.links.link(suite.suite_id,p.proposal_id,content_hash(p),actor="QA")
        with self.db.read() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM wf_heads").fetchone()[0],0)
            self.assertEqual(c.execute("SELECT count(*) FROM wf_objects WHERE kind='suite_link'").fetchone()[0],0)

class SuiteAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="rule2test-suite-api-");self.addCleanup(self.temp.cleanup)
        self.app=Application(Path(self.temp.name)/"workspace.db")
        self.server=WorkspaceServer(("127.0.0.1",0),self.app)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.base=f"http://127.0.0.1:{self.server.server_port}"
        self.token=self.get("/session")["csrf_token"]
    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
    def request(self,path,body=None,*,expected=200):
        head={"Content-Type":"application/json","X-CSRF-Token":getattr(self,"token","")} if body is not None else {}
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=head)
        try:response=urlopen(req,timeout=30)
        except HTTPError as exc:response=exc
        with response:payload=response.read();status=response.status;headers=response.headers
        self.assertEqual(status,expected,payload.decode(errors="replace"))
        return json.loads(payload) if "application/json" in headers.get("Content-Type","") else (payload,headers)
    def get(self,path,**kwargs):return self.request("/api/v1"+path,**kwargs)
    def post(self,path,body,**kwargs):return self.request("/api/v1"+path,body,**kwargs)
    def test_guided_flow_over_http(self):
        sample=self.get("/suites/samples/eligibility")
        upload=dict(filename=sample["filename"],content_base64=sample["content_base64"])
        info=self.post("/suites/inspect",upload);sheet=info["sheets"][0]
        self.assertEqual(sheet["suggested"]["expected"],"F")
        preview=self.post("/suites/preview",dict(upload,sheet=sheet["name"],mapping=sheet["suggested"],header_row=sheet["header_row"]))
        self.assertEqual(preview["summary"],dict(ready=4,needs_confirmation=1,skipped=0))
        self.assertEqual(self.get("/suites"),[])
        saved=self.post("/suites",dict(upload,sheet=sheet["name"],mapping=sheet["suggested"],actor="QA",resolutions=[dict(row_number=6,skip=True)]))
        suite_id=saved["summary"]["suite_id"]
        self.assertEqual(self.get("/suites/"+suite_id)["summary"]["skipped"],1)
        raw,_=self.get("/suites/"+suite_id+"/source");self.assertEqual(base64.b64encode(raw).decode(),sample["content_base64"])
        examples=self.get("/rules/examples")["examples"];example=next(e for e in examples if e["key"]=="eligibility")
        p=self.post("/extract",dict(sources=[dict(document_id="current-rule.txt",label="v1",text=example["current"]),dict(document_id="new-rule.txt",label="v2",text=example["new"])],actor="BA",engine="pattern"))
        self.assertEqual((p["status"],p["provider"],p["baseline_known"]),("pending_review","pattern",True))
        detail=self.get("/proposals/"+p["proposal_id"])
        self.assertEqual(detail["compiled"]["delta"]["deltas"][0]["kind"],"modified");self.assertEqual(len(detail["compiled"]["new_rules"]),1)
        self.post("/suites/"+suite_id+"/link",dict(proposal_id=p["proposal_id"],proposal_hash=p["proposal_hash"],actor="QA"),expected=409)
        self.post("/proposals/"+p["proposal_id"]+"/review",dict(proposal_hash=p["proposal_hash"],decision="approved",reason="Read both sentences",actor="BA"))
        self.assertEqual(self.get("/proposals")[0]["review"],"approved")
        linked=self.post("/suites/"+suite_id+"/link",dict(proposal_id=p["proposal_id"],proposal_hash=p["proposal_hash"],actor="QA"))
        w=linked["workflow"];self.assertEqual(w["status"],"in_review");self.assertEqual(w["suite_id"],suite_id)
        detail=self.get("/workflows/"+w["workflow_id"])
        self.assertEqual(detail["suite"]["suite_id"],suite_id);self.assertEqual(detail["sut_suggestion"]["max_age"],65)
        rows={r["test_id"]:r for r in detail["proposal"]["rows"]}
        self.assertEqual(rows["TC002"]["kind"],"change");self.assertEqual(detail["proposal"]["excluded"][0]["row_id"],"TC005")
        self.assertIn(sample["filename"],self.get("/workflows")[0]["title"])
        tests=detail["workflow"]["tests"]
        w=self.post("/workflows/"+w["workflow_id"]+"/review",dict(revision=w["revision"],actor="QA",tests=[dict(test_id=t["test_id"],revision=t["revision"]) for t in tests],decision="approved",reason="Proposals inspected"))
        w=self.post("/workflows/"+w["workflow_id"]+"/finalize",dict(revision=w["revision"],actor="QA",reason="Done"))
        sut={k:v for k,v in detail["sut_suggestion"].items() if k!="note"}
        result=self.post("/workflows/"+w["workflow_id"]+"/execute",dict(revision=w["revision"],actor="QA",sut=sut))
        self.assertTrue(all(e["status"]=="pass" for e in result["run"]["executions"]))
    def test_rejected_uploads_leave_no_suite(self):
        self.post("/suites/inspect",dict(filename="cases.txt",content_base64=base64.b64encode(b"x").decode()),expected=400)
        self.post("/suites/inspect",dict(filename="cases.csv",content_base64="%%%"),expected=400)
        csv=base64.b64encode(csv_bytes("eligibility")).decode()
        self.post("/suites",dict(filename="cases.csv",content_base64=csv,sheet="CSV",mapping={"expected":"Z"},actor="QA"),expected=400)
        self.post("/suites",dict(filename="cases.csv",content_base64=csv,sheet="CSV",mapping={"expected":"F","test_data":"E"},actor="QA",bogus=1),expected=400)
        self.assertEqual(self.get("/suites"),[]);self.get("/suites/missing",expected=404)



# Additional regression coverage for the independent-intake UI.
import tempfile,unittest
from pathlib import Path
from factory.models import content_hash
from factory.models.extraction import ExtractionRequest,SourceText
from factory.repositories.connection import Database
from factory.providers.llm.patterns import PatternRuleProvider
from factory.services.extraction_service import ExtractionService
from factory.services.suite_service import SuiteService
from factory.services.link_service import LinkService
from factory.services.change_proposal_service import build
from factory.parsers.testcase_samples import csv_bytes,RULE_SENTENCES
from factory.exceptions import ConflictError

class AdditionalSuiteWorkflowTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.db=Database(Path(temp.name)/'test.db')

    def link(self,baseline=True):
        service=SuiteService(self.db); data=csv_bytes('eligibility')
        sheet=service.inspect(data,'cases.csv')['sheets'][0]
        suite=service.create(data,'cases.csv','CSV',sheet['suggested'],actor='QA',resolutions=[dict(row_number=6,skip=True)])
        pair=RULE_SENTENCES['eligibility']
        sources=tuple(SourceText(document_id=label+'.txt',label=label,text=text) for label,text in zip(('v1','v2'),pair) if baseline or label=='v2')
        extraction=ExtractionService(self.db,PatternRuleProvider())
        proposal=extraction.propose(ExtractionRequest(sources=sources),actor='BA')
        self.assertEqual(proposal.status,'pending_review',proposal.issues)
        with self.assertRaises(ConflictError):LinkService(self.db).link(suite.suite_id,proposal.proposal_id,content_hash(proposal),actor='QA')
        extraction.review(proposal.proposal_id,content_hash(proposal),decision='approved',reviewer='QA',reason='Checked source')
        workflow,link=LinkService(self.db).link(suite.suite_id,proposal.proposal_id,content_hash(proposal),actor='QA')
        self.assertEqual(service.source(suite.suite_id)[1],data)
        return workflow,build(workflow,link=link,suite=suite,baseline_known=baseline)

    def test_change_explains_before_after_and_excludes_ambiguous_row(self):
        workflow,report=self.link()
        rows={r['test_id']:r for r in report['rows']}
        self.assertEqual(rows['TC001']['kind'],'keep')
        self.assertEqual((rows['TC002']['before_text'],rows['TC002']['after_text']),('DENY','ALLOW'))
        self.assertEqual(rows['TC002']['source']['cell'],'E3')
        self.assertEqual(report['excluded'][0]['row_id'],'TC005')
        self.assertFalse(workflow.approvals)
        self.assertTrue(any('Age = 66' in r['inputs_text'] for r in report['rows']))

    def test_new_rule_only_does_not_claim_historical_change(self):
        _,report=self.link(False)
        self.assertFalse(report['baseline_known']);self.assertFalse(report['changed'])
        self.assertFalse(report['changes'])
        row=next(r for r in report['rows'] if r['test_id']=='TC002')
        self.assertNotIn('The rule changed',row['reason'])
