
import unittest,json,copy
from pathlib import Path
from factory.core import analyze,execute,oracle,digest
class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((Path(__file__).resolve().parents[1]/"data/demo.json").read_text())
        self.plan=analyze(**self.data)
        self.ids=[x["id"] for x in self.plan["candidates"]]
    def test_full_pipeline(self):
        r=execute(self.plan,self.ids,"none")
        self.assertEqual(r["gate"],"GO")
        self.assertEqual(r["metrics"]["boundary_coverage"],100)
        self.assertEqual(r["metrics"]["mutation_score"],100)
        self.assertTrue(all(x["source"] and x["rule_hash"] for x in r["rows"]))
    def test_injected_boundary_is_detected(self):
        r=execute(self.plan,self.ids,"boundary")
        self.assertEqual(r["metrics"]["failed"],2)
        self.assertEqual(r["gate"],"NO-GO")
    def test_missing_approval_never_executes_candidates(self):
        r=execute(self.plan,[],"none")
        self.assertEqual(len(r["rows"]),len(self.data["existing"]))
        self.assertEqual(r["gate"],"NO-GO")
    def test_unknown_approval_is_rejected(self):
        with self.assertRaises(ValueError):execute(self.plan,["fake"],"none")
    def test_boolean_is_not_integer_input(self):
        self.assertEqual(oracle(self.data["new"][0],True),"INVALID")
    def test_rule_ids_must_be_unique(self):
        self.data["new"][1]["id"]="R01"
        with self.assertRaises(ValueError):analyze(**self.data)
    def test_behavior_impact_is_not_all_related_tests(self):
        self.assertEqual(len(self.plan["impact"]),5)
        self.assertEqual(sum(t["behavior_changed"] for t in self.plan["impact"]),2)
    def test_hash_detects_tampering(self):
        before=digest(self.plan);self.plan["new"][0]["threshold"]=64
        self.assertNotEqual(before,digest(self.plan))
    def test_seeded_gap_recall(self):
        # Independent fixture truth: seven withheld obligations per rule.
        expected={(rid,label) for rid in ("R01","R02") for label in ("below","at","above","null","negative","overflow","wrong_type")}
        found={(t["rule_id"],t["obligation"]) for t in self.plan["candidates"]}
        self.assertEqual(len(expected & found)/len(expected),1)
    def test_domain_overflow_and_stale_fault(self):
        r=execute(self.plan,self.ids,"stale")
        self.assertGreater(r["metrics"]["failed"],0)
        self.assertEqual(oracle(self.data["new"][0],121),"INVALID")
if __name__=="__main__":unittest.main()
