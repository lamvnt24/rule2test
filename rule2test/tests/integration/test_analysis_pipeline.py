import unittest
from scripts.run_analysis_demo import run_demo
from factory.models import Evidence

class AnalysisPipelineTests(unittest.TestCase):
    def test_rule_change_to_evidence(self):
        report=run_demo()
        self.assertEqual(len(report["delta"]["deltas"]),1)
        self.assertEqual(sum(x["status"]=="changed" for x in report["impact"]),1)
        self.assertLess(report["baseline_boundary_percent"],report["final_boundary_percent"])
        self.assertEqual(report["final_boundary_percent"],100)
        self.assertEqual(report["mutation_score"],100)
        good,bad=report["runs"]
        self.assertEqual(good["failed"],0);self.assertEqual(good["errors"],0)
        self.assertEqual(bad["failed"],1);self.assertEqual(bad["errors"],0)
        for run in report["runs"]:
            evidence=Evidence.from_dict(run["evidence"])
            self.assertEqual(evidence.fingerprint,run["evidence_hash"])
