"""Shared canonicalization and bounded witness search, not an AI provider."""
import hashlib
import itertools
import json
from decimal import Decimal, localcontext
from factory.models import Value, ValueKind, TestInput, RuleReference, content_hash
from factory.models.common import require
from factory.validators.rule_validator import validate_table
from factory.validators.test_validator import input_map
from factory.engines.oracle_engine import OracleEngine
from factory.exceptions import ConflictError, ValidationError

def stable_id(prefix, value):
    return prefix+hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()[:20]

def value_key(value):
    data=value.data
    if value.kind is ValueKind.MONEY:
        with localcontext() as ctx:
            ctx.prec=64
            data=format(data.normalize(),"f")
    elif hasattr(data,"isoformat"): data=data.isoformat()
    return (value.kind.value,data,value.currency)

def inputs_key(inputs):
    # Explicit MISSING and omitted input represent the same request semantics.
    return tuple(sorted((x.field,value_key(x.value)) for x in inputs if x.value.kind is not ValueKind.MISSING))

def unique_tests(tests):
    require(type(tests) is tuple,"Expected test tuple")
    require(len({(t.test_id,t.revision) for t in tests})==len(tests),"Duplicate test revision")
    return tests

def references(rules):
    return tuple(RuleReference(rule_id=r.rule_id,version=r.version,rule_hash=content_hash(r)) for r in sorted(rules,key=lambda r:r.rule_id))

def numeric(field, number, currency):
    if field=="age": return Value(kind=ValueKind.INTEGER,data=int(number))
    return Value(kind=ValueKind.MONEY,data=Decimal(number),currency=currency or "VND")

class SearchContext:
    def __init__(self,table,rules,*,as_of=None,money_step=Decimal("1"),max_combinations=4096):
        self.table=table;self.rules=rules;self.as_of=as_of;self.oracle=OracleEngine()
        lookup,self.currency=validate_table(table,rules,as_of)
        require(type(money_step) is Decimal and money_step.is_finite() and 0<money_step<=1000000000 and money_step.as_tuple().exponent>=-12,"Invalid money step")
        require(type(max_combinations) is int and 0<max_combinations<=100000,"Invalid search budget")
        require(len({r.rule_id for r in rules})==len(rules),"One version per rule ID is required for analysis")
        self.money_step=money_step;self.cache={}
        self.active=tuple(row for row in table.rows if self.is_active(lookup[(row.rule.rule_id,row.rule.version)]))
        fields={c.field for row in self.active for c in row.conditions}
        actions=[table.default_action]+[r.action for r in self.active]
        fields.update(a.formula.field for a in actions if a.formula)
        self.fields=tuple(sorted(fields))
        require(bool(self.active),"No active rule rows at the evaluation date; select an applicable version")
        self.pools={}
        for field in self.fields:
            numbers={0,120} if field=="age" else {Decimal(0),Decimal(1000000000)}
            step=1 if field=="age" else money_step
            thresholds=[c.value.data for row in self.active for c in row.conditions if c.field==field and c.value.kind in (ValueKind.INTEGER,ValueKind.MONEY)]
            thresholds += [a.formula.deductible.data for a in actions if a.formula and a.formula.field==field]
            with localcontext() as ctx:
                ctx.prec=64
                for threshold in thresholds: numbers.update((threshold-step,threshold,threshold+step))
            maximum=120 if field=="age" else 1000000000
            vals=[numeric(field,n,self.currency) for n in sorted(numbers) if 0<=n<=maximum]
            # Also search explicit null/missing rows, without mistaking them for invalid matches.
            vals += [Value(kind=ValueKind.NULL),Value(kind=ValueKind.MISSING)]
            self.pools[field]=vals
        size=1
        for values in self.pools.values():size*=len(values)
        require(size<=max_combinations,"Witness search budget exceeded; narrow the table or raise max_combinations")
        self.search_size=size
        self.probes=tuple(tuple(TestInput(field=field,value=value) for field,value in zip(self.fields,combo))
                          for combo in itertools.product(*(self.pools[field] for field in self.fields)))

    def is_active(self,rule):
        return not ((rule.effective_from is not None and self.as_of<rule.effective_from) or
                    (rule.effective_to is not None and self.as_of>rule.effective_to))

    def trace(self,inputs):
        key=inputs_key(inputs)
        if key not in self.cache:
            try:self.cache[key]=self.oracle.trace(self.table,self.rules,inputs,as_of=self.as_of)
            except (ConflictError,ValidationError): self.cache[key]=None
        return self.cache[key]

    def related(self,test):
        return bool({r.rule_id for r in test.rules}&{r.rule_id for r in self.rules})

    def replace_input(self,inputs,field,value):
        return tuple(TestInput(field=x.field,value=value if x.field==field else x.value) for x in inputs)
