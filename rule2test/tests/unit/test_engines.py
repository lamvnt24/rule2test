import unittest
from dataclasses import replace
from datetime import date,datetime,timezone
from decimal import Decimal
from unittest.mock import Mock
from factory.models import *
from factory.models.rule import PayoutFormula
from factory.engines.oracle_engine import OracleEngine
from factory.engines.insurance_engine import InsuranceEngine
from factory.engines.test_executor import TestExecutor
from factory.providers.sut.mock import MockSUTAdapter
from factory.exceptions import ValidationError,ConflictError,ProviderError
from factory.validators.llm_output_validator import validate_rule_proposal
from tests.fixtures.engine_cases import scenario,approved_case,money

class EngineTests(unittest.TestCase):
    def setUp(self): self.oracle=OracleEngine()
    def evaluate(self,profile,value):
        table,rules=scenario(profile)
        field="age" if profile=="eligibility" else "claim_amount"
        return self.oracle.evaluate(table,rules,(TestInput(field=field,value=value),))
    def test_eligibility_boundaries_against_explicit_truth(self):
        for age,outcome in [(17,Outcome.DENY),(18,Outcome.ALLOW),(64,Outcome.ALLOW),(65,Outcome.ALLOW),(66,Outcome.DENY)]:
            with self.subTest(age=age):
                self.assertEqual(self.evaluate("eligibility",Value(kind=ValueKind.INTEGER,data=age)).outcome,outcome)
    def test_claim_boundaries_against_explicit_truth(self):
        for amount,outcome in [(149999999,Outcome.ALLOW),(150000000,Outcome.ALLOW),(150000001,Outcome.REVIEW)]:
            self.assertEqual(self.evaluate("claim_review",money(amount)).outcome,outcome)
    def test_deductible_exact_boundary(self):
        for claim,payout in [("9999999","0"),("10000000","0"),("10000001","1"),("10000000.123456789123","0.123456789123")]:
            result=self.evaluate("deductible",money(claim))
            self.assertEqual(result.amount.data,Decimal(payout))
            self.assertIsNone(result.formula)
    def test_invalid_age_types_and_domain(self):
        for value in [Value(kind=ValueKind.INTEGER,data=-1),Value(kind=ValueKind.INTEGER,data=121),
                      Value(kind=ValueKind.TEXT,data="65"),Value(kind=ValueKind.BOOLEAN,data=True),
                      Value(kind=ValueKind.NULL),Value(kind=ValueKind.MISSING)]:
            self.assertEqual(self.evaluate("eligibility",value).outcome,Outcome.INVALID)
    def test_invalid_money_and_currency(self):
        for value in [money(-1),money(1000000001),money("0.0000000000001"),
                      Value(kind=ValueKind.INTEGER,data=100),replace(money(100),currency="USD")]:
            self.assertEqual(self.evaluate("claim_review",value).outcome,Outcome.INVALID)
    def test_missing_input_is_invalid(self):
        table,rules=scenario("eligibility")
        self.assertEqual(self.oracle.evaluate(table,rules,()).outcome,Outcome.INVALID)
    def test_unknown_field_rejected(self):
        table,rules=scenario("eligibility")
        with self.assertRaises(ValidationError):
            self.oracle.evaluate(table,rules,(TestInput(field="secret",value=money(1)),))
    def test_unique_collision_and_first_hit(self):
        table,rules=scenario("eligibility")
        other=replace(table.rows[0],row_id="ROW2")
        duplicate=replace(table,rows=table.rows+(other,))
        inputs=(TestInput(field="age",value=Value(kind=ValueKind.INTEGER,data=65)),)
        with self.assertRaises(ConflictError):self.oracle.evaluate(duplicate,rules,inputs)
        self.assertEqual(self.oracle.evaluate(replace(duplicate,hit_policy=HitPolicy.FIRST),rules,inputs).outcome,Outcome.ALLOW)
    def test_collect_rejected_explicitly(self):
        table,rules=scenario("eligibility")
        with self.assertRaises(ValidationError): self.oracle.evaluate(replace(table,hit_policy=HitPolicy.COLLECT),rules,())
    def test_tampered_row_rejected(self):
        table,rules=scenario("eligibility")
        bad=replace(table.rows[0],action=Action(outcome=Outcome.DENY))
        with self.assertRaises(ValidationError):self.oracle.evaluate(replace(table,rows=(bad,)),rules,())
    def test_effective_dates_require_context(self):
        table,rules=scenario("eligibility")
        rule=replace(rules[0],effective_from=date(2026,1,1),effective_to=date(2026,12,31))
        row=replace(table.rows[0],rule=replace(table.rows[0].rule,rule_hash=content_hash(rule)))
        table=replace(table,rows=(row,))
        inputs=(TestInput(field="age",value=Value(kind=ValueKind.INTEGER,data=65)),)
        with self.assertRaises(ValidationError):self.oracle.evaluate(table,(rule,),inputs)
        self.assertEqual(self.oracle.evaluate(table,(rule,),inputs,as_of=date(2026,12,31)).outcome,Outcome.ALLOW)
        self.assertEqual(self.oracle.evaluate(table,(rule,),inputs,as_of=date(2027,1,1)).outcome,Outcome.DENY)
    def test_null_and_missing_are_different_predicates(self):
        table,rules=scenario("eligibility")
        for kind,op in [(ValueKind.NULL,Operator.IS_NULL),(ValueKind.MISSING,Operator.IS_MISSING)]:
            rule=replace(rules[0],conditions=(Condition(field="age",operator=op,value=Value(kind=kind)),),action=Action(outcome=Outcome.REVIEW))
            ref=replace(table.rows[0].rule,rule_hash=content_hash(rule))
            row=replace(table.rows[0],rule=ref,conditions=rule.conditions,action=rule.action)
            result=self.oracle.evaluate(replace(table,rows=(row,)),(rule,),(TestInput(field="age",value=Value(kind=kind)),))
            self.assertEqual(result.outcome,Outcome.REVIEW)
    def test_executor_pass_and_injected_fail(self):
        for profile,value,expected,fault in [
            ("eligibility",Value(kind=ValueKind.INTEGER,data=65),Action(outcome=Outcome.ALLOW),"boundary"),
            ("claim_review",money(150000000),Action(outcome=Outcome.ALLOW),"boundary"),
            ("deductible",money(10000000),Action(outcome=Outcome.PAYOUT,amount=money(0)),"deductible_off_by_one")]:
            table,rules,test,approval=approved_case(profile,value,expected)
            for mode,status in [("none",ExecutionStatus.PASS),(fault,ExecutionStatus.FAIL)]:
                executor=TestExecutor(MockSUTAdapter(InsuranceEngine(profile=profile,fault=mode)))
                self.assertEqual(executor.execute(test,approval,table,rules,run_id="RUN").status,status)
    def test_wrong_approval_prevents_adapter_call(self):
        table,rules,test,approval=approved_case("eligibility",Value(kind=ValueKind.INTEGER,data=65),Action(outcome=Outcome.ALLOW))
        adapter=Mock();adapter.name="spy"
        for bad in [replace(approval,revision=2),replace(approval,decision=ApprovalDecision.REJECTED),replace(approval,content_hash="0"*64)]:
            with self.assertRaises(ValidationError):TestExecutor(adapter).execute(test,bad,table,rules,run_id="RUN")
        adapter.execute.assert_not_called()
    def test_wrong_expected_is_not_silently_repaired(self):
        table,rules,test,approval=approved_case("eligibility",Value(kind=ValueKind.INTEGER,data=65),Action(outcome=Outcome.DENY))
        adapter=Mock()
        with self.assertRaises(ValidationError):TestExecutor(adapter).execute(test,approval,table,rules,run_id="RUN")
        adapter.execute.assert_not_called()
    def test_timeout_is_error_and_secret_not_exposed(self):
        table,rules,test,approval=approved_case("eligibility",Value(kind=ValueKind.INTEGER,data=65),Action(outcome=Outcome.ALLOW))
        adapter=Mock();adapter.name="timeout";adapter.execute.side_effect=ProviderError("secret-token")
        result=TestExecutor(adapter).execute(test,approval,table,rules,run_id="RUN")
        self.assertEqual(result.status,ExecutionStatus.ERROR);self.assertIsNone(result.actual)
        self.assertNotIn("secret-token",result.error)
    def test_adapter_cannot_supply_formula_as_actual(self):
        table,rules,test,approval=approved_case("eligibility",Value(kind=ValueKind.INTEGER,data=65),Action(outcome=Outcome.ALLOW))
        adapter=Mock();adapter.name="bad";adapter.execute.return_value=Action(outcome=Outcome.PAYOUT,formula=PayoutFormula(field="claim_amount",deductible=money(10)))
        self.assertEqual(TestExecutor(adapter).execute(test,approval,table,rules,run_id="RUN").status,ExecutionStatus.ERROR)
    def test_mock_does_not_call_oracle(self):
        from unittest.mock import patch
        with patch.object(OracleEngine,"evaluate",side_effect=AssertionError("Oracle leaked into SUT")):
            actual=MockSUTAdapter(InsuranceEngine(profile="eligibility")).execute(
                (TestInput(field="age",value=Value(kind=ValueKind.INTEGER,data=65)),),timeout_seconds=1)
            self.assertEqual(actual.outcome,Outcome.ALLOW)
    def test_formula_json_roundtrip(self):
        table,_=scenario("deductible")
        self.assertEqual(DecisionTable.from_json(table.to_json()),table)
    def test_llm_source_hash_and_quote(self):
        _,rules=scenario("eligibility")
        rule=rules[0];source=rule.sources[0]
        self.assertEqual(validate_rule_proposal(rule.to_dict(),{source.document_id:source.quote.encode()}),rule)
        with self.assertRaises(ValidationError):validate_rule_proposal(rule.to_dict(),{source.document_id:b"wrong"})

    def test_typed_execution_evidence_roundtrip(self):
        table,rules,test,approval=approved_case("deductible",money(10000001),Action(outcome=Outcome.PAYOUT,amount=money(1)))
        execution=TestExecutor(MockSUTAdapter(InsuranceEngine(profile="deductible"))).execute(test,approval,table,rules,run_id="EVIDENCE")
        evidence=Evidence(evidence_id="EV1",run_id="EVIDENCE",rules=rules,tests=(test,),approvals=(approval,),
            executions=(execution,),metadata=Metadata(created_at=datetime.now(timezone.utc),created_by="QA"),decision_tables=(table,))
        self.assertEqual(Evidence.from_json(evidence.to_json()),evidence)
        self.assertEqual(execution.decision_table_hash,content_hash(table))
        with self.assertRaises(ValidationError):replace(evidence,decision_tables=())

    def test_future_approval_rejected(self):
        from datetime import timedelta
        table,rules,test,approval=approved_case("eligibility",Value(kind=ValueKind.INTEGER,data=65),Action(outcome=Outcome.ALLOW))
        approval=replace(approval,decided_at=datetime.now(timezone.utc)+timedelta(days=1))
        adapter=Mock()
        with self.assertRaises(ValidationError):TestExecutor(adapter).execute(test,approval,table,rules,run_id="FUTURE")
        adapter.execute.assert_not_called()
