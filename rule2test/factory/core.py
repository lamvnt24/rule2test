import hashlib, json, copy
# Compatibility exports for the original demo API.
from .validators.rule_validator import FIELDS, validate_legacy_rules as validate
from .engines.oracle_engine import legacy_oracle as oracle
from .engines.insurance_engine import legacy_mock_sut as mock_sut
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
def obligations(rule):
    t=rule["threshold"]; lo,hi=FIELDS[rule["field"]]
    return [("below",t-1),("at",t),("above",t+1),("null",None),("negative",-1),("overflow",hi+1),("wrong_type","invalid")]
def analyze(old,new,existing):
    validate(old);validate(new)
    a={r["id"]:r for r in old}; b={r["id"]:r for r in new}
    if set(a)!=set(b): raise ValueError("This base supports threshold changes on stable rule IDs; added/deleted rules require explicit modeling")
    if any(a[k]["field"]!=b[k]["field"] for k in a): raise ValueError("Field migration requires explicit modeling")
    if not isinstance(existing,list) or len(existing)>2000: raise ValueError("Invalid test repository")
    seen=set(); tests=[]; impact=[]
    for test in existing:
        if set(test)!={"id","rule_id","value"} or test["rule_id"] not in b: raise ValueError("Test must cite a known rule")
        if not isinstance(test["id"],str) or not test["id"] or test["id"] in seen: raise ValueError("Duplicate test ID")
        if test["id"].startswith("GEN-"): raise ValueError("GEN- prefix is reserved")
        seen.add(test["id"]); t=copy.deepcopy(test); t["origin"]="existing"; tests.append(t)
        k=t["rule_id"]
        if a[k]["threshold"]!=b[k]["threshold"]:
            impact.append({**t,"old_expected":oracle(a[k],t["value"]),"new_expected":oracle(b[k],t["value"]),
                           "behavior_changed":oracle(a[k],t["value"])!=oracle(b[k],t["value"])})
    gaps=[]; total=0; covered=0
    for r in new:
        for label,value in obligations(r):
            total+=1
            if any(t["rule_id"]==r["id"] and type(t["value"])==type(value) and t["value"]==value for t in tests): covered+=1
            else: gaps.append({"id":f"GEN-{r['id']}-{label}","rule_id":r["id"],"value":value,"origin":"generated","obligation":label})
    return {"old":old,"new":new,"existing":tests,"candidates":gaps,"impact":impact,
            "delta":[{"rule_id":k,"before":a[k]["threshold"],"after":b[k]["threshold"],"source":b[k]["source"]} for k in a if a[k]["threshold"]!=b[k]["threshold"]],
            "baseline_coverage":round(100*covered/total,2),"obligation_count":total,"input_hash":digest({"old":old,"new":new,"existing":existing})}
def execute(plan,approved,fault):
    if fault not in {"none","boundary","stale"}: raise ValueError("Unknown fault mode")
    candidates={t["id"]:t for t in plan["candidates"]}
    if not isinstance(approved,list) or len(set(approved))!=len(approved) or any(x not in candidates for x in approved): raise ValueError("Invalid approved IDs")
    tests=plan["existing"]+[candidates[x] for x in approved]
    rules={r["id"]:r for r in plan["new"]}; rows=[]
    for t in tests:
        r=rules[t["rule_id"]]; expected=oracle(r,t["value"]); actual=mock_sut(r,t["value"],fault)
        rows.append({**t,"expected":expected,"actual":actual,"status":"PASS" if actual==expected else "FAIL",
                     "source":r["source"],"rule_hash":digest(r)})
    covered=0
    for r in rules.values():
        for _,v in obligations(r):
            covered+=any(t["rule_id"]==r["id"] and type(t["value"])==type(v) and t["value"]==v for t in tests)
    mutants=[]
    for r in rules.values():
        for kind in ("boundary","stale"):
            killed=[t["id"] for t in tests if t["rule_id"]==r["id"] and oracle(r,t["value"])!=mock_sut(r,t["value"],kind)]
            mutants.append({"rule_id":r["id"],"mutation":kind,"killed":bool(killed),"witnesses":killed})
    coverage=round(covered/plan["obligation_count"]*100,2)
    acceptance=round(len(approved)/len(candidates)*100,2) if candidates else None
    failures=sum(x["status"]=="FAIL" for x in rows)
    return {"rows":rows,"mutants":mutants,"metrics":{"boundary_coverage":coverage,
            "rule_coverage":round(100*len({t["rule_id"] for t in tests})/len(rules),2),
            "reviewer_acceptance":acceptance,"mutation_score":round(100*sum(x["killed"] for x in mutants)/len(mutants),2),
            "traceability":100 if rows else 0,"passed":len(rows)-failures,"failed":failures},
            "gate":"GO" if coverage>=90 and failures==0 and (acceptance is None or acceptance>=70) else "NO-GO",
            "fault_mode":fault,"approved_ids":approved,"input_hash":plan["input_hash"]}
