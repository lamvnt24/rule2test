"""HTTP contract and persisted workflow integration tests for the local workspace."""
import base64,hashlib,json,tempfile,threading,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import MagicMock,patch
from factory.api.dependencies import Application
from factory.server import WorkspaceServer
from factory.parsers.templates import demo_payload,json_bytes
from scripts.run_retrieval_demo import reviewed_source,target_workflow

SUT=dict(profile="eligibility",fault="none",min_age=18,max_age=65,claim_threshold="150000000",deductible="10000000",currency="VND")

class WorkspaceAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="rule2test-api-")
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"workspace.db"
        self.app=Application(self.path)
        self.server=WorkspaceServer(("127.0.0.1",0),self.app)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.base=f"http://127.0.0.1:{self.server.server_port}"
        self.token=self.get("/session")["csrf_token"]
    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
    def request(self,path,body=None,*,headers=None,raw=None,expected=200):
        head={}
        if body is not None or raw is not None:
            head={"Content-Type":"application/json","X-CSRF-Token":getattr(self,"token","")}
        head.update(headers or {})
        data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        req=Request(self.base+path,data=data,headers=head)
        try:response=urlopen(req,timeout=30)
        except HTTPError as exc:response=exc
        with response:
            payload=response.read();status=response.status;response_headers=response.headers
        self.assertEqual(status,expected,payload.decode(errors="replace"))
        if "application/json" in response_headers.get("Content-Type",""):return json.loads(payload)
        return payload,response_headers
    def get(self,path,**kwargs):return self.request("/api/v1"+path,**kwargs)
    def post(self,path,body,**kwargs):return self.request("/api/v1"+path,body,**kwargs)
    def create(self):return self.post("/demo",dict(profile="eligibility",actor="QA"))
    def detail(self,w):return self.get("/workflows/"+w["workflow_id"])["workflow"]
    def command(self,w,action,**extra):
        return self.post("/workflows/"+w["workflow_id"]+"/"+action,dict(revision=w["revision"],actor="QA",**extra))
    def reviewed(self):
        w=self.command(self.create(),"analyze");w=self.command(w,"start-review")
        tests=self.detail(w)["tests"]
        w=self.command(w,"review",tests=[dict(test_id=t["test_id"],revision=t["revision"]) for t in tests],decision="approved",reason="Boundary and expected values inspected")
        return self.command(w,"finalize",reason="All current test decisions inspected")
    def test_complete_workflow_evidence_and_source_survive_restart(self):
        w=self.reviewed()
        result=self.command(w,"execute",sut=SUT);w=result["workflow"]
        self.assertTrue(all(e["status"]=="pass" for e in result["run"]["executions"]))
        result=self.command(w,"evidence");w=result["workflow"]
        e=self.get("/workflows/"+w["workflow_id"]+"/evidence/"+result["evidence_id"])
        self.assertEqual(w["status"],"evidenced")
        from factory.models import Evidence
        self.assertEqual(Evidence.from_dict(e).fingerprint,result["evidence_hash"])
        run=self.get("/workflows/"+w["workflow_id"]+"/runs/"+e["run_id"])
        self.assertEqual(run["coverage"]["mode"],"executed inputs")
        snapshot=self.detail(w);document=snapshot["documents"][0]
        archived=self.get("/workflows/"+w["workflow_id"]+"/sources/"+document["document_hash"])
        self.assertEqual(hashlib.sha256(json_bytes(demo_payload("eligibility"))).hexdigest(),document["document_hash"])
        self.assertEqual(archived,demo_payload("eligibility"))
        self.server.app=Application(self.path)
        self.assertEqual(self.detail(w),snapshot)
        self.assertTrue(self.get("/workflows/"+w["workflow_id"]+"/history"))
    def test_quality_gate_http_and_download_match_current_snapshot(self):
        w=self.reviewed()
        w=self.command(w,"execute",sut=SUT)["workflow"]
        w=self.command(w,"evidence")["workflow"]
        path="/workflows/"+w["workflow_id"]
        report=self.get(path+"/quality-gate")
        self.assertEqual(report["verdict"],"GO")
        self.assertEqual(report,self.get(path+"/quality-gate-report"))
        self.assertEqual(report["workflow_revision"],w["revision"])
        w=self.command(w,"reopen-review",reason="Gate must become stale")
        self.assertEqual(self.get(path+"/quality-gate")["verdict"],"NO-GO")

    def test_ai_status_is_metadata_only_and_does_not_create_workflows(self):
        with patch("factory.services.ai_readiness_service.inventory",return_value=dict(available=False,models=[])):
            status=self.get("/ai-status")
        self.assertFalse(status["readiness"]["live_ready"])
        self.assertEqual(status["readiness"]["status"],"mock_only")
        self.assertEqual(self.get("/workflows"),[])

    def test_stale_revision_and_unreviewed_execution_are_blocked(self):
        draft=self.create();w=self.command(draft,"analyze")
        path="/workflows/"+w["workflow_id"]
        self.post(path+"/analyze",dict(revision=draft["revision"],actor="QA"),expected=409)
        # Building the adapter is pure in-process construction; what must never happen for an
        # unreviewed workflow is a call out to the system under test.
        spy=MagicMock(wraps=self.app.adapter(SUT))
        with patch.object(self.app,"adapter",return_value=spy):
            self.post(path+"/execute",dict(revision=w["revision"],actor="QA",sut=SUT),expected=409)
        spy.execute.assert_not_called()
        self.assertEqual(self.detail(w)["status"],"analyzed")
    def test_bulk_review_rolls_back_if_any_test_revision_is_stale(self):
        w=self.command(self.command(self.create(),"analyze"),"start-review")
        tests=self.detail(w)["tests"]
        selected=[dict(test_id=t["test_id"],revision=t["revision"]) for t in tests]
        selected[-1]["revision"]+=1
        self.post("/workflows/"+w["workflow_id"]+"/review",dict(revision=w["revision"],actor="QA",tests=selected,decision="approved",reason="Explicit review"),expected=409)
        self.assertEqual(self.detail(w)["approvals"],[])
        self.assertEqual(self.detail(w)["revision"],w["revision"])
    def test_fault_produces_business_failure_not_fabricated_pass(self):
        w=self.reviewed()
        result=self.command(w,"execute",sut={**SUT,"fault":"boundary"})
        self.assertIn("fail",[e["status"] for e in result["run"]["executions"]])
        self.assertNotIn("error",[e["status"] for e in result["run"]["executions"]])
    def test_client_cannot_send_expected_to_execution(self):
        w=self.create()
        self.post("/workflows/"+w["workflow_id"]+"/execute",dict(revision=w["revision"],actor="QA",sut=SUT,expected="ALLOW"),expected=400)
    def test_csrf_origin_host_and_content_type_guards(self):
        body=dict(profile="eligibility",actor="QA")
        self.post("/demo",body,headers={"X-CSRF-Token":""},expected=403)
        self.post("/demo",body,headers={"Origin":"https://attacker.example"},expected=403)
        self.get("/session",headers={"Host":"attacker.example"},expected=403)
        self.post("/demo",body,headers={"Content-Type":"text/plain"},expected=415)
        self.assertEqual(self.get("/workflows"),[])
    def test_strict_json_and_bad_import_leave_no_workflows(self):
        self.request("/api/v1/demo",raw=b'{"profile":"eligibility","profile":"deductible","actor":"QA"}',expected=400)
        self.post("/import",dict(filename="rules.json",content_base64="%%%invalid",actor="QA"),expected=400)
        self.post("/import",dict(filename="../rules.json",content_base64="e30=",actor="QA"),expected=400)
        self.post("/import",dict(filename="rules.json",content_base64="e30=",actor="QA"),expected=400)
        self.assertEqual(self.get("/workflows"),[])
    def test_structured_import_archives_identical_bytes(self):
        raw=json_bytes(demo_payload("deductible"))
        w=self.post("/import",dict(filename="rules.json",content_base64=base64.b64encode(raw).decode(),actor="QA"))
        self.assertEqual(self.detail(w)["documents"][0]["document_hash"],hashlib.sha256(raw).hexdigest())
    def test_extraction_review_and_promotion_are_separate(self):
        sample=self.get("/samples/eligibility")
        body=dict(sources=[dict(document_id="v1.txt",label="v1",text=sample["v1"]),dict(document_id="v2.txt",label="v2",text=sample["v2"])],existing_tests_json=json.dumps(sample["existing_tests"]),actor="QA")
        p=self.post("/extract",body);path="/proposals/"+p["proposal_id"]
        self.assertEqual(p["status"],"pending_review")
        self.post(path+"/promote",dict(proposal_hash=p["proposal_hash"],actor="QA"),expected=409)
        self.post(path+"/review",dict(proposal_hash=p["proposal_hash"],decision="approved",reason="Source lines and decision table checked",actor="QA"))
        w=self.post(path+"/promote",dict(proposal_hash=p["proposal_hash"],actor="QA"))
        self.assertEqual(w["status"],"draft")
        self.assertEqual(len(self.get("/proposals")),1)
        self.assertEqual(self.get(path)["review"]["decision"],"approved")
    def test_retrieval_api_keeps_attached_candidates_pending(self):
        source=reviewed_source(self.app.db,"eligibility");target=target_workflow(self.app.db,source)
        index=self.post("/indexes",dict(workflow_ids=[source.workflow_id],actor="QA"))
        self.assertTrue(self.post("/search",dict(index_id=index["index_id"],query="age"))["hits"])
        b=self.post("/suggestions",dict(workflow_id=target.workflow_id,revision=target.revision,index_id=index["index_id"],query="age",actor="QA"))
        self.assertGreater(b["candidates"],0)
        detail=self.get("/batches/"+b["batch_id"])
        self.assertEqual(detail["batch_hash"],b["batch_hash"])
        w=self.post("/batches/"+b["batch_id"]+"/attach",dict(batch_hash=b["batch_hash"],actor="QA"))
        self.assertEqual(w["status"],"in_review");self.assertEqual(self.detail(w)["approvals"],[])
        self.assertEqual(len(self.get("/indexes")),1);self.assertEqual(len(self.get("/batches")),1)
    def test_static_assets_legacy_and_unknown_paths(self):
        html,headers=self.request("/")
        self.assertIn(b"Evidence workspace",html)
        self.assertNotIn("unsafe-inline",headers["Content-Security-Policy"])
        js,_=self.request("/workspace.js");self.assertIn(b"use strict",js)
        legacy,headers=self.request("/legacy")
        self.assertIn("unsafe-inline",headers["Content-Security-Policy"])
        self.assertTrue(legacy);self.request("/api/demo")
        self.request("/../pyproject.toml",expected=404)
        self.get("/workflows/missing",expected=404)
    def test_edit_invalidates_approval_and_mutation_is_read_only(self):
        w=self.reviewed();t=self.detail(w)["tests"][0]
        w=self.command(w,"reopen-review",reason="Inspect new input")
        w=self.command(w,"edit-test",test_id=t["test_id"],test_revision=t["revision"],inputs=t["inputs"],expected=t["expected"],title=t["title"]+" reviewed",reason="Clarify title")
        self.assertEqual(self.detail(w)["approvals"],[])
        before=self.detail(w)
        report=self.get("/workflows/"+w["workflow_id"]+"/mutation")
        self.assertIn("score",report);self.assertEqual(before,self.detail(w))

if __name__=="__main__":unittest.main()


