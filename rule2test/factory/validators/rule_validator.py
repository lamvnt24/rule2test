"""Supported engine contract validation, separate from model shape validation."""
from datetime import date
from factory.models import Rule, DecisionTable, HitPolicy, ValueKind, content_hash
from factory.models.common import require
FIELDS={"age":(0,120),"claim_amount":(0,1000000000)}

def validate_legacy_rules(rules):
    require(type(rules) is list and 0<len(rules)<=50,"Expected 1..50 rules")
    ids=set()
    for r in rules:
        require(type(r) is dict and set(r)=={"id","field","threshold","source"},"Invalid legacy rule schema")
        require(type(r["id"]) is str and bool(r["id"].strip()) and r["id"] not in ids,"Duplicate or invalid rule ID")
        ids.add(r["id"])
        require(type(r["field"]) is str and r["field"] in FIELDS,"Unsupported field")
        lo,hi=FIELDS[r["field"]]
        require(type(r["threshold"]) is int and lo<r["threshold"]<hi,"Threshold outside supported domain")
        require(type(r["source"]) is str and bool(r["source"].strip()),"Source citation required")
    return rules

def validate_money(value):
    # A bounded precision contract permits exact arithmetic under localcontext(prec=64).
    require(value.kind is ValueKind.MONEY,"Expected money")
    require(0<=value.data<=1000000000,"Money outside 0..1 billion demo domain")
    require(value.data.as_tuple().exponent>=-12,"At most 12 fractional decimal places")
    return value

def validate_table(table, rules, as_of=None):
    require(type(table) is DecisionTable,"Expected DecisionTable")
    require(type(rules) is tuple and all(type(r) is Rule for r in rules),"Expected rule snapshots tuple")
    require(table.hit_policy in (HitPolicy.UNIQUE,HitPolicy.FIRST),"COLLECT unsupported: executor expects one action")
    require(as_of is None or type(as_of) is date,"as_of must be a date")
    lookup={(r.rule_id,r.version):r for r in rules}
    require(len(lookup)==len(rules),"Duplicate rule snapshot")
    refs={(row.rule.rule_id,row.rule.version) for row in table.rows}
    require(refs==set(lookup),"Table must reference exactly the supplied rule snapshots")
    kinds={}; currencies=set()
    for row in table.rows:
        rule=lookup[(row.rule.rule_id,row.rule.version)]
        require(content_hash(rule)==row.rule.rule_hash,"Rule hash mismatch")
        require(row.conditions==rule.conditions and row.action==rule.action,"Decision row differs from source rule")
        if rule.effective_from is not None:
            require(as_of is not None,"Effective rules require explicit as_of")
        for condition in row.conditions:
            require(condition.field in FIELDS,"Unsupported rule field: "+condition.field)
            if condition.value.kind not in (ValueKind.NULL,ValueKind.MISSING):
                kind=ValueKind.INTEGER if condition.field=="age" else ValueKind.MONEY
                require(condition.value.kind is kind,"Incorrect condition value kind")
                kinds[condition.field]=kind
                if kind is ValueKind.MONEY:
                    validate_money(condition.value);currencies.add(condition.value.currency)
    for action in [table.default_action]+[r.action for r in table.rows]:
        if action.amount is not None:
            validate_money(action.amount);currencies.add(action.amount.currency)
        if action.formula is not None:
            validate_money(action.formula.deductible);currencies.add(action.formula.deductible.currency)
            kinds["claim_amount"]=ValueKind.MONEY
    require(len(currencies)<=1,"Mixed currencies are unsupported; explicit conversion is required")
    return lookup, next(iter(currencies),None)
