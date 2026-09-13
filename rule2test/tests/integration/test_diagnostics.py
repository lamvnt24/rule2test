"""Phase 11 over HTTP: diagnostics payload, trace correlation, classified provider failures and no hidden retry."""
import json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from factory.api.dependencies import Application
from factory.observability import metrics
from factory.providers.failure import failure
from factory.repositories.connection import Database
from factory.services.extraction_service import ExtractionService
from factory.server import WorkspaceServer
from tests.unit.test_extraction import request as extraction_request

class CountingFailureProvider:
    """Records every call so a hidden retry cannot pass unnoticed."""
    name="counting-failure";model="synthetic";simulated=False
    def __init__(self,error):self.error=error;self.calls=0
    def extract(self,request,*,system_prompt,timeout_seconds):
        self.calls+=1;raise self.error

class DiagnosticsAPITests(unittest.TestCase):
    def setUp(self):
        metrics.reset();self.addCleanup(metrics.reset)
        self.temp=tempfile.TemporaryDirectory(prefix="rule2test-diagnostics-");self.addCleanup(self.temp.cleanup)
        self.app=Application(Path(self.temp.name)/"workspace.db")
        self.server=WorkspaceServer(("127.0.0.1",0),self.app)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.base=f"http://127.0.0.1:{self.server.server_port}"
        self.token=self.call("/api/v1/session")[2]["csrf_token"]
    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
    def call(self,path,body=None,*,expected=200):
        head={"Content-Type":"application/json","X-CSRF-Token":getattr(self,"token","")} if body is not None else {}
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=head)
        try:response=urlopen(req,timeout=30)
        except HTTPError as exc:response=exc
        with response:payload=response.read();status=response.status;headers=response.headers
        self.assertEqual(status,expected,payload.decode(errors="replace"))
        return status,headers,json.loads(payload)

    def test_every_response_carries_a_trace_identifier(self):
        _,headers,_=self.call("/api/v1/diagnostics")
        self.assertEqual(len(headers["X-Trace-Id"]),16)

    def test_error_bodies_reference_the_same_trace_identifier(self):
        _,headers,body=self.call("/api/v1/workflows/missing",expected=404)
        self.assertEqual(body["trace_id"],headers["X-Trace-Id"])

    def test_diagnostics_reports_configuration_metrics_and_limits(self):
        _,_,body=self.call("/api/v1/diagnostics")
        self.assertEqual(body["schema_version"],1)
        self.assertEqual(body["database"]["migrations"],[1,2])
        self.assertIn("counters",body["metrics"]);self.assertIn("durations",body["metrics"])
        self.assertLessEqual(body["metrics"]["series"],body["metrics"]["max_series"])
        self.assertIn("reset on restart",body["limitation"])

    def test_diagnostics_never_exposes_secret_values_or_the_session_token(self):
        self.call("/api/v1/demo",dict(profile="eligibility",actor="Confidential Reviewer"))
        _,_,body=self.call("/api/v1/diagnostics")
        text=json.dumps(body,ensure_ascii=False)
        self.assertNotIn(self.token,text)
        self.assertNotIn("Confidential Reviewer",text)
        self.assertTrue(set(body["configuration"]["secrets"].values())<={"set","unset"})

    def test_metric_route_labels_stay_bounded_across_many_identifiers(self):
        for _ in range(4):
            created=self.call("/api/v1/demo",dict(profile="eligibility",actor="QA"))[2]
            self.call("/api/v1/workflows/"+created["workflow_id"])
        _,_,body=self.call("/api/v1/diagnostics")
        labels={counter["labels"].get("route") for counter in body["metrics"]["counters"] if counter["name"]=="http_responses_total"}
        self.assertIn("/api/v1/workflows/:id",labels)
        self.assertEqual(body["metrics"]["dropped_series"],0)

    def test_provider_failure_returns_502_with_a_classification_and_no_retry(self):
        with patch.object(Application,"knowledge",side_effect=failure("unreachable","Embedding service refused the connection")):
            _,_,body=self.call("/api/v1/indexes",dict(workflow_ids=[],actor="QA"),expected=502)
        self.assertEqual(body["kind"],"unreachable")
        self.assertFalse(body["retried"]);self.assertFalse(body["fallback_used"])
        self.assertTrue(body["remediation"])
        self.assertNotIn("Traceback",json.dumps(body))

    def test_provider_failures_are_counted_by_kind(self):
        with patch.object(Application,"knowledge",side_effect=failure("timeout","Embedding call timed out")):
            self.call("/api/v1/indexes",dict(workflow_ids=[],actor="QA"),expected=502)
        _,_,body=self.call("/api/v1/diagnostics")
        counters={(c["name"],c["labels"].get("kind")):c["value"] for c in body["metrics"]["counters"]}
        self.assertEqual(counters.get(("provider_failures_total","timeout")),1)

class ExtractionFailureTests(unittest.TestCase):
    def setUp(self):
        metrics.reset();self.addCleanup(metrics.reset)
        temp=tempfile.TemporaryDirectory(prefix="rule2test-extract-fail-");self.addCleanup(temp.cleanup)
        self.db=Database(Path(temp.name)/"test.db")

    def proposal_for(self,error):
        provider=CountingFailureProvider(error)
        proposal=ExtractionService(self.db,provider).propose(extraction_request(),actor="BA")
        return provider,proposal

    def test_the_provider_is_called_exactly_once(self):
        provider,proposal=self.proposal_for(failure("timeout","Provider timed out"))
        self.assertEqual(provider.calls,1)
        self.assertEqual(proposal.status,"provider_error")

    def test_the_failure_kind_and_remediation_are_recorded_without_the_payload(self):
        _,proposal=self.proposal_for(failure("model_mismatch","gateway said tag 'secret-model' at 10.0.0.7"))
        self.assertIn("model_mismatch",proposal.issues[0])
        self.assertIn("ai_doctor.py",proposal.issues[0])
        self.assertNotIn("10.0.0.7",proposal.issues[0])
        self.assertNotIn("secret-model",proposal.issues[0])
        self.assertEqual(proposal.response_json,"")

    def test_an_unclassified_transport_error_is_still_classified(self):
        _,proposal=self.proposal_for(ConnectionRefusedError("refused"))
        self.assertIn("unreachable",proposal.issues[0])

    def test_no_fallback_to_mock_output_is_stored(self):
        _,proposal=self.proposal_for(failure("unreachable","down"))
        self.assertEqual(proposal.response_json,"")
        self.assertFalse(proposal.simulated)

    def test_failures_are_counted_by_kind(self):
        self.proposal_for(failure("timeout","down"))
        counters={(c["name"],c["labels"].get("kind")):c["value"] for c in metrics.snapshot()["counters"]}
        self.assertEqual(counters.get(("extraction_failures_total","timeout")),1)

if __name__=="__main__":unittest.main()
