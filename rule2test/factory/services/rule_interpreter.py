"""Reads one-sentence insurance rules into the typed rule rows, citing the exact line each came from.

Three shapes the demo domain supports, in Vietnamese, English or Japanese:
  age range      "Khách hàng từ 18 đến 65 tuổi được tham gia bảo hiểm."      -> allow inside, deny outside
  claim threshold "Yêu cầu bồi thường trên 100.000.000 VND phải được xem xét." -> review above, allow otherwise
  deductible      "Số tiền chi trả bằng số tiền yêu cầu trừ đi 5.000.000 VND." -> payout max(claim - 5,000,000, 0)
Everything else is a question back to the person, never a guess.
"""
import re
from dataclasses import dataclass,field
from decimal import Decimal
from factory.parsers.schema import POLICY_COLUMNS,RULE_COLUMNS
from .text_patterns import fold,find_money

INTERPRETER="rule-patterns-v1"
TABLE_ID="DT-rules"
SHAPES={"age":("R-age-eligibility","Age eligibility"),"claim":("R-claim-review","Claim review threshold"),"deductible":("R-deductible","Deductible payout")}

@dataclass(frozen=True)
class Found:
    field: str
    operator: str
    value: object          # int for age, Decimal for money
    line: int
    quote: str

@dataclass
class Finding:
    shape: str
    conditions: list=field(default_factory=list)
    outcome: str="allow"
    default: str="deny"
    currency: str|None=None
    deductible: Decimal|None=None
    notes: list=field(default_factory=list)

AGE_WORD=r"(?:tuoi|do\s+tuoi|age[ds]?|years?\s+old|年齢|歳)"
RANGE=(r"tu\s+(\d+)\s*(?:tuoi)?\s*(?:den|toi|-|–|~)\s*(\d+)\s*tuoi",
       r"(\d+)\s*(?:den|toi|-|–|~|to|through|thru|and)\s*(\d+)\s*(?:tuoi|years?(?:\s+old)?|years?\s+of\s+age|歳)",
       r"(?:age[ds]?|tuoi|do\s+tuoi)\s*(?:from|tu|between|of|:|la)?\s*(\d+)\s*(?:to|through|thru|and|-|–|~|den|toi)\s*(\d+)",
       r"(\d+)\s*歳以上\s*(\d+)\s*歳以下")
OUTSIDE=r"(?:duoi|under|below|younger\s+than|less\s+than)\s*(\d+)\s*(?:tuoi)?\s*(?:hoac|or|va|and|,)\s*(?:tren|over|above|older\s+than|more\s+than)\s*(\d+)"
MAX_ONLY=(r"(?:toi\s+da|khong\s+qua|khong\s+vuot\s+qua|up\s+to|at\s+most|not\s+(?:older|more)\s+than|no\s+older\s+than|maximum(?:\s+age)?(?:\s+of)?|max(?:imum)?)[^\d]{0,30}?(\d+)",
          r"(\d+)\s*歳以下")
MIN_ONLY=(r"(?:tu|from|toi\s+thieu|it\s+nhat|at\s+least|minimum(?:\s+age)?(?:\s+of)?|min(?:imum)?)[^\d]{0,30}?(\d+)\s*(?:tuoi|years?)?\s*(?:tro\s+len|or\s+older|or\s+more|and\s+(?:above|over|older)|upwards?|以上)",
          r"(?:age[ds]?|tuoi)\s*(?:is\s+|la\s+|:\s*)?(?:at\s+least|toi\s+thieu|it\s+nhat|>=|≥)\s*(\d+)",
          r"(?:at\s+least|toi\s+thieu|it\s+nhat|minimum(?:\s+age)?(?:\s+of)?)\s*(\d+)\s*(?:tuoi|years?(?:\s+old)?|歳)",
          r"(\d+)\s*歳以上")
ALLOW=(r"(?:duoc\s+tham\s+gia|duoc\s+chap\s+nhan|du\s+dieu\s+kien|duoc\s+(?:mua|dang\s+ky|bao\s+hiem|phe\s+duyet|duyet)|hop\s+le|eligible|allowed|permitted|accept"
       r"|may\s+(?:enrol|join|apply|participate|buy|be\s+insured)|can\s+(?:enrol|join|apply|participate|buy)|許可|加入(?:でき|を認|可)|tham\s+gia|enrol|join|participat|apply)")
DENY=r"(?:khong\s+duoc|tu\s+choi|khong\s+du\s+dieu\s+kien|khong\s+hop\s+le|not\s+eligible|ineligible|denied|deny|reject|refus|declin|拒否|不可)"
REVIEW=r"(?:xem\s+xet|kiem\s+tra\s+thu\s+cong|duyet\s+thu\s+cong|tham\s+dinh|phe\s+duyet\s+thu\s+cong|review|manual|escalat|審査|要確認)"
ACCEPT=r"(?:duoc\s+chap\s+nhan|chap\s+nhan|duoc\s+duyet|tu\s+dong\s+duyet|duoc\s+phe\s+duyet|hop\s+le|cho\s+phep|accept|allow|approv|permit|許可|承認)"
COMPARATORS=(("gt",r"(?:tren|lon\s+hon|vuot\s+qua|vuot|cao\s+hon|nhieu\s+hon|over|above|exceed(?:s|ing)?|greater\s+than|more\s+than|higher\s+than|larger\s+than|beyond|>|を超え|超過)"),
             ("ge",r"(?:tro\s+len|>=|≥|at\s+least|or\s+more|or\s+above|以上|toi\s+thieu|khong\s+nho\s+hon|khong\s+duoi|from)"),
             ("lt",r"(?:duoi|nho\s+hon|thap\s+hon|it\s+hon|under|below|less\s+than|lower\s+than|smaller\s+than|<|未満)"),
             ("le",r"(?:toi\s+da|khong\s+qua|khong\s+vuot\s+qua|up\s+to|at\s+most|not\s+more\s+than|or\s+less|or\s+below|<=|≤|以下|tro\s+xuong)"))
OTHERWISE=r"(?:;|\botherwise\b|\belse\b|\bother\s+(?:valid\s+)?claims?\b|\bcac\s+(?:truong\s+hop|yeu\s+cau)\s+(?:khac|con\s+lai)\b|\bcon\s+lai\b|\bnguoc\s+lai\b|\bngoai\s+(?:khoang|pham\s+vi)\b|その他|上記の条件に該当しない)"
DEDUCTIBLE=r"(?:khau\s+tru|mien\s+thuong|tru\s+di|tru\s+(?=\d)|deductible|minus|less\s+(?:a|the)?\s*deductible|差し引|免責)"
MONEY_CUE=r"(?:trieu|ty|nghin|ngan|tr|dong|vnd)(?![a-z])"

def _currency(amount,folded):
    if amount[1]:return amount[1],None
    if re.search(MONEY_CUE,folded) or re.search(r"(?:so\s+tien|yeu\s+cau|boi\s+thuong|chi\s+tra)",folded):return "VND","Currency not written; VND assumed."
    return None,None

def _outcome(fragment):
    if re.search(REVIEW,fragment):return "review"
    if re.search(DENY,fragment):return "deny"
    if re.search(ACCEPT,fragment):return "allow"
    return None

def _age(line,folded):
    if not re.search(AGE_WORD,folded):return None,[]
    lo=hi=None;matched=None
    for pattern in RANGE:
        match=re.search(pattern,folded)
        if match:lo,hi=int(match.group(1)),int(match.group(2));matched=match;break
    inverse=re.search(OUTSIDE,folded) if matched is None else None
    if inverse and re.search(DENY,folded):lo,hi=int(inverse.group(1)),int(inverse.group(2));matched=inverse
    if matched is None:
        maximum=next((m for p in MAX_ONLY for m in [re.search(p,folded)] if m),None)
        minimum=next((m for p in MIN_ONLY for m in [re.search(p,folded)] if m),None)
        if maximum:hi=int(maximum.group(1))
        if minimum:lo=int(minimum.group(1))
        if maximum is None and minimum is None:return None,[]
    if inverse is None and not re.search(ALLOW,folded):
        if re.search(DENY,folded):return None,["Line "+str(line[0])+" states who is refused; write the accepted age range instead (for example “từ 18 đến 65 tuổi được tham gia”)."]
        return None,["Line "+str(line[0])+" gives an age range but not whether those customers are accepted."]
    if lo is not None and hi is not None and lo>hi:return None,["Line "+str(line[0])+": the lower age "+str(lo)+" is above the upper age "+str(hi)+"."]
    for bound in (lo,hi):
        if bound is not None and not 0<=bound<=120:return None,["Line "+str(line[0])+": age "+str(bound)+" is outside 0..120."]
    finding=Finding(shape="age",outcome="allow",default="deny")
    if lo is not None:finding.conditions.append(Found("age","ge",lo,line[0],line[1]))
    if hi is not None:finding.conditions.append(Found("age","le",hi,line[0],line[1]))
    return finding,[]

def _deductible(line,folded):
    keyword=re.search(DEDUCTIBLE,folded)
    amounts=find_money(folded)
    if not keyword or not amounts:return None,[]
    if keyword.group(0) in ("差し引","免責"):  # Japanese puts the amount before the verb: 5000000 VNDを差し引いた
        chosen=next((a for a in reversed(amounts) if a[4]<=keyword.start()),amounts[0])
    else:chosen=next((a for a in amounts if a[3]>=keyword.end()-1),amounts[0])
    currency,note=_currency(chosen,folded)
    if currency is None:return None,["Line "+str(line[0])+": specify the currency of the deductible (for example VND)."]
    finding=Finding(shape="deductible",outcome="payout",default="invalid",currency=currency,deductible=chosen[0])
    finding.conditions.append(Found("claim_amount","ge",Decimal(0),line[0],line[1]))
    if note:finding.notes.append(note)
    return finding,[]

def _claim(line,folded):
    amounts=find_money(folded)
    # A bare number is not money: the line needs a currency, a multiplier word or claim wording.
    if not amounts or not (any(a[1] for a in amounts) or re.search(MONEY_CUE,folded) or re.search(r"(?:claim|yeu\s+cau|boi\s+thuong|so\s+tien|請求|金額)",folded)):return None,[]
    split=re.search(OTHERWISE,folded)
    main=folded[:split.start()] if split else folded
    rest=folded[split.end():] if split else ""
    amount=next((a for a in amounts if a[3]<len(main)),None)
    if amount is None:return None,[]
    operator=None;best=-1
    for name,pattern in COMPARATORS:
        for match in re.finditer(pattern,main):
            if match.end()<=amount[3]+1 and match.end()>best:operator,best=name,match.end()
    if operator is None:
        after=main[amount[4]:]
        if re.search(r"^\s*(?:tro\s+len|or\s+more|以上)",after):operator="ge"
        elif re.search(r"^\s*(?:tro\s+xuong|or\s+less|以下)",after):operator="le"
        elif re.search(r"^\s*(?:を超え|超過)",after):operator="gt"
        elif re.search(r"^\s*未満",after):operator="lt"
    outcome=_outcome(main)
    if operator is None or outcome is None:
        if re.search(r"(?:claim|yeu\s+cau|boi\s+thuong|請求)",folded):
            return None,["Line "+str(line[0])+": state the comparison (over / at least / under) and the outcome (review / accepted / rejected) for the amount."]
        return None,[]
    currency,note=_currency(amount,folded)
    if currency is None:return None,["Line "+str(line[0])+": specify the currency of the amount (for example VND)."]
    default=_outcome(rest) if rest else None
    if default is None:default={"review":"allow","allow":"review","deny":"allow"}[outcome]
    finding=Finding(shape="claim",outcome=outcome,default=default,currency=currency)
    finding.conditions.append(Found("claim_amount",operator,amount[0],line[0],line[1]))
    if note:finding.notes.append(note)
    return finding,[]

def interpret(text):
    """Returns (Finding or None, questions). A text is one rule; several sentences may refine it."""
    findings=[];questions=[]
    for number,raw in enumerate(text.splitlines(),1):
        folded=fold(raw)
        if not folded.strip():continue
        for reader in (_deductible,_age,_claim):
            finding,asked=reader((number,raw),folded)
            questions.extend(asked)
            if finding:findings.append(finding);break
    if questions:return None,questions
    if not findings:
        return None,["No rule pattern recognised. Write one of: an accepted age range (“từ 18 đến 65 tuổi được tham gia”), "
                     "a claim threshold (“trên 100.000.000 VND phải xem xét”), or a deductible (“trừ đi 5.000.000 VND”)."]
    shapes={f.shape for f in findings}
    if len(shapes)>1:return None,["The text mixes different rule types ("+", ".join(sorted(shapes))+"). Enter one rule at a time."]
    merged=findings[0]
    for extra in findings[1:]:
        if merged.shape!="age" or extra.outcome!=merged.outcome:
            return None,["Lines "+str(merged.conditions[0].line)+" and "+str(extra.conditions[0].line)+" both state a "+merged.shape+" rule; keep one."]
        for condition in extra.conditions:
            if any(c.operator==condition.operator for c in merged.conditions):
                return None,["Lines "+str(merged.conditions[0].line)+" and "+str(condition.line)+" both set the "+("lower" if condition.operator=="ge" else "upper")+" age limit; keep one."]
            merged.conditions.append(condition)
    return merged,[]

def rows(finding,label,version):
    """Extraction-contract rows: one policy row, one rule row per condition, one citation per row."""
    rule_id,title=SHAPES[finding.shape]
    policy=dict(zip(POLICY_COLUMNS,(label,TABLE_ID,version,"unique",finding.default,None,None,None,None)))
    rules=[]
    for found in finding.conditions:
        money=found.field=="claim_amount"
        rules.append(dict(zip(RULE_COLUMNS,(rule_id,version,title,found.field,found.operator,"money" if money else "integer",
            format(found.value,"f") if money else int(found.value),finding.currency if money else None,finding.outcome,None,
            format(finding.deductible,"f") if finding.deductible is not None else None,None,None,found.quote))))
    return policy,rules
