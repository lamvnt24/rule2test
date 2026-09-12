"""Compile located table rows into validated domain models without AI inference."""
from datetime import date,datetime
from decimal import Decimal
import re
from factory.models import *
from factory.models.rule import PayoutFormula
from factory.models.common import require
from factory.validators.rule_validator import validate_table,validate_money
from factory.services.rule_delta_service import RuleDeltaService
from factory.validators.test_validator import input_map
from .common import ImportFailure,ImportBundle,strict_json

def text(value):
    require(type(value) is str and bool(value.strip()),"Expected non-empty text")
    return value.strip()

def integer(value):
    require(type(value) in (str,int) and re.fullmatch(r"[+-]?[0-9]+",str(value).strip()) is not None,"Expected integer, not boolean/fraction/date")
    return int(value)

def decimal(value):
    require(type(value) in (str,int,Decimal),"Store fractional money as text to preserve decimal precision")
    require(re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?",str(value).strip()) is not None,"Expected plain decimal without separators or exponent")
    number=Decimal(str(value).strip())
    require(number.is_finite(),"Money must be finite")
    return number

def optional_date(value):
    if value in (None,""):return None
    if type(value) is datetime:
        require(value.time()==datetime.min.time(),"Date must not contain a time")
        return value.date()
    if type(value) is date:return value
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}",value) is not None,"Expected ISO YYYY-MM-DD or an Excel date cell")
    return date.fromisoformat(value)

def money(number,currency):
    return Value(kind=ValueKind.MONEY,data=decimal(number),currency=text(currency))

def operand(kind,number,currency):
    kind=ValueKind(text(kind))
    if kind is ValueKind.INTEGER:return Value(kind=kind,data=integer(number))
    if kind is ValueKind.MONEY:return money(number,currency)
    if kind in (ValueKind.NULL,ValueKind.MISSING):
        require(number in (None,""),"Null/missing value must be blank")
        return Value(kind=kind)
    if kind is ValueKind.TEXT:
        require(type(number) is str,"Text input requires a string")
        return Value(kind=kind,data=number)
    if kind is ValueKind.BOOLEAN:
        require(type(number) is bool,"Boolean input requires true/false")
        return Value(kind=kind,data=number)
    raise ValueError("Unsupported import value kind")

def action(outcome,amount,deductible,currency):
    outcome=Outcome(text(outcome))
    if outcome is not Outcome.PAYOUT:
        require(amount in (None,"") and deductible in (None,""),"Non-payout action cannot contain payout amounts")
        return Action(outcome=outcome)
    fixed=money(amount,currency) if amount not in (None,"") else None
    formula=PayoutFormula(field="claim_amount",deductible=money(deductible,currency)) if deductible not in (None,"") else None
    return Action(outcome=outcome,amount=fixed,formula=formula)

def standalone_action(outcome,amount,deductible,currency):
    if outcome!="payout":require(currency in (None,""),"Currency only applies to a payout action")
    return action(outcome,amount,deductible,currency)

def compile_document(doc,manifest,tables):
    issues=[]
    def attempt(fn):
        try:return fn()
        except ImportFailure as exc:issues.extend(exc.issues);return None
    schema=manifest.read("schema_version",integer)
    require(schema==1,"Unsupported import schema version")
    meta=manifest.read("created_at",lambda v:Metadata(created_at=datetime.fromisoformat(text(v)),created_by=manifest.read("created_by",text)))
    policies={}
    for row in tables["Policies"]:
        def parse_policy(row=row):
            label=row.read("label",text)
            if label not in ("v1","v2") or label in policies:raise ImportFailure((row.issue("label","Expected unique v1 or v2 policy"),))
            policies[label]=(row,row.read("table_id",text),row.read("version",integer),row.read("hit_policy",lambda x:HitPolicy(text(x))),
                row.read("default_outcome",lambda v:standalone_action(v,row.values.get("default_amount"),row.values.get("default_deductible"),row.values.get("currency"))),
                row.read("as_of",optional_date))
        attempt(parse_policy)
    for label in ("v1","v2"):
        if label not in policies:issues.append(manifest.issue("schema_version","Missing policy "+label))
    def parse_rules(sheet):
        groups={}
        for row in tables[sheet]:
            def parse(row=row):
                rid=row.read("rule_id",text)
                condition=row.read("value",lambda value:Condition(field=row.read("field",text),operator=row.read("operator",lambda v:Operator(text(v))),
                    value=operand(row.values.get("value_type"),value,row.values.get("currency"))))
                if condition.value.kind is ValueKind.MONEY:row.read("value",lambda _:validate_money(condition.value))
                version=row.read("version",integer);title=row.read("title",text)
                output=row.read("outcome",lambda v:action(v,row.values.get("payout_amount"),row.values.get("deductible"),row.values.get("currency")))
                if condition.value.kind is not ValueKind.MONEY and output.outcome is not Outcome.PAYOUT:
                    row.read("currency",lambda v:require(v in (None,""),"Currency is unused by this rule"))
                start=row.read("effective_from",optional_date);end=row.read("effective_to",optional_date)
                quote=row.read("quote",lambda v:(text(v),v)[1])
                metadata=(version,title,output,start,end)
                if rid not in groups:groups[rid]=[metadata,[],[],row]
                elif groups[rid][0]!=metadata:raise ImportFailure((row.issue("rule_id","Rows of one rule must repeat identical version/title/action/effective dates"),))
                if condition in groups[rid][1]:raise ImportFailure((row.issue("field","Duplicate condition in rule"),))
                groups[rid][1].append(condition);groups[rid][2].append(row.source(quote))
            attempt(parse)
        rules=[]
        for rid,(values,conditions,sources,row) in groups.items():
            def build(row=row,rid=rid,values=values,conditions=conditions,sources=sources):
                version,title,output,start,end=values
                rule=row.read("rule_id",lambda _:Rule(rule_id=rid,version=version,title=title,conditions=tuple(conditions),action=output,
                    sources=tuple(sources),metadata=meta,effective_from=start,effective_to=end))
                rules.append(rule)
            attempt(build)
        return tuple(rules)
    old_rules=parse_rules("RulesV1");new_rules=parse_rules("RulesV2")
    compiled={}
    for label,rules in (("v1",old_rules),("v2",new_rules)):
        if label not in policies:continue
        row,tid,version,policy,default,as_of=policies[label]
        def build_table(row=row,tid=tid,version=version,policy=policy,default=default,as_of=as_of,rules=rules,label=label):
            entries=tuple(DecisionRow(row_id=r.rule_id,conditions=r.conditions,action=r.action,
                rule=RuleReference(rule_id=r.rule_id,version=r.version,rule_hash=content_hash(r))) for r in rules)
            table=row.read("table_id",lambda _:DecisionTable(table_id=tid,version=version,hit_policy=policy,rows=entries,default_action=default))
            row.read("table_id",lambda _:validate_table(table,rules,as_of))
            compiled[label]=(table,as_of)
        attempt(build_table)
    tests=[];test_ids=set();lookup={r.rule_id:r for r in old_rules}
    for row in tables["Tests"]:
        def parse_test(row=row):
            tid=row.read("test_id",text)
            if tid in test_ids:raise ImportFailure((row.issue("test_id","Duplicate test ID"),))
            test_ids.add(tid)
            def parse_inputs(value):
                data=strict_json(value) if type(value) is str else value
                require(type(data) is list and bool(data),"inputs_json must be a non-empty JSON array")
                result=[]
                for entry in data:
                    require(type(entry) is dict and set(entry)=={"field","kind","value","currency"},"Input requires field, kind, value, currency")
                    if entry["kind"]!="money":require(entry["currency"] in (None,""),"Non-money input cannot contain currency")
                    result.append(TestInput(field=text(entry["field"]),value=operand(entry["kind"],entry["value"],entry["currency"])))
                input_map(tuple(result))
                return tuple(result)
            inputs=row.read("inputs_json",parse_inputs)
            refs=row.read("rule_ids",lambda v:tuple(text(x) for x in text(v).split(",")))
            if not set(refs)<=set(lookup):raise ImportFailure((row.issue("rule_ids","Unknown V1 rule reference"),))
            rule_refs=tuple(RuleReference(rule_id=key,version=lookup[key].version,rule_hash=content_hash(lookup[key])) for key in refs)
            expected=row.read("expected_outcome",lambda v:standalone_action(v,row.values.get("expected_amount"),None,row.values.get("currency")))
            source_quote=row.values["inputs_json"]
            if type(source_quote) is not str:
                import json
                source_quote=json.dumps(source_quote,ensure_ascii=False,default=str)
            test=row.read("test_id",lambda _:TestCase(test_id=tid,revision=row.read("revision",integer),title=row.read("title",text),
                inputs=inputs,expected=expected,kind=row.read("kind",lambda v:TestKind(text(v))),origin=TestOrigin.EXISTING,
                rules=rule_refs,rationale=row.read("rationale",text),metadata=meta,sources=(row.source(source_quote,"inputs_json"),)))
            tests.append(test)
        attempt(parse_test)
    if not issues and len(compiled)==2:
        attempt(lambda:manifest.read("schema_version",lambda _:RuleDeltaService().compare(old_rules,new_rules)))
        if compiled["v1"][0].table_id==compiled["v2"][0].table_id and compiled["v1"][0]!=compiled["v2"][0] and compiled["v2"][0].version<=compiled["v1"][0].version:
            issues.append(policies["v2"][0].issue("version","Changed table snapshot must increase its version"))
    if issues:raise ImportFailure(issues[:100])
    return ImportBundle(doc,compiled["v1"][0],old_rules,compiled["v2"][0],new_rules,tuple(tests),compiled["v1"][1],compiled["v2"][1])
