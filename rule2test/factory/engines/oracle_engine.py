"""Deterministic expected-result engine. Never imports a SUT implementation."""
import operator
from dataclasses import dataclass
from decimal import Decimal, localcontext
from factory.models import Action, Outcome, Value, ValueKind, Operator, HitPolicy
from factory.models.common import require
from factory.validators.rule_validator import validate_table, FIELDS
from factory.validators.test_validator import input_map, valid_business_value
from factory.exceptions import ConflictError

def legacy_oracle(rule,value):
    lo,hi=FIELDS[rule["field"]]
    if type(value) is not int or not lo<=value<=hi: return "INVALID"
    return "ALLOW" if value<=rule["threshold"] else "REVIEW"

_COMPARISONS={Operator.EQ:operator.eq,Operator.NE:operator.ne,Operator.LT:operator.lt,
              Operator.LE:operator.le,Operator.GT:operator.gt,Operator.GE:operator.ge}

@dataclass(frozen=True)
class EvaluationTrace:
    action: Action
    matched_row_ids: tuple[str, ...] = ()
    default_used: bool = False

class OracleEngine:
    def evaluate(self,table,rules,inputs,*,as_of=None):
        return self.trace(table,rules,inputs,as_of=as_of).action

    def trace(self,table,rules,inputs,*,as_of=None):
        lookup,currency=validate_table(table,rules,as_of)
        values=input_map(inputs)
        active=[]
        for row in table.rows:
            rule=lookup[(row.rule.rule_id,row.rule.version)]
            if rule.effective_from is not None and as_of<rule.effective_from: continue
            if rule.effective_to is not None and as_of>rule.effective_to: continue
            active.append(row)
        required={c.field for row in active for c in row.conditions}
        for action in [table.default_action]+[r.action for r in active]:
            if action.formula: required.add(action.formula.field)
        # Invalid values never silently match a permissive default.
        for field in set(values)|required:
            value=values.get(field,Value(kind=ValueKind.MISSING))
            if value.kind in (ValueKind.NULL,ValueKind.MISSING):
                accepted=any(c.field==field and c.value.kind==value.kind for row in active for c in row.conditions)
                if not accepted: return EvaluationTrace(Action(outcome=Outcome.INVALID))
            elif not valid_business_value(field,value,currency):
                return EvaluationTrace(Action(outcome=Outcome.INVALID))
        matches=[]
        for row in active:
            if all(self._matches(c,values.get(c.field,Value(kind=ValueKind.MISSING))) for c in row.conditions):
                matches.append(row)
                if table.hit_policy is HitPolicy.FIRST: break
        if len(matches)>1: raise ConflictError("UNIQUE hit policy violated: "+", ".join(r.row_id for r in matches))
        action=matches[0].action if matches else table.default_action
        return EvaluationTrace(self._resolve(action,values),tuple(r.row_id for r in matches),not matches)

    @staticmethod
    def _matches(condition,value):
        if condition.operator is Operator.IS_NULL: return value.kind is ValueKind.NULL
        if condition.operator is Operator.IS_MISSING: return value.kind is ValueKind.MISSING
        if condition.value.kind is not value.kind: return False
        return _COMPARISONS[condition.operator](value.data,condition.value.data)

    @staticmethod
    def _resolve(action,values):
        if action.formula is None: return action
        value=values.get(action.formula.field)
        if value is None or value.kind is not ValueKind.MONEY: return Action(outcome=Outcome.INVALID)
        if value.currency!=action.formula.deductible.currency: return Action(outcome=Outcome.INVALID)
        with localcontext() as ctx:
            ctx.prec=64
            amount=max(Decimal(0),value.data-action.formula.deductible.data)
        return Action(outcome=Outcome.PAYOUT,amount=Value(kind=ValueKind.MONEY,data=amount,currency=value.currency))
