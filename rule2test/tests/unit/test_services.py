import unittest
from dataclasses import replace
from datetime import datetime,timezone
from decimal import Decimal
from factory.models import *
from factory.models.analysis import DeltaAnalysis,GenerationResult,CoverageReport,MutationStatus
from factory.services.rule_delta_service import RuleDeltaService
from factory.services.impact_service import ImpactService
from factory.services.gap_service import GapService
from factory.services.generation_service import GenerationService
from factory.services.coverage_service import CoverageService
from factory.services.mutation_service import MutationService
from factory.services._support import inputs_key
from factory.exceptions import ValidationError
from factory.engines.test_executor import TestExecutor
from factory.providers.sut.mock import MockSUTAdapter
from factory.engines.insurance_engine import InsuranceEngine
from tests.fixtures.engine_cases import scenario,approved_case,money

def older_eligibility():
    table,rules=scenario("eligibility")
    old=replace(rules[0],conditions=(rules[0].conditions[0],replace(rules[0].conditions[1],value=Value(kind=ValueKind.INTEGER,data=60))))
    newer=replace(rules[0],version=2)
    def bind(rule):
        ref=RuleReference(rule_id=rule.rule_id,version=rule.version,rule_hash=content_hash(rule))
        return replace(table,version=rule.version,rows=(replace(table.rows[0],conditions=rule.conditions,rule=ref),)),(rule,)
    return (*bind(old),*bind(newer))

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.table,self.rules=scenario("eligibility")
        self.meta=Metadata(created_at=datetime(2020,1,1,tzinfo=timezone.utc),created_by="QA")
    def candidates(self):
        gaps=GapService().analyze(self.table,self.rules)
        return GenerationService().generate(self.table,self.rules,gaps,metadata=self.meta).candidates
    def test_delta_detects_threshold_and_roundtrips(self):
        old_table,old,new_table,new=older_eligibility()
        report=RuleDeltaService().compare(old,new)
        self.assertEqual(len(report.deltas),1)
        self.assertEqual(report.deltas[0].changed_fields,("conditions",))
        self.assertEqual(DeltaAnalysis.from_json(report.to_json()),report)
    def test_presentation_and_order_do_not_create_semantic_delta(self):
        newer=replace(self.rules[0],version=2,title="  Eligibility reformatted  ",conditions=tuple(reversed(self.rules[0].conditions)))
        report=RuleDeltaService().compare(self.rules,(newer,))
        self.assertEqual(report.deltas,())
        self.assertEqual(report.presentation_only_rule_ids,(newer.rule_id,))
    def test_add_remove_and_version_guard(self):
        self.assertEqual(RuleDeltaService().compare((),self.rules).deltas[0].kind,DeltaKind.ADDED)
        self.assertEqual(RuleDeltaService().compare(self.rules,()).deltas[0].kind,DeltaKind.REMOVED)
        with self.assertRaises(ValidationError):RuleDeltaService().compare(self.rules,(replace(self.rules[0],title="Changed"),))
        with self.assertRaises(ValidationError):RuleDeltaService().compare(self.rules,self.rules*2)
    def test_impact_related_vs_changed(self):
        ot,old,nt,new=older_eligibility()
        _,_,base,_=approved_case("eligibility",Value(kind=ValueKind.INTEGER,data=60),Action(outcome=Outcome.ALLOW))
        tests=tuple(replace(base,test_id="TC"+str(age),inputs=(TestInput(field="age",value=Value(kind=ValueKind.INTEGER,data=age)),),
            rules=(ot.rows[0].rule,),expected=Action(outcome=Outcome.ALLOW if age<=60 else Outcome.DENY)) for age in (18,60,61))
        report=ImpactService().analyze(ot,old,nt,new,tests)
        self.assertEqual(sum(x.related for x in report),3)
        self.assertEqual(sum(x.status=="changed" for x in report),1)
        self.assertTrue(next(x for x in report if x.test_id=="TC61").expected_is_stale)
    def test_impact_table_default_change(self):
        _,_,test,_=approved_case("eligibility",Value(kind=ValueKind.INTEGER,data=17),Action(outcome=Outcome.DENY))
        newer=replace(self.table,version=2,default_action=Action(outcome=Outcome.REVIEW))
        record=ImpactService().analyze(self.table,self.rules,newer,self.rules,(test,))[0]
        self.assertEqual(record.status,"changed");self.assertTrue(record.related)
    def test_generation_is_stable_and_deduplicated(self):
        gaps=GapService().analyze(self.table,self.rules)
        first=GenerationService().generate(self.table,self.rules,gaps,metadata=self.meta)
        second=GenerationService().generate(self.table,self.rules,gaps,metadata=self.meta)
        self.assertEqual(first,second)
        self.assertEqual(GenerationResult.from_json(first.to_json()),first)
        keys=[inputs_key(t.inputs) for t in first.candidates]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertTrue(all(t.obligation_ids and t.rationale for t in first.candidates))
    def test_boundary_ground_truth_and_negative_cases(self):
        candidates=self.candidates()
        ints={t.inputs[0].value.data for t in candidates if t.inputs[0].value.kind is ValueKind.INTEGER}
        self.assertTrue({17,18,19,64,65,66,-1,121}<=ints)
        kinds={t.inputs[0].value.kind for t in candidates}
        self.assertTrue({ValueKind.NULL,ValueKind.MISSING,ValueKind.TEXT}<=kinds)
    def test_full_design_coverage_and_empty_suite(self):
        report=CoverageService().measure(self.table,self.rules,self.candidates())
        self.assertEqual(report.rule.percent,100)
        self.assertEqual(report.boundary.percent,100)
        self.assertEqual(report.branch.percent,100)
        self.assertEqual(report.exception.percent,100)
        self.assertEqual(CoverageReport.from_json(report.to_json()),report)
        empty=CoverageService().measure(self.table,self.rules,())
        self.assertEqual(empty.boundary.percent,0)
    def test_covered_suite_generates_no_more_candidates(self):
        candidates=self.candidates()
        gaps=GapService().analyze(self.table,self.rules,candidates)
        self.assertEqual(gaps.missing_ids,())
        self.assertEqual(GenerationService().generate(self.table,self.rules,gaps,metadata=self.meta).candidates,())
    def test_decimal_scale_does_not_duplicate_input_coverage(self):
        self.assertEqual(inputs_key((TestInput(field="claim_amount",value=money("150.0")),)),
                         inputs_key((TestInput(field="claim_amount",value=money("150.00")),)))
    def test_shadowed_row_stays_unresolved(self):
        second=replace(self.rules[0],rule_id="R-shadowed")
        ref=RuleReference(rule_id=second.rule_id,version=1,rule_hash=content_hash(second))
        table=replace(self.table,hit_policy=HitPolicy.FIRST,rows=self.table.rows+(replace(self.table.rows[0],row_id="SHADOW",rule=ref),))
        rules=self.rules+(second,)
        gaps=GapService().analyze(table,rules)
        self.assertTrue(any(o.row_id=="SHADOW" and o.inputs is None for o in gaps.obligations))
        candidates=GenerationService().generate(table,rules,gaps,metadata=self.meta).candidates
        coverage=CoverageService().measure(table,rules,candidates)
        self.assertLess(coverage.rule.percent,100)
        self.assertTrue(coverage.unresolved_ids)
    def test_deductible_boundaries_and_unreachable_default(self):
        table,rules=scenario("deductible")
        gaps=GapService().analyze(table,rules)
        formula=[o for o in gaps.obligations if o.label.startswith("deductible ")]
        self.assertEqual({o.inputs[0].value.data for o in formula},{Decimal("9999999"),Decimal("10000000"),Decimal("10000001")})
        self.assertTrue(any(o.label=="default selected" and o.inputs is None for o in gaps.obligations))
    def test_compound_fields_keep_other_conditions_true(self):
        condition=Condition(field="claim_amount",operator=Operator.LE,value=money(150000000))
        rule=replace(self.rules[0],conditions=self.rules[0].conditions+(condition,))
        ref=replace(self.table.rows[0].rule,rule_hash=content_hash(rule))
        table=replace(self.table,rows=(replace(self.table.rows[0],conditions=rule.conditions,rule=ref),))
        gaps=GapService().analyze(table,(rule,))
        boundary=next(o for o in gaps.obligations if "claim_amount at" in o.label)
        values={x.field:x.value.data for x in boundary.inputs}
        self.assertTrue(18<=values["age"]<=65)
        self.assertEqual(values["claim_amount"],Decimal(150000000))
    def test_search_budget_fails_explicitly(self):
        with self.assertRaises(ValidationError):GapService(max_combinations=1).analyze(self.table,self.rules)
    def test_rebase_creates_revision_without_mutating_original(self):
        ot,old,nt,new=older_eligibility()
        _,_,test,_=approved_case("eligibility",Value(kind=ValueKind.INTEGER,data=61),Action(outcome=Outcome.DENY))
        test=replace(test,rules=(ot.rows[0].rule,))
        proposal=GenerationService().rebase(nt,new,(test,),metadata=self.meta)[0]
        self.assertEqual(proposal.revision,2);self.assertEqual(proposal.expected.outcome,Outcome.ALLOW)
        self.assertEqual(test.revision,1);self.assertEqual(test.expected.outcome,Outcome.DENY)
    def test_mutations_are_killed_by_concrete_witnesses(self):
        report=MutationService().analyze(self.table,self.rules,self.candidates())
        self.assertEqual(report.score,100)
        self.assertTrue(all(r.witnesses for r in report.results if r.status is MutationStatus.KILLED))
    def test_no_tests_has_no_mutation_score(self):
        report=MutationService().analyze(self.table,self.rules,())
        self.assertIsNone(report.score)
    def test_invalid_mutants_reported_and_budget_guarded(self):
        table,rules=scenario("deductible")
        gaps=GapService().analyze(table,rules)
        tests=GenerationService().generate(table,rules,gaps,metadata=self.meta).candidates
        report=MutationService().analyze(table,rules,tests)
        self.assertTrue(any(r.status is MutationStatus.INVALID for r in report.results))
        self.assertTrue(any(r.status is MutationStatus.SURVIVED for r in report.results))
        with self.assertRaises(ValidationError):MutationService(max_mutants=1).analyze(self.table,self.rules,self.candidates())
    def test_execution_coverage_excludes_errors(self):
        table,rules,test,approval=approved_case("eligibility",Value(kind=ValueKind.INTEGER,data=65),Action(outcome=Outcome.ALLOW))
        execution=TestExecutor(MockSUTAdapter(InsuranceEngine(profile="eligibility",fault="boundary"))).execute(test,approval,table,rules,run_id="R")
        failed=CoverageService().measure(table,rules,(test,),executions=(execution,))
        self.assertGreater(failed.boundary.covered,0)
        error=replace(execution,status=ExecutionStatus.ERROR,actual=None,error="timeout")
        report=CoverageService().measure(table,rules,(test,),executions=(error,))
        self.assertEqual(report.boundary.covered,0)
        with self.assertRaises(ValidationError):
            CoverageService().measure(table,rules,(test,),executions=(replace(execution,test_hash="0"*64),))
