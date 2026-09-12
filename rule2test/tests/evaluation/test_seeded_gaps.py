"""Independent finite truth sets: benchmark recall, not a production accuracy claim."""
import unittest
from factory.models import TestCase,TestInput,Value,ValueKind,TestKind,TestOrigin,Action,Outcome
from factory.services.gap_service import GapService
from tests.fixtures.engine_cases import scenario,money

class SeededGapBenchmark(unittest.TestCase):
    def test_age_new_upper_boundary_recall(self):
        table,rules=scenario("eligibility")
        ref=table.rows[0].rule
        suite=tuple(TestCase(test_id="AGE-"+str(age),revision=1,title="Existing age",
            inputs=(TestInput(field="age",value=Value(kind=ValueKind.INTEGER,data=age)),),
            expected=Action(outcome=Outcome.ALLOW if 18<=age<=65 else Outcome.DENY),
            kind=TestKind.BOUNDARY,origin=TestOrigin.EXISTING,rules=(ref,),rationale="Synthetic benchmark",
            metadata=rules[0].metadata) for age in (17,18,19,60,61))
        gaps=GapService().analyze(table,rules,suite)
        truth={64,65,66}
        detected={o.inputs[0].value.data for o in gaps.obligations if o.category=="boundary" and o.obligation_id in gaps.missing_ids and o.inputs is not None}
        self.assertEqual(len(truth&detected)/len(truth),1.0)
        self.assertFalse({17,18,19}&detected)

    def test_claim_threshold_recall(self):
        table,rules=scenario("claim_review")
        gaps=GapService().analyze(table,rules)
        truth={149999999,150000000,150000001}
        detected={o.inputs[0].value.data for o in gaps.obligations if o.category=="boundary" and o.inputs is not None}
        self.assertEqual(len(truth&detected)/len(truth),1.0)
