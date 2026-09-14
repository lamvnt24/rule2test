"""Deterministic reading of Vietnamese, English and Japanese business phrases. Not a language model.

Matching happens on a folded copy of the text (lower case, diacritics removed, đ→d) so that
"Tuổi", "tuoi" and "TUỔI" read the same; anything quoted back to a person is always the original.
"""
import re,unicodedata
from decimal import Decimal,InvalidOperation
from factory.models import Value,ValueKind

def normalize(text):
    return unicodedata.normalize("NFC",str(text or ""))

def fold(text):
    """Length-preserving: folded[i] always comes from text[i], so a match span can quote the original."""
    result=[]
    for ch in normalize(text):
        if ch in ("đ","Đ"):result.append("d");continue
        decomposed=unicodedata.normalize("NFD",ch)
        base=decomposed[0] if decomposed and not unicodedata.combining(decomposed[0]) else " "
        lowered=base.lower()
        result.append(lowered if len(lowered)==1 else base)
    return "".join(result)

NUMBER=r"(?:\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)"
MULTIPLIERS={"nghin":1000,"ngan":1000,"thousand":1000,"k":1000,"trieu":10**6,"tr":10**6,"million":10**6,"mn":10**6,"m":10**6,
             "ty":10**9,"billion":10**9,"bn":10**9,"b":10**9}
CURRENCIES={"vnd":"VND","vnđ":"VND","dong":"VND","d":"VND","usd":"USD","jpy":"JPY","yen":"JPY","円":"JPY","eur":"EUR"}
MONEY=re.compile(r"(?<![A-Za-z0-9.,])(?P<number>"+NUMBER+r")\s*(?P<mult>trieu|tr|million|mn|m|ty|billion|bn|b|nghin|ngan|thousand|k)?(?![a-z])"
                 r"\s*(?:(?P<cur>vnd|vnđ|dong|usd|jpy|yen|eur|円|d)(?![a-z]))?")

def parse_number(text):
    """'100.000.000' and '100,000,000' are grouped integers; '1,5' and '1.5' are decimals."""
    text=text.strip()
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+",text):return Decimal(re.sub(r"[.,]","",text))
    try:return Decimal(text.replace(",","."))
    except InvalidOperation as exc:raise ValueError("Unreadable number: "+text) from exc

def find_money(folded):
    """Every amount in a folded text as (Decimal, currency or None, matched text), in order."""
    found=[]
    for match in MONEY.finditer(folded):
        amount=parse_number(match.group("number"))
        if match.group("mult"):amount=amount*MULTIPLIERS[match.group("mult")]
        # 1,5 tỷ is 1500000000, not 1500000000.0: keep integral amounts integral.
        amount=amount.quantize(Decimal(1)) if amount==amount.to_integral_value() else amount.normalize()
        currency=CURRENCIES.get(match.group("cur")) if match.group("cur") else None
        found.append((amount,currency,match.group(0).strip(),match.start(),match.end()))
    return found

def money_value(amount,currency):
    return Value(kind=ValueKind.MONEY,data=amount,currency=currency)

def integer_value(number):
    return Value(kind=ValueKind.INTEGER,data=int(number))

def grouped(number):
    """Thousands separators for people: 150000000 -> 150,000,000."""
    text=format(number,"f") if isinstance(number,Decimal) else str(number)
    if "." in text:text=text.rstrip("0").rstrip(".")
    sign="-" if text.startswith("-") else "";text=text.lstrip("-")
    whole,_,fraction=text.partition(".")
    whole=re.sub(r"\B(?=(\d{3})+(?!\d))",",",whole)
    return sign+whole+("."+fraction if fraction else "")

def fmt_value(value):
    if value is None:return "—"
    if value.kind is ValueKind.INTEGER:return str(value.data)
    if value.kind is ValueKind.MONEY:return grouped(value.data)+" "+value.currency
    if value.kind is ValueKind.DATE:return value.data.isoformat()
    if value.kind is ValueKind.BOOLEAN:return "yes" if value.data else "no"
    if value.kind is ValueKind.TEXT:return "text "+repr(value.data)
    if value.kind is ValueKind.NULL:return "empty"
    return "missing"

FIELD_NAMES={"age":"Age","claim_amount":"Claim amount"}
OPERATORS={"eq":"=","ne":"≠","lt":"<","le":"≤","gt":">","ge":"≥","is_null":"is empty","is_missing":"is missing"}

def field_name(field):return FIELD_NAMES.get(field,field)

def fmt_inputs(inputs):
    return ", ".join(field_name(x.field)+" = "+fmt_value(x.value) for x in inputs) or "—"

def fmt_action(action):
    if action is None:return "—"
    outcome=action.outcome.value.upper()
    if action.formula:return outcome+" = "+field_name(action.formula.field)+" − "+fmt_value(action.formula.deductible)+", minimum 0"
    if action.amount:return outcome+" "+fmt_value(action.amount)
    return outcome

def fmt_condition(condition):
    operator=OPERATORS[condition.operator.value]
    if condition.operator.value in ("is_null","is_missing"):return field_name(condition.field)+" "+operator
    return field_name(condition.field)+" "+operator+" "+fmt_value(condition.value)

def fmt_rule(rule):
    if rule is None:return "—"
    return "If "+(" and ".join(fmt_condition(c) for c in rule.conditions) or "any input")+" → "+fmt_action(rule.action)
