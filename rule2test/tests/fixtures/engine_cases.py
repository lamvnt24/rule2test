"""Synthetic business specifications with explicit source text, shared by tests and CLI."""
from datetime import datetime,timezone
from decimal import Decimal
from factory.models import *
from factory.models.rule import PayoutFormula

def money(value):
    return Value(kind=ValueKind.MONEY,data=Decimal(str(value)),currency="VND")

def scenario(profile):
    meta=Metadata(created_at=datetime(2020,1,1,tzinfo=timezone.utc),created_by="Synthetic fixture")
    if profile=="eligibility":
        quote="Age from 18 through 65 inclusive is allowed; otherwise denied."
        conditions=(Condition(field="age",operator=Operator.GE,value=Value(kind=ValueKind.INTEGER,data=18)),
                    Condition(field="age",operator=Operator.LE,value=Value(kind=ValueKind.INTEGER,data=65)))
        action=Action(outcome=Outcome.ALLOW);default=Action(outcome=Outcome.DENY)
    elif profile=="claim_review":
        quote="Claims exceeding 150000000 VND require review; other valid claims are allowed."
        conditions=(Condition(field="claim_amount",operator=Operator.GT,value=money(150000000)),)
        action=Action(outcome=Outcome.REVIEW);default=Action(outcome=Outcome.ALLOW)
    elif profile=="deductible":
        quote="Payout equals max(claim_amount - 10000000 VND, 0)."
        conditions=(Condition(field="claim_amount",operator=Operator.GE,value=money(0)),)
        action=Action(outcome=Outcome.PAYOUT,formula=PayoutFormula(field="claim_amount",deductible=money(10000000)))
        default=Action(outcome=Outcome.INVALID)
    else: raise ValueError("Unknown profile")
    import hashlib
    source=SourceReference(document_id=profile+".txt",document_hash=hashlib.sha256(quote.encode()).hexdigest(),quote=quote)
    rule=Rule(rule_id="R-"+profile,version=1,title=profile,conditions=conditions,action=action,sources=(source,),metadata=meta)
    ref=RuleReference(rule_id=rule.rule_id,version=rule.version,rule_hash=content_hash(rule))
    row=DecisionRow(row_id="ROW1",conditions=conditions,action=action,rule=ref)
    table=DecisionTable(table_id="DT-"+profile,version=1,hit_policy=HitPolicy.UNIQUE,rows=(row,),default_action=default)
    return table,(rule,)

def approved_case(profile,value,expected):
    table,rules=scenario(profile)
    field="age" if profile=="eligibility" else "claim_amount"
    inputs=(TestInput(field=field,value=value),)
    test=TestCase(test_id="TC-"+profile,revision=1,title="Boundary",inputs=inputs,expected=expected,
        kind=TestKind.BOUNDARY,origin=TestOrigin.HUMAN,rules=(table.rows[0].rule,),
        rationale="Explicit synthetic expected, independently specified",metadata=rules[0].metadata)
    approval=Approval(approval_id="A-"+profile,subject_kind=SubjectKind.TEST,subject_id=test.test_id,revision=1,
        content_hash=content_hash(test),reviewer="Synthetic demo reviewer",decision=ApprovalDecision.APPROVED,
        decided_at=rules[0].metadata.created_at,reason="Fixture only; not a real user approval")
    return table,rules,test,approval
