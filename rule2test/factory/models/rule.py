"""Versioned rule IR. Conditions are an AND conjunction."""
from dataclasses import dataclass
from datetime import date
from enum import Enum
from .common import Model, Value, ValueKind, SourceReference, Metadata, require, nonempty

class Operator(str,Enum):
    EQ="eq"
    NE="ne"
    LT="lt"
    LE="le"
    GT="gt"
    GE="ge"
    IS_NULL="is_null"
    IS_MISSING="is_missing"

class Outcome(str,Enum):
    ALLOW="allow"
    DENY="deny"
    REVIEW="review"
    INVALID="invalid"
    PAYOUT="payout"

@dataclass(frozen=True,kw_only=True)
class Condition(Model):
    field: str
    operator: Operator
    value: Value
    def __post_init__(self):
        super().__post_init__();nonempty(self.field,"field")
        if self.operator is Operator.IS_NULL: require(self.value.kind is ValueKind.NULL,"is_null requires null value")
        elif self.operator is Operator.IS_MISSING: require(self.value.kind is ValueKind.MISSING,"is_missing requires missing value")
        else:
            require(self.value.kind not in (ValueKind.NULL,ValueKind.MISSING),"Use explicit null/missing operator")
            if self.operator in (Operator.LT,Operator.LE,Operator.GT,Operator.GE):
                require(self.value.kind in (ValueKind.INTEGER,ValueKind.MONEY,ValueKind.DATE),"Ordered comparison requires integer, money or date")
        if self.field=="age" and self.value.kind not in (ValueKind.NULL,ValueKind.MISSING):
            require(self.value.kind is ValueKind.INTEGER and 0<=self.value.data<=120,"Age threshold must be integer 0..120")

@dataclass(frozen=True,kw_only=True)
class PayoutFormula(Model):
    """Only supported formula: max(claim_amount - deductible, 0). No code evaluation."""
    field: str
    deductible: Value
    def __post_init__(self):
        super().__post_init__()
        require(self.field=="claim_amount","Only claim_amount payout formula is supported")
        require(self.deductible.kind is ValueKind.MONEY and self.deductible.data>=0,
                "Deductible must be nonnegative money")

@dataclass(frozen=True,kw_only=True)
class Action(Model):
    outcome: Outcome
    amount: Value | None = None
    formula: PayoutFormula | None = None
    def __post_init__(self):
        super().__post_init__()
        if self.outcome is Outcome.PAYOUT:
            require((self.amount is None)!=(self.formula is None),"Payout requires either fixed money or formula")
            if self.amount is not None:
                require(self.amount.kind is ValueKind.MONEY,"Payout requires money")
                require(self.amount.data>=0,"Payout must not be negative")
        else:
            require(self.amount is None and self.formula is None,"Only payout may have money/formula")

@dataclass(frozen=True,kw_only=True)
class Rule(Model):
    rule_id: str
    version: int
    title: str
    conditions: tuple[Condition,...]
    action: Action
    sources: tuple[SourceReference,...]
    metadata: Metadata
    effective_from: date | None = None
    effective_to: date | None = None
    def __post_init__(self):
        super().__post_init__();nonempty(self.rule_id,"rule_id");nonempty(self.title,"title")
        require(self.version>0,"Version must be positive")
        require(bool(self.conditions),"Rule requires conditions");require(bool(self.sources),"Rule requires source evidence")
        require(len(set(self.conditions))==len(self.conditions),"Duplicate conditions")
        require(self.effective_to is None or self.effective_from is not None,"effective_to requires effective_from")
        if self.effective_to is not None: require(self.effective_to>=self.effective_from,"Invalid effective interval")
