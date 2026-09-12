"""Explicit, bounded boundary/exception/branch obligations with unresolved reporting."""
from decimal import Decimal,localcontext
from factory.models import Value,ValueKind,HitPolicy,content_hash
from factory.models.analysis import Obligation,GapAnalysis
from ._support import SearchContext,stable_id,inputs_key,numeric,unique_tests

class GapService:
    def __init__(self,*,money_step=Decimal("1"),max_combinations=4096):
        self.money_step=money_step;self.max_combinations=max_combinations

    def analyze(self,table,rules,tests=(),*,as_of=None):
        unique_tests(tests)
        ctx=SearchContext(table,rules,as_of=as_of,money_step=self.money_step,max_combinations=self.max_combinations)
        obligations=[]
        def add(category,rule_id,row_id,label,witness):
            identifier=stable_id("OBL-",[content_hash(table),str(as_of),str(self.money_step),category,row_id,label])
            obligations.append(Obligation(obligation_id=identifier,category=category,rule_id=rule_id,row_id=row_id,
                label=label,inputs=witness,unresolved_reason=None if witness is not None else "No unmasked witness found within the bounded search; not proof of unreachability"))
        def first(predicate):
            return next((p for p in ctx.probes if predicate(p)),None)

        for row in ctx.active:
            rid=row.rule.rule_id
            baseline=first(lambda p: (trace:=ctx.trace(p)) is not None and row.row_id in trace.matched_row_ids)
            add("branch",rid,row.row_id,"row selected",baseline)
            for index,condition in enumerate(row.conditions):
                if condition.value.kind not in (ValueKind.INTEGER,ValueKind.MONEY):continue
                step=1 if condition.field=="age" else self.money_step
                for label,offset in (("below",-1),("at",0),("above",1)):
                    with localcontext() as lc:
                        lc.prec=64
                        value=numeric(condition.field,condition.value.data+offset*step,ctx.currency)
                    def isolates(probe):
                        values={i.field:i.value for i in probe}
                        if not all(ctx.oracle._matches(c,values[c.field]) for j,c in enumerate(row.conditions) if j!=index):return False
                        changed=ctx.replace_input(probe,condition.field,value)
                        trace=ctx.trace(changed)
                        if trace is None:return False
                        updated={i.field:i.value for i in changed}
                        # Other conditions must remain true after replacing a shared-field input.
                        if not all(ctx.oracle._matches(c,updated[c.field]) for j,c in enumerate(row.conditions) if j!=index):return False
                        target_true=ctx.oracle._matches(condition,value)
                        if target_true:return row.row_id in trace.matched_row_ids
                        if ctx.table.hit_policy is HitPolicy.FIRST and trace.matched_row_ids:
                            order={r.row_id:i for i,r in enumerate(ctx.table.rows)}
                            if order[trace.matched_row_ids[0]]<order[row.row_id]:return False
                        return True
                    probe=first(isolates)
                    witness=ctx.replace_input(probe,condition.field,value) if probe is not None else None
                    add("boundary",rid,row.row_id,f"condition {index}: {condition.field} {label} {condition.value.data}",witness)
            for field in sorted({c.field for c in row.conditions} | ({row.action.formula.field} if row.action.formula else set())):
                maximum=120 if field=="age" else 1000000000
                step=1 if field=="age" else self.money_step
                values=[("null",Value(kind=ValueKind.NULL)),("missing",Value(kind=ValueKind.MISSING)),
                        ("negative",numeric(field,-step,ctx.currency)),("overflow",numeric(field,maximum+step,ctx.currency)),
                        ("wrong_type",Value(kind=ValueKind.TEXT,data="invalid"))]
                if field=="claim_amount":
                    values.append(("wrong_currency",Value(kind=ValueKind.MONEY,data=Decimal(1),currency="USD" if ctx.currency!="USD" else "VND")))
                for label,value in values:
                    witness=ctx.replace_input(baseline,field,value) if baseline is not None else None
                    if witness is not None and ctx.trace(witness) is None:witness=None
                    add("exception",rid,row.row_id,field+": "+label,witness)
            if row.action.formula is not None:
                formula=row.action.formula
                for label,offset in (("below",-1),("at",0),("above",1)):
                    with localcontext() as lc:
                        lc.prec=64
                        value=numeric(formula.field,formula.deductible.data+offset*self.money_step,ctx.currency)
                    witness=None
                    for probe in ctx.probes:
                        candidate=ctx.replace_input(probe,formula.field,value)
                        trace=ctx.trace(candidate)
                        if trace is not None and row.row_id in trace.matched_row_ids:
                            witness=candidate;break
                    add("boundary",rid,row.row_id,"deductible "+label,witness)
        # Default formulas need their own boundary obligations even without a matching rule row.
        if table.default_action.formula:
            formula=table.default_action.formula
            for label,offset in (("below",-1),("at",0),("above",1)):
                with localcontext() as lc:
                    lc.prec=64
                    value=numeric(formula.field,formula.deductible.data+offset*self.money_step,ctx.currency)
                witness=None
                for probe in ctx.probes:
                    candidate=ctx.replace_input(probe,formula.field,value);trace=ctx.trace(candidate)
                    if trace is not None and trace.default_used and trace.action.formula is None:
                        witness=candidate;break
                add("boundary",None,None,"default deductible "+label,witness)
        default=first(lambda p:(trace:=ctx.trace(p)) is not None and trace.default_used)
        add("branch",None,None,"default selected",default)
        covered=self.covered(ctx,tuple(obligations),tests)
        return GapAnalysis(evaluation_date=as_of,money_step=self.money_step,table_hash=content_hash(table),obligations=tuple(obligations),covered_ids=covered,
            missing_ids=tuple(o.obligation_id for o in obligations if o.obligation_id not in covered),
            unresolved_ids=tuple(o.obligation_id for o in obligations if o.inputs is None),search_size=ctx.search_size)

    @staticmethod
    def covered(ctx,obligations,tests):
        eligible=[t for t in tests if ctx.related(t)]
        covered=[]
        for obligation in obligations:
            if obligation.inputs is None:continue
            for test in eligible:
                trace=ctx.trace(test.inputs)
                if trace is None:continue
                if obligation.category=="branch":
                    hit=(obligation.row_id in trace.matched_row_ids) if obligation.row_id else trace.default_used
                else:hit=inputs_key(test.inputs)==inputs_key(obligation.inputs)
                if hit:
                    covered.append(obligation.obligation_id);break
        return tuple(covered)
