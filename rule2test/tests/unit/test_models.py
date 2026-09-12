import unittest
from dataclasses import replace, FrozenInstanceError
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from factory.exceptions import ValidationError, ConfigurationError
from factory.config import Settings
from factory.models.common import *
from factory.models.rule import *
from factory.models.rule_delta import *
from factory.models.decision_table import *
from factory.models.test_case import TestCase, TestInput, TestKind, TestOrigin
from factory.models.approval import *
from factory.models.execution import *
from factory.models.evidence import Evidence, content_hash

class ModelTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,9,11,tzinfo=timezone.utc)
        self.meta=Metadata(created_at=self.now,created_by="QA")
        self.source=SourceReference(document_id="rules.xlsx",document_hash="a"*64,quote="Age <= 65",sheet="Rules",cell="B2")
        self.rule=Rule(rule_id="R01",version=1,title="Maximum age",
            conditions=(Condition(field="age",operator=Operator.LE,value=Value(kind=ValueKind.INTEGER,data=65)),),
            action=Action(outcome=Outcome.ALLOW),sources=(self.source,),metadata=self.meta)
        self.ref=RuleReference(rule_id="R01",version=1,rule_hash=content_hash(self.rule))
        self.test=TestCase(test_id="TC01",revision=1,title="At age boundary",
            inputs=(TestInput(field="age",value=Value(kind=ValueKind.INTEGER,data=65)),),
            expected=Action(outcome=Outcome.ALLOW),kind=TestKind.BOUNDARY,origin=TestOrigin.DETERMINISTIC,
            rules=(self.ref,),rationale="At upper boundary",metadata=self.meta)
        self.approval=Approval(approval_id="A1",subject_kind=SubjectKind.TEST,subject_id="TC01",revision=1,
            content_hash=content_hash(self.test),reviewer="QA",decision=ApprovalDecision.APPROVED,
            decided_at=self.now,reason="Boundary reviewed")
        self.execution=Execution(execution_id="E1",run_id="RUN1",test_id="TC01",test_revision=1,
            test_hash=content_hash(self.test),rules=(self.ref,),approval_id="A1",
            expected=self.test.expected,actual=self.test.expected,status=ExecutionStatus.PASS,
            adapter="mock-v1",started_at=self.now,finished_at=self.now)
        self.evidence=Evidence(evidence_id="EV1",run_id="RUN1",rules=(self.rule,),tests=(self.test,),
            approvals=(self.approval,),executions=(self.execution,),metadata=self.meta)
    def test_evidence_roundtrip(self):
        self.assertEqual(Evidence.from_json(self.evidence.to_json()),self.evidence)
        self.assertEqual(Evidence.from_json(self.evidence.to_json()).fingerprint,self.evidence.fingerprint)
    def test_decimal_date_missing_roundtrip(self):
        for value in (Value(kind=ValueKind.MONEY,data=Decimal("999999999.123456789"),currency="VND"),
                      Value(kind=ValueKind.DATE,data=date(2026,9,11)),Value(kind=ValueKind.NULL),Value(kind=ValueKind.MISSING)):
            self.assertEqual(Value.from_json(value.to_json()),value)
        self.assertNotEqual(Value(kind=ValueKind.NULL),Value(kind=ValueKind.MISSING))
    def test_bool_not_integer(self):
        with self.assertRaises(ValidationError): Value(kind=ValueKind.INTEGER,data=True)
        with self.assertRaises(ValidationError): replace(self.rule,version=True)
    def test_money_validation(self):
        for number in (Decimal("NaN"),Decimal("Infinity")):
            with self.assertRaises(ValidationError): Value(kind=ValueKind.MONEY,data=number,currency="VND")
        with self.assertRaises(ValidationError): Value(kind=ValueKind.MONEY,data=Decimal(10))
        with self.assertRaises(ValidationError): Value(kind=ValueKind.MONEY,data=10.1,currency="VND")
    def test_unknown_missing_and_malformed_json(self):
        data=self.rule.to_dict();data["untrusted"]=1
        with self.assertRaises(ValidationError): Rule.from_dict(data)
        with self.assertRaises(ValidationError): Rule.from_dict({})
        with self.assertRaises(ValidationError): Rule.from_json("{")
    def test_rule_constraints(self):
        for updates in ({"version":0},{"sources":()},{"conditions":()},
                        {"effective_from":date(2026,9,11),"effective_to":date(2025,1,1)}):
            with self.assertRaises(ValidationError): replace(self.rule,**updates)
        with self.assertRaises(ValidationError): Condition(field="age",operator=Operator.LE,value=Value(kind=ValueKind.INTEGER,data=121))
    def test_source_validation(self):
        with self.assertRaises(ValidationError): replace(self.source,cell=None)
        with self.assertRaises(ValidationError): replace(self.source,document_hash="bad")
        with self.assertRaises(ValidationError): replace(self.source,cell="A0")
    def test_immutable(self):
        with self.assertRaises(FrozenInstanceError): self.rule.title="changed"
        with self.assertRaises(ValidationError): replace(self.rule,conditions=list(self.rule.conditions))
    def test_decision_table(self):
        row=DecisionRow(row_id="D1",conditions=self.rule.conditions,action=self.rule.action,rule=self.ref)
        table=DecisionTable(table_id="DT1",version=1,hit_policy=HitPolicy.UNIQUE,rows=(row,),default_action=Action(outcome=Outcome.REVIEW))
        self.assertEqual(DecisionTable.from_json(table.to_json()),table)
        with self.assertRaises(ValidationError): replace(table,rows=(row,row))
    def test_delta_snapshots(self):
        newer=replace(self.rule,version=2,title="Updated")
        delta=RuleDelta(delta_id="D1",kind=DeltaKind.MODIFIED,before=self.rule,after=newer,changed_fields=("title",))
        self.assertEqual(RuleDelta.from_json(delta.to_json()),delta)
        with self.assertRaises(ValidationError): replace(delta,changed_fields=("action",))
        with self.assertRaises(ValidationError): replace(delta,after=self.rule)
        added=RuleDelta(delta_id="D2",kind=DeltaKind.ADDED,before=None,after=self.rule)
        self.assertEqual(RuleDelta.from_json(added.to_json()),added)
    def test_execution_error_not_fail(self):
        error=replace(self.execution,status=ExecutionStatus.ERROR,actual=None,error="timeout")
        self.assertEqual(Execution.from_json(error.to_json()),error)
        with self.assertRaises(ValidationError): replace(self.execution,status=ExecutionStatus.FAIL)
        with self.assertRaises(ValidationError): replace(self.execution,status=ExecutionStatus.ERROR)
    def test_stale_approval_rejected(self):
        for updates in ({"revision":2},{"content_hash":"b"*64},{"decision":ApprovalDecision.REJECTED},
                        {"decided_at":self.now+timedelta(seconds=1)}):
            with self.assertRaises(ValidationError): replace(self.evidence,approvals=(replace(self.approval,**updates),))
    def test_tampered_evidence_rejected(self):
        with self.assertRaises(ValidationError): replace(self.evidence,rules=(replace(self.rule,title="Tampered"),))
        with self.assertRaises(ValidationError): replace(self.evidence,run_id="wrong")
        with self.assertRaises(ValidationError): replace(self.evidence,executions=(self.execution,self.execution))
    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValidationError): replace(self.meta,created_at=datetime(2026,9,11))
    def test_test_inputs_allow_negative_case(self):
        invalid=replace(self.test,inputs=(TestInput(field="age",value=Value(kind=ValueKind.INTEGER,data=-1)),))
        self.assertEqual(TestCase.from_json(invalid.to_json()),invalid)
        with self.assertRaises(ValidationError): replace(self.test,inputs=self.test.inputs*2)
    def test_malformed_decimal_and_duplicate_json(self):
        with self.assertRaises(ValidationError):
            Value.from_dict({"kind":"money","data":{"$decimal":"not-money"},"currency":"VND"})
        with self.assertRaises(ValidationError):
            Value.from_json('{"kind":"null","kind":"missing"}')
    def test_payout_contract(self):
        payout=Action(outcome=Outcome.PAYOUT,amount=Value(kind=ValueKind.MONEY,data=Decimal("100.25"),currency="VND"))
        self.assertEqual(Action.from_json(payout.to_json()),payout)
        with self.assertRaises(ValidationError): Action(outcome=Outcome.PAYOUT)
        with self.assertRaises(ValidationError): Action(outcome=Outcome.ALLOW,amount=payout.amount)
    def test_config(self):
        self.assertEqual(Settings.from_env({}).port,8000)
        with self.assertRaises(ConfigurationError): Settings.from_env({"RULE2TEST_PORT":"bad"})
        with self.assertRaises(ConfigurationError): Settings.from_env({"RULE2TEST_LLM_PROVIDER":"openai"})
        settings=Settings.from_env({"RULE2TEST_LLM_PROVIDER":"openai","OPENAI_API_KEY":"secret-123","OPENAI_MODEL":"configured-model"})
        self.assertNotIn("secret-123",repr(settings))
        with self.assertRaises(ConfigurationError): Settings(port=True)
if __name__=="__main__": unittest.main()
