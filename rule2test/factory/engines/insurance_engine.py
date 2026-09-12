"""Independent mock application with deployed policy configuration, not an oracle."""
from dataclasses import dataclass
from decimal import Decimal, localcontext
from factory.models import Action, Outcome, Value, ValueKind
from factory.exceptions import ConfigurationError

def legacy_mock_sut(rule,value,fault="none"):
    if fault not in ("none","stale","boundary"): raise ValueError("Unknown fault mode")
    if isinstance(value,bool) or not isinstance(value,int): return "INVALID"
    limits={"age":120,"claim_amount":1000000000}
    if value<0 or value>limits[rule["field"]]: return "INVALID"
    threshold=rule["threshold"]
    if fault=="stale": threshold-=5 if rule["field"]=="age" else 50000000
    if fault=="boundary": return "REVIEW" if value>=threshold else "ALLOW"
    return "REVIEW" if value>threshold else "ALLOW"

@dataclass(frozen=True,kw_only=True)
class InsuranceEngine:
    """One endpoint/product behavior per instance; configuration models deployed code."""
    profile: str
    min_age: int = 18
    max_age: int = 65
    claim_threshold: Decimal = Decimal("150000000")
    deductible: Decimal = Decimal("10000000")
    currency: str = "VND"
    fault: str = "none"

    def __post_init__(self):
        if self.profile not in ("eligibility","claim_review","deductible"): raise ConfigurationError("Unsupported mock profile")
        if self.fault not in ("none","boundary","stale","deductible_off_by_one"): raise ConfigurationError("Unsupported fault")
        if type(self.min_age) is not int or type(self.max_age) is not int or not 0<=self.min_age<=self.max_age<=120: raise ConfigurationError("Invalid mock age range")
        for number in (self.claim_threshold,self.deductible):
            if type(number) is not Decimal or not number.is_finite() or not 0<=number<=1000000000 or number.as_tuple().exponent < -12:
                raise ConfigurationError("Invalid mock money configuration")
        if type(self.currency) is not str or len(self.currency)!=3 or not self.currency.isascii() or not self.currency.isalpha() or not self.currency.isupper():
            raise ConfigurationError("Invalid currency")

    def decide(self,inputs):
        # Deliberately independent from oracle validators and condition evaluator.
        values={}
        for entry in inputs:
            if entry.field in values or entry.field not in ("age","claim_amount"): return Action(outcome=Outcome.INVALID)
            values[entry.field]=entry.value
        for name,value in values.items():
            if name=="age":
                if value.kind is not ValueKind.INTEGER or not 0<=value.data<=120: return Action(outcome=Outcome.INVALID)
            else:
                if value.kind is not ValueKind.MONEY or value.currency!=self.currency: return Action(outcome=Outcome.INVALID)
                if value.data<0 or value.data>1000000000 or value.data.as_tuple().exponent < -12: return Action(outcome=Outcome.INVALID)
        if self.profile=="eligibility":
            age=values.get("age")
            if age is None: return Action(outcome=Outcome.INVALID)
            top=self.max_age-5 if self.fault=="stale" else self.max_age
            eligible=self.min_age<=age.data<top if self.fault=="boundary" else self.min_age<=age.data<=top
            return Action(outcome=Outcome.ALLOW if eligible else Outcome.DENY)
        claim=values.get("claim_amount")
        if claim is None: return Action(outcome=Outcome.INVALID)
        if self.profile=="claim_review":
            cutoff=self.claim_threshold-Decimal("50000000") if self.fault=="stale" else self.claim_threshold
            review=claim.data>=cutoff if self.fault=="boundary" else claim.data>cutoff
            return Action(outcome=Outcome.REVIEW if review else Outcome.ALLOW)
        with localcontext() as ctx:
            ctx.prec=64
            retained=self.deductible
            if self.fault=="stale": retained=retained-Decimal("5000000")
            paid=Decimal(0)
            if claim.data>retained: paid=claim.data-retained
            if self.fault=="deductible_off_by_one" and claim.data==retained: paid=Decimal(1)
        return Action(outcome=Outcome.PAYOUT,amount=Value(kind=ValueKind.MONEY,data=paid,currency=self.currency))
