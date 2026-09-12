"""Specification mutation analysis, not mutation of a deployed application's code."""
from dataclasses import replace
from decimal import Decimal,localcontext
from factory.models import Operator,Action,Outcome,RuleReference,content_hash
from factory.models.analysis import MutationResult,MutationReport,MutationStatus
from factory.models.common import require
from factory.exceptions import ValidationError,ConflictError
from factory.engines.oracle_engine import OracleEngine
from ._support import stable_id,references,unique_tests
from factory.validators.rule_validator import validate_table

class MutationService:
    def __init__(self,*,money_step=Decimal("1"),max_mutants=200):
        require(type(money_step) is Decimal and money_step.is_finite() and 0<money_step<=1000000000 and money_step.as_tuple().exponent>=-12,"Invalid mutation step")
        require(type(max_mutants) is int and 0<max_mutants<=1000,"Invalid mutation budget")
        self.money_step=money_step;self.max_mutants=max_mutants

    def analyze(self,table,rules,tests,*,as_of=None,previous_rules=()):
        unique_tests(tests);validate_table(table,rules,as_of)
        oracle=OracleEngine()
        for test in tests:
            require(set(test.rules)==set(references(rules)),"Mutation tests must reference current rules")
            require(test.expected==oracle.evaluate(table,rules,test.inputs,as_of=as_of),"Mutation tests have stale expected results")
        specs=[]
        flip={Operator.LE:Operator.LT,Operator.LT:Operator.LE,Operator.GE:Operator.GT,
              Operator.GT:Operator.GE,Operator.EQ:Operator.NE,Operator.NE:Operator.EQ}
        def add(rule,description,change):
            specs.append((rule,description,change))
            require(len(specs)<=self.max_mutants,"Mutation budget exceeded; narrow the table or raise max_mutants")
        for rule in sorted(rules,key=lambda r:r.rule_id):
            if rule.effective_from is not None and as_of<rule.effective_from:continue
            if rule.effective_to is not None and as_of>rule.effective_to:continue
            for i,condition in enumerate(rule.conditions):
                if condition.operator in flip:
                    def change(r,i=i,c=condition):
                        return replace(r,conditions=tuple(replace(x,operator=flip[c.operator]) if j==i else x for j,x in enumerate(r.conditions)))
                    add(rule,f"condition {i}: comparator {condition.operator.value} -> {flip[condition.operator].value}",change)
                if condition.field in ("age","claim_amount") and condition.value.data is not None and condition.operator in flip:
                    step=1 if condition.field=="age" else self.money_step
                    for direction in (-1,1):
                        def shift(r,i=i,c=condition,d=direction,step=step):
                            with localcontext() as ctx:
                                ctx.prec=64
                                value=replace(c.value,data=c.value.data+d*step)
                            return replace(r,conditions=tuple(replace(x,value=value) if j==i else x for j,x in enumerate(r.conditions)))
                        add(rule,f"condition {i}: threshold shift {direction} step",shift)
            if rule.action.formula:
                for direction in (-1,1):
                    def deductible(r,d=direction):
                        with localcontext() as ctx:
                            ctx.prec=64
                            value=replace(r.action.formula.deductible,data=r.action.formula.deductible.data+d*self.money_step)
                        return replace(r,action=replace(r.action,formula=replace(r.action.formula,deductible=value)))
                    add(rule,f"deductible shift {direction} step",deductible)
        old={r.rule_id:r for r in previous_rules}
        require(len(old)==len(previous_rules),"Duplicate previous rule ID")
        for rule in rules:
            if rule.rule_id in old and (old[rule.rule_id].conditions!=rule.conditions or old[rule.rule_id].action!=rule.action):
                add(rule,"restore previous conditions/action",lambda r:replace(r,conditions=old[r.rule_id].conditions,action=old[r.rule_id].action))
        # An untested default branch must not disappear from the mutation score.
        add(None,"change default outcome",lambda _:None)
        results=[]
        for original,description,change in specs:
            identifier=stable_id("MUT-",[content_hash(table),original.rule_id if original else None,description,str(self.money_step)])
            witnesses=[];reason=None
            try:
                if original:
                    mutated=change(original)
                    mutated_rules=tuple(mutated if r.rule_id==original.rule_id else r for r in rules)
                    ref=RuleReference(rule_id=mutated.rule_id,version=mutated.version,rule_hash=content_hash(mutated))
                    rows=tuple(replace(row,rule=ref,conditions=mutated.conditions,action=mutated.action) if row.rule.rule_id==original.rule_id else row for row in table.rows)
                    mutated_table=replace(table,rows=rows)
                else:
                    mutated_rules=rules
                    outcome=Outcome.DENY if table.default_action.outcome is Outcome.ALLOW else Outcome.ALLOW
                    mutated_table=replace(table,default_action=Action(outcome=outcome))
                validate_table(mutated_table,mutated_rules,as_of)
                for test in tests:
                    actual=oracle.evaluate(mutated_table,mutated_rules,test.inputs,as_of=as_of)
                    if actual!=test.expected:witnesses.append(test.test_id+"@"+str(test.revision))
                status=MutationStatus.KILLED if witnesses else MutationStatus.SURVIVED
            except (ValidationError,ConflictError) as exc:
                status=MutationStatus.INVALID;reason=str(exc);witnesses=[]
            results.append(MutationResult(mutation_id=identifier,rule_id=original.rule_id if original else None,
                description=description,status=status,witnesses=tuple(sorted(witnesses)),reason=reason))
        return MutationReport(results=tuple(results),test_count=len(tests))
