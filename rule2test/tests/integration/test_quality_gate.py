"""Gate truth comes from controlled fixtures, never from the returned verdict."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from factory.api.dependencies import Application
from factory.api.routes.workspace import WorkspaceRoutes
from factory.services.quality_gate_service import QualityGateService, canonical_report
from factory.exceptions import ValidationError
from tests.integration.test_workspace_api import SUT

class QualityGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="rule2test-gate-")
        self.addCleanup(temporary.cleanup)
        self.app = Application(Path(temporary.name) / "gate.db")
        self.routes = WorkspaceRoutes(self.app)
        self.gate = QualityGateService(self.app.db)
    def action(self, w, action, **extra):
        return self.routes.post("/api/v1/workflows/" + w["workflow_id"] + "/" + action,
                                dict(revision=w["revision"], actor="Synthetic QA", **extra))
    def prepare(self, profile="eligibility", fault="none", evidence=True, reject=False):
        w = self.routes.post("/api/v1/demo", dict(profile=profile, actor="Synthetic BA"))
        w = self.action(w, "analyze")
        w = self.action(w, "start-review")
        tests = self.app.workflow.get(w["workflow_id"]).tests
        if reject:
            w = self.action(w, "review", tests=[dict(test_id=t.test_id, revision=t.revision) for t in tests[1:]],
                            decision="rejected", reason="Synthetic deliberate coverage loss")
            tests = tests[:1]
        w = self.action(w, "review", tests=[dict(test_id=t.test_id, revision=t.revision) for t in tests],
                        decision="approved", reason="Synthetic fixture review")
        w = self.action(w, "finalize", reason="Synthetic fixture finalization")
        w = self.action(w, "execute", sut={**SUT, "profile":profile, "fault":fault})["workflow"]
        if evidence:
            w = self.action(w, "evidence")["workflow"]
        return w
    def test_correct_threshold_profiles_go_and_hash_is_reproducible(self):
        for profile in ("eligibility", "claim_review"):
            with self.subTest(profile=profile):
                w = self.prepare(profile)
                report = self.gate.evaluate(w["workflow_id"])
                self.assertEqual(report["verdict"], "GO", report["reason"])
                self.assertEqual(report, self.gate.evaluate(w["workflow_id"]))
                digest = report.pop("report_hash")
                self.assertEqual(digest, hashlib.sha256(canonical_report(report).encode()).hexdigest())
    def test_faults_fail_even_with_full_exercised_coverage(self):
        for profile, fault in (("eligibility","boundary"), ("claim_review","boundary"), ("deductible","deductible_off_by_one")):
            with self.subTest(profile=profile):
                report = self.gate.evaluate(self.prepare(profile,fault)["workflow_id"])
                self.assertEqual(report["verdict"], "NO-GO")
                self.assertIn("execution_results", report["reason"])
                self.assertGreater(report["metrics"]["executions"]["fail"], 0)
    def test_deductible_unreachable_default_remains_explicitly_blocked(self):
        report = self.gate.evaluate(self.prepare("deductible")["workflow_id"])
        self.assertEqual(report["verdict"], "NO-GO")
        self.assertEqual(report["metrics"]["executions"]["fail"], 0)
        self.assertIn("resolved_obligations", report["reason"])
    def test_draft_is_not_evaluated_as_success(self):
        w = self.routes.post("/api/v1/demo", dict(profile="eligibility",actor="BA"))
        report = self.gate.evaluate(w["workflow_id"])
        self.assertEqual(report["verdict"],"NO-GO")
        self.assertEqual(report["metrics"], {})
        self.assertTrue(report["unmeasured"])
    def test_missing_evidence_blocks_otherwise_correct_run(self):
        report = self.gate.evaluate(self.prepare(evidence=False)["workflow_id"])
        self.assertEqual(report["verdict"],"NO-GO")
        self.assertIn("current_evidence",report["reason"])
    def test_reopened_review_cannot_reuse_old_go(self):
        w = self.prepare()
        old = self.gate.evaluate(w["workflow_id"])
        w = self.action(w,"reopen-review",reason="New review round")
        report = self.gate.evaluate(w["workflow_id"])
        self.assertEqual(report["verdict"],"NO-GO")
        self.assertNotEqual(report["workflow_hash"],old["workflow_hash"])
    def test_rejection_can_leave_all_pass_but_insufficient_coverage(self):
        report = self.gate.evaluate(self.prepare(reject=True)["workflow_id"])
        self.assertEqual(report["verdict"],"NO-GO")
        self.assertEqual(report["metrics"]["executions"]["fail"],0)
        self.assertIn("candidate_acceptance",report["reason"])
    def test_corrupt_archive_never_produces_go(self):
        w = self.prepare()
        with self.app.db.transaction() as c:
            c.execute("UPDATE wf_source_documents SET data=? WHERE workflow_id=?", (b"corrupt",w["workflow_id"]))
        with self.assertRaises(ValidationError):
            self.gate.evaluate(w["workflow_id"])
    def test_corrupt_journal_never_produces_go(self):
        w = self.prepare()
        with self.app.db.transaction() as c:
            c.execute("UPDATE wf_runs SET hash=? WHERE workflow_id=?", ("0"*64,w["workflow_id"]))
        with self.assertRaises(ValidationError):
            self.gate.evaluate(w["workflow_id"])
    def test_report_read_does_not_mutate_workflow(self):
        w = self.prepare()
        before = self.app.workflow.get(w["workflow_id"])
        events = self.app.workflow.events(w["workflow_id"])
        self.gate.evaluate(w["workflow_id"])
        self.assertEqual(before,self.app.workflow.get(w["workflow_id"]))
        self.assertEqual(events,self.app.workflow.events(w["workflow_id"]))

if __name__ == "__main__":
    unittest.main()
