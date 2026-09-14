"""Reads test-case cells written for people ("Tuổi: 61", "Bị từ chối") into typed inputs and outcomes.

Deterministic patterns only. Anything the patterns cannot read unambiguously is reported as a
question for the person importing the file, never guessed.
"""
import re
from decimal import Decimal
from factory.models import Value,ValueKind,TestInput,Action,Outcome
from .text_patterns import fold,normalize,find_money,money_value,integer_value,fmt_inputs,fmt_action

INTERPRETER="pattern-v1"

AGE=r"(?:do\s+tuoi|tuoi|ages?d?|年齢|年令)"
CLAIM=(r"(?:so\s+tien(?:\s+(?:yeu\s+cau|boi\s+thuong|claim|doi\s+boi\s+thuong|toi\s+thieu))?|yeu\s+cau\s+boi\s+thuong|gia\s+tri\s+(?:yeu\s+cau|boi\s+thuong)"
       r"|muc\s+(?:yeu\s+cau|boi\s+thuong)|boi\s+thuong|claim(?:[_\s]?amount)?|amount|請求金額|請求額|金額)")
EMPTY=r"(?:de\s+trong|bo\s+trong|trong|rong|null|none|empty|blank|空|なし)"
MISSING=r"(?:thieu|khong\s+co|khong\s+gui|khong\s+nhap|khong\s+truyen|bo\s+qua|missing|omitted|absent|not\s+(?:sent|provided|given|supplied)|未入力|欠落)"
QUOTED=re.compile(r"[\"'“”‘’]([^\"'“”‘’]+)[\"'“”‘’]")
NUMBER=r"(-?\d+)(?![.,]?\d)"

def _first(patterns,folded):
    for pattern in patterns:
        match=re.search(pattern,folded)
        if match:return match
    return None

def _special(word,folded,original):
    """Explicit empty/missing/text values, which are valid robustness inputs."""
    if _first((word+r"\s*[:=]?\s*[\(\[]?\s*"+EMPTY+r"(?![a-z])",EMPTY+r"\s+(?:truong\s+)?"+word),folded):
        return Value(kind=ValueKind.NULL),"empty"
    if _first((word+r"\s*[:=]?\s*[\(\[]?\s*"+MISSING+r"(?![a-z])",MISSING+r"\s+(?:truong\s+)?"+word),folded):
        return Value(kind=ValueKind.MISSING),"missing"
    quoted=re.search(word+r"\s*[:=]?\s*[\"'“”‘’]",folded)
    if quoted:
        text=QUOTED.search(original[quoted.start():])
        if text:return Value(kind=ValueKind.TEXT,data=text.group(1)),"text"
    return None

def read_inputs(text):
    """Typed inputs found in a cell, with one note per reading and one question per unreadable part."""
    original=normalize(text);folded=fold(original)
    inputs=[];notes=[];questions=[]
    def add(field,value,fragment):
        if any(x.field==field for x in inputs):return
        inputs.append(TestInput(field=field,value=value));notes.append("“"+fragment.strip()+"” → "+fmt_inputs(inputs[-1:]))
    special=_special(AGE,folded,original)
    if special:add("age",special[0],original)
    else:
        match=_first((AGE+r"\s*[:=]?\s*"+NUMBER,NUMBER+r"\s*(?:tuoi|歳|years?\s*old|yo|y/o)(?![a-z])",r"(?:aged|age\s+of)\s*"+NUMBER),folded)
        if match:add("age",integer_value(match.group(1)),original[match.start():match.end()])
        elif re.search(AGE+r"(?![a-z])",folded):questions.append("Could not read a number after the age wording in “"+original.strip()+"”.")
    special=_special(CLAIM,folded,original)
    if special:add("claim_amount",special[0],original)
    else:
        keyword=re.search(CLAIM+r"\s*[:=]?\s*",folded)
        amounts=find_money(folded)
        chosen=None
        if keyword:
            chosen=next((a for a in amounts if a[3]>=keyword.end()-1),None)
            if chosen is None:questions.append("Could not read an amount after the claim wording in “"+original.strip()+"”.")
        elif not inputs and len(amounts)==1 and amounts[0][1]:
            chosen=amounts[0];notes.append("No field name; the amount was read as the claim amount.")
        if chosen:
            amount,currency,_,start,end=chosen
            fragment=original[(keyword.start() if keyword else start):end]
            if currency is None:
                vietnamese=bool(re.search(r"(?:trieu|ty|nghin|ngan|tr)(?![a-z])",folded[start:end])) or bool(keyword and re.match(r"(?:so|yeu|gia|muc|boi)",keyword.group(0)))
                if vietnamese:currency="VND";notes.append("Currency not written; VND assumed.")
                else:questions.append("Currency missing for “"+fragment.strip()+"” (for example VND).")
            if currency:add("claim_amount",money_value(amount,currency),fragment)
    return tuple(inputs),tuple(notes),tuple(questions)

INVALID=r"(?:khong\s+hop\s+le|invalid|\bloi\b|error|bao\s+loi|validation|bad\s+request|無効|エラー)"
DENY=(r"(?:bi\s+tu\s+choi|tu\s+choi|khong\s+duoc\s+(?:tham\s+gia|chap\s+nhan|duyet|phe\s+duyet|bao\s+hiem|mua)|khong\s+du\s+dieu\s+kien|khong\s+dat"
      r"|khong\s+chap\s+nhan|deny|denied|reject|declin|not\s+eligible|ineligible|not\s+allowed|disallow|refus|拒否|不可)")
REVIEW=r"(?:xem\s+xet|kiem\s+tra\s+thu\s+cong|duyet\s+thu\s+cong|tham\s+dinh|cho\s+duyet|review|manual|escalat|審査|要確認)"
PAYOUT=r"(?:chi\s+tra|thanh\s+toan|boi\s+thuong|tra\s+tien|payout|pay(?:s|ed|ment)?(?![a-z])|paid|支払)"
ALLOW=(r"(?:duoc\s+chap\s+nhan|chap\s+nhan|duoc\s+tham\s+gia|duoc\s+duyet|duoc\s+phe\s+duyet|phe\s+duyet|du\s+dieu\s+kien|dong\s+y|cho\s+phep|hop\s+le|\bdat\b|thanh\s+cong"
       r"|accept|allow|approv|eligible|permit|success|\bpass(?:ed)?\b|\bok\b|許可|承認|合格|有効)")
ORDER=(("invalid",INVALID),("deny",DENY),("review",REVIEW),("payout",PAYOUT),("allow",ALLOW))

def read_expected(text):
    """One Action, or None with a question. The first category wins; a second, non-overlapping one is a question."""
    original=normalize(text);folded=fold(original)
    if not folded.strip():return None,"The expected result is blank."
    matches=[(name,m) for name,pattern in ORDER for m in [re.search(pattern,folded)] if m]
    if not matches:return None,"Could not read an outcome from “"+original.strip()+"”. Use accepted / rejected / review / invalid / payout <amount>."
    name,match=matches[0]
    others=[(n,m) for n,m in matches[1:] if m.end()<=match.start() or m.start()>=match.end()]
    if others:return None,"“"+original.strip()+"” reads as both "+name.upper()+" and "+others[0][0].upper()+"; state one outcome."
    if name=="payout":
        amounts=[a for a in find_money(folded) if a[3]>=match.end()-1] or find_money(folded)
        if not amounts:return None,"“"+original.strip()+"” mentions a payout but no amount."
        amount,currency,_,_,_=amounts[0]
        if currency is None:
            if re.search(r"(?:chi\s+tra|thanh\s+toan|boi\s+thuong|tra\s+tien|trieu|ty|nghin|ngan)",folded):currency="VND"
            else:return None,"Payout amount in “"+original.strip()+"” has no currency."
        if amount<0:return None,"A payout cannot be negative."
        return Action(outcome=Outcome.PAYOUT,amount=money_value(amount,currency)),"“"+original.strip()+"” → "+fmt_action(Action(outcome=Outcome.PAYOUT,amount=money_value(amount,currency)))
    action=Action(outcome=Outcome(name))
    return action,"“"+original.strip()+"” → "+fmt_action(action)

def interpret(cells):
    """cells maps a canonical column to its text. Returns (inputs, expected, status, notes, questions)."""
    notes=[];questions=[]
    inputs,found,asked=read_inputs(cells.get("test_data",""))
    notes.extend(found);questions.extend(asked)
    if not inputs and not asked:
        for column in ("title","steps","preconditions"):
            inputs,found,asked=read_inputs(cells.get(column,""))
            if inputs:
                notes.extend(found);notes.append("Inputs were read from the "+column.replace("_"," ")+" because the test data cell names none; please confirm.")
                questions.append("Confirm the inputs read from the "+column.replace("_"," ")+".");break
        else:
            questions.append("No test input recognised (expected something like “Tuổi: 61” or “Số tiền: 120.000.000 VND”).")
    expected,note=read_expected(cells.get("expected",""))
    if expected is None:questions.append(note)
    else:notes.append(note)
    status="ready" if inputs and expected is not None and not questions else "needs_confirmation"
    return tuple(inputs),expected,status,tuple(notes),tuple(questions)
