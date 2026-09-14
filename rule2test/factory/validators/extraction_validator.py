"""Independent schema and exact-line citation gate. Literal grounding is not semantic proof."""
import json
from dataclasses import replace
from factory.models import SourceReference,RuleReference,content_hash
from factory.models.common import require
from factory.exceptions import ValidationError
from factory.models.extraction import MAX_RESPONSE_BYTES
from factory.parsers.common import strict_json
from factory.parsers.json_parser import JsonParser

KEYS={"status","issues","policies","rules_v1","rules_v2","citations"}

def validate_response(raw,request):
    require(type(raw) is str and 0<len(raw.encode("utf-8"))<=MAX_RESPONSE_BYTES,"Expected bounded JSON text")
    try:result=strict_json(raw)
    except (ValueError,TypeError,RecursionError) as exc:raise ValidationError("Invalid strict JSON output") from exc
    require(type(result) is dict and set(result)==KEYS,"Unexpected extraction output fields")
    require(result["status"] in ("ready","needs_clarification"),"Unsupported extraction status")
    issues=result["issues"]
    require(type(issues) is list and len(issues)<=20 and all(type(x) is str and 0<len(x.strip())<=512 for x in issues),"Invalid clarification issues")
    for key,limit in (("policies",2),("rules_v1",50),("rules_v2",50),("citations",102)):
        require(type(result[key]) is list and len(result[key])<=limit,"Invalid or oversized "+key)
        require(all(type(row) is dict for row in result[key]),"Expected row objects")
    if result["status"]=="needs_clarification":
        require(bool(issues) and all(not result[k] for k in KEYS-{"status","issues"}),"Clarification must not contain executable rules")
        return result,{}
    labels={s.label for s in request.sources}
    if request.baseline_known:
        require(not issues and len(result["policies"])==2 and bool(result["rules_v1"]) and bool(result["rules_v2"]),"Ready requires complete rules and no issues")
    else:
        require(not issues and len(result["policies"])==1 and not result["rules_v1"] and bool(result["rules_v2"]),"Without a current rule, ready output holds only the v2 policy and rules")
    expected={}
    for index,row in enumerate(result["policies"]):
        require(row.get("label") in labels and row["label"] not in expected.values(),"Policy requires one label per supplied version")
        expected["/policies/"+str(index)]=row["label"]
    for label in ("v1","v2"):
        for index,row in enumerate(result["rules_"+label]):expected["/rules_"+label+"/"+str(index)]=label
    sources={s.document_id:s for s in request.sources};citations={}
    for citation in result["citations"]:
        require(set(citation)=={"path","document_id","line","quote"},"Invalid citation fields")
        path=citation["path"];identifier=citation["document_id"];line=citation["line"];quote=citation["quote"]
        require(type(path) is str and path in expected and path not in citations,"Unknown or duplicate citation target")
        require(type(identifier) is str and identifier in sources,"Unknown source document")
        source=sources[identifier]
        require(source.label==expected[path],"Citation refers to wrong source version")
        require(type(line) is int and 1<=line<=len(source.text.splitlines()),"Citation line outside source")
        require(type(quote) is str and bool(quote.strip()) and quote==source.text.splitlines()[line-1],"Citation does not match exact source line")
        if path.startswith("/rules_"):
            _,key,index=path.split("/")
            require(result[key][int(index)].get("quote")==quote,"Rule quote differs from citation")
        citations[path]=SourceReference(document_id=identifier,document_hash=source.document_hash,quote=quote,line_start=line,line_end=line)
    require(set(citations)==set(expected),"Every rule and policy row requires a source citation")
    return result,citations

def compile_proposal(proposal):
    result,citations=validate_response(proposal.response_json,proposal.request)
    require(result["status"]=="ready","Proposal requires clarification")
    tests=strict_json(proposal.request.existing_tests_json)
    require(type(tests) is list and len(tests)<=1000,"Existing tests must be an array of at most 1000 rows")
    policies=list(result["policies"]);rules_v1=list(result["rules_v1"]);rules_v2=list(result["rules_v2"]);citations=dict(citations)
    if not proposal.request.baseline_known:
        # No current rule was supplied: the baseline is the new rule itself (as version 1), so the
        # workflow has no semantic delta and every existing test is judged against the new rule only.
        policies=[dict(policies[0],label="v1",version=1),policies[0]];rules_v1=[dict(row,version=1) for row in rules_v2]
        citations["/policies/1"]=citations["/policies/0"]
        for index in range(len(rules_v2)):citations["/rules_v1/"+str(index)]=citations["/rules_v2/"+str(index)]
    payload=dict(schema_version=1,created_at=proposal.metadata.created_at.isoformat(),created_by="Extraction proposal",
        policies=policies,rules_v1=rules_v1,rules_v2=rules_v2,tests=tests)
    data=json.dumps(payload,ensure_ascii=False,default=str,separators=(",",":")).encode("utf-8")
    bundle=JsonParser().parse(data,"extracted-"+proposal.proposal_id+".json")
    rows={"v1":rules_v1,"v2":rules_v2}
    def bind(label,rules,table):
        bound=[]
        for rule in rules:
            source_refs=tuple(citations["/rules_"+label+"/"+str(i)] for i,row in enumerate(rows[label]) if row["rule_id"]==rule.rule_id)
            # Include the default-policy citation so typed evidence also carries that source.
            policy_source=next(citations["/policies/"+str(i)] for i,row in enumerate(policies) if row["label"]==label)
            bound.append(replace(rule,sources=tuple(dict.fromkeys(source_refs+(policy_source,)))))
        refs={r.rule_id:RuleReference(rule_id=r.rule_id,version=r.version,rule_hash=content_hash(r)) for r in bound}
        return tuple(bound),replace(table,rows=tuple(replace(row,rule=refs[row.rule.rule_id]) for row in table.rows)),refs
    old_rules,old_table,old_refs=bind("v1",bundle.old_rules,bundle.old_table)
    new_rules,new_table,_=bind("v2",bundle.new_rules,bundle.new_table)
    tests=tuple(replace(t,rules=tuple(old_refs[r.rule_id] for r in t.rules)) for t in bundle.existing_tests)
    return replace(bundle,old_rules=old_rules,old_table=old_table,new_rules=new_rules,new_table=new_table,existing_tests=tests),data
