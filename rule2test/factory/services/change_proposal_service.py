"""Turn an analysed workflow into the sentences a reviewer needs: keep / change / add, and why.

Nothing here decides anything. Expected results come from the typed oracle, the affected-test
list from the impact analysis and the additions from the gap analysis; this module only explains
them, citing the rule and the original spreadsheet cell each proposal rests on.
"""
import re
from factory.engines.oracle_engine import OracleEngine
from factory.exceptions import ConflictError,ValidationError
from .text_patterns import fmt_inputs,fmt_action,fmt_condition,fmt_rule,fmt_value,field_name

GROUPS=(("check","Needs your attention"),("affected","Directly affected by the change"),("boundary","Other limits worth a test"),
        ("coverage","Coverage of every rule branch"),("robustness","Robustness: invalid or missing inputs"),("unchanged","Unchanged tests"))
PRIORITY={key:index for index,(key,_) in enumerate(GROUPS)}
EXCEPTIONS={"null":"{field} left empty","missing":"{field} not sent at all","negative":"Negative {lower}","overflow":"{field} above the supported maximum",
            "wrong_type":"{field} given as text","wrong_currency":"Claim in a different currency"}
POSITIONS={"below":"just below","at":"exactly at","above":"just above"}

def explain_delta(delta):
    """One sentence per rule delta, in business words."""
    if delta.kind.value=="added":return "New rule: "+fmt_rule(delta.after)
    if delta.kind.value=="removed":return "Rule removed: "+fmt_rule(delta.before)
    before,after=delta.before,delta.after;parts=[]
    removed=[c for c in before.conditions if c not in after.conditions];added=[c for c in after.conditions if c not in before.conditions]
    for old in removed:
        new=next((c for c in added if c.field==old.field and c.operator==old.operator),None)
        if new:parts.append(fmt_condition(old)+" became "+fmt_condition(new));added.remove(new)
        else:parts.append("condition removed: "+fmt_condition(old))
    parts.extend("condition added: "+fmt_condition(c) for c in added)
    if before.action!=after.action:
        if before.action.formula and after.action.formula and before.action.formula.deductible!=after.action.formula.deductible:
            parts.append("deductible "+fmt_value(before.action.formula.deductible)+" became "+fmt_value(after.action.formula.deductible))
        else:parts.append("outcome "+fmt_action(before.action)+" became "+fmt_action(after.action))
    if (before.effective_from,before.effective_to)!=(after.effective_from,after.effective_to):parts.append("effective dates changed")
    return "; ".join(parts) or "rule text changed"

def changes(workflow):
    """Everything the reviewer should know changed, including a default outcome the rule delta does not cover."""
    analysis=workflow.analysis
    result=[explain_delta(d) for d in analysis.delta.deltas] if analysis else []
    if workflow.old_table.default_action!=workflow.new_table.default_action:
        result.append("default outcome "+fmt_action(workflow.old_table.default_action)+" became "+fmt_action(workflow.new_table.default_action))
    return result

def _trace(oracle,workflow,inputs):
    try:return oracle.trace(workflow.new_table,workflow.new_rules,inputs,as_of=workflow.new_as_of)
    except (ValidationError,ConflictError):return None

def _rule_info(workflow,trace):
    if trace is None:return dict(title="Cannot evaluate",sentence="The inputs cannot be evaluated against the rule table.",quote="",rule_id=None)
    if not trace.matched_row_ids and not trace.default_used:
        return dict(title="Input validation",sentence="An invalid or missing input is rejected before any rule is evaluated",quote="",rule_id=None)
    if trace.matched_row_ids:
        row=next(r for r in workflow.new_table.rows if r.row_id==trace.matched_row_ids[0])
        rule=next(r for r in workflow.new_rules if r.rule_id==row.rule.rule_id and r.version==row.rule.version)
        return dict(title=rule.title,sentence=fmt_rule(rule),quote=next((s.quote for s in rule.sources if s.quote),""),rule_id=rule.rule_id)
    return dict(title="Default outcome",sentence="No rule matches → "+fmt_action(workflow.new_table.default_action),quote="",rule_id=None)

def _boundary(obligation,workflow,old_conditions,baseline_known):
    """(reason, is_new_limit) for a boundary obligation, located through its row and condition index."""
    label=obligation.label
    match=re.match(r"condition (\d+): ",label)
    if match and obligation.row_id:
        row=next((r for r in workflow.new_table.rows if r.row_id==obligation.row_id),None)
        index=int(match.group(1))
        if row and index<len(row.conditions):
            condition=row.conditions[index];position=next((p for p in POSITIONS if label.endswith(" "+p+" "+str(condition.value.data))),None)
            new=baseline_known and condition not in old_conditions
            where=POSITIONS.get(position,"at")+(" the new limit" if new else " the limit")
            return "Tests "+where+" ("+fmt_condition(condition)+")",new
    if label.startswith("deductible ") or label.startswith("default deductible "):
        position=label.split()[-1]
        return "Claim "+POSITIONS.get(position,"exactly at")+" the deductible",False
    return "Covers "+label,False

def _addition(test,workflow,obligations,old_conditions,baseline_known,changed):
    reasons=[];groups=[]
    for identifier in test.obligation_ids:
        obligation=obligations.get(identifier)
        if obligation is None:continue
        if obligation.category=="boundary":
            reason,new=_boundary(obligation,workflow,old_conditions,baseline_known)
            reasons.append(reason);groups.append("affected" if new and changed else "boundary")
        elif obligation.category=="exception":
            field,_,label=obligation.label.partition(": ")
            reasons.append("Robustness: "+EXCEPTIONS.get(label,label).format(field=field_name(field),lower=field_name(field).lower()))
            groups.append("robustness")
        else:
            reasons.append("Exercises the default outcome" if obligation.row_id is None else "Exercises the rule row")
            groups.append("coverage")
    unique=list(dict.fromkeys(reasons)) or ["Covers a gap the current tests leave"]
    # A candidate covering several obligations belongs to the most important group among them.
    return "; ".join(unique),(min(groups,key=lambda g:PRIORITY[g]) if groups else "coverage")

def build(workflow,*,link=None,suite=None,baseline_known=True):
    """Rows for the review table plus the excluded suite rows. Requires an analysed workflow."""
    analysis=workflow.analysis
    if analysis is None:return dict(baseline_known=baseline_known,changed=False,changes=[],rows=[],excluded=[],summary={},groups=list(GROUPS))
    oracle=OracleEngine()
    changed=bool(analysis.delta.deltas) or workflow.old_table.default_action!=workflow.new_table.default_action
    delta_text="; ".join(changes(workflow))
    existing={t.test_id:t for t in workflow.existing_tests};impact={r.test_id:r for r in analysis.impact}
    decisions={a.subject_id:a.decision.value for a in workflow.approvals}
    obligations={o.obligation_id:o for o in analysis.gaps.obligations}
    old_conditions={c for r in workflow.old_rules for c in r.conditions}
    suite_rows={r.row_id:r for r in suite.rows} if suite else {}
    rows=[]
    for test in workflow.tests:
        trace=_trace(oracle,workflow,test.inputs);rule=_rule_info(workflow,trace)
        after=test.expected;attention=False
        original=[c.to_dict() for c in suite_rows[test.test_id].cells] if test.test_id in suite_rows else []
        source=next((dict(sheet=s.sheet,cell=s.cell,quote=s.quote) for s in test.sources if s.sheet),None)
        if test.test_id in existing:
            before=existing[test.test_id].expected;record=impact.get(test.test_id);title=test.title
            if record is not None and record.status=="unknown":
                kind,group="check","check";reason=record.reason
            elif before==after:
                kind,group="keep","unchanged"
                reason=fmt_inputs(test.inputs)+" still gives "+fmt_action(after)+(" under the new rule" if baseline_known else " under the rule")+": "+rule["sentence"]+"."
            else:
                kind,group="change","affected"
                stated_matches_old=record is not None and record.old_expected is not None and record.old_expected==before
                if baseline_known and changed and stated_matches_old:
                    reason="The rule changed ("+delta_text+"). Under the new rule "+fmt_inputs(test.inputs)+" → "+fmt_action(after)+"."
                elif baseline_known and record is not None and record.old_expected is not None:
                    attention=True;group="check"
                    reason=("The file expects "+fmt_action(before)+", which matches neither the current rule ("+fmt_action(record.old_expected)
                            +") nor the new rule ("+fmt_action(after)+"). Check the original test; the proposal follows the new rule.")
                else:
                    reason="Under the rule "+fmt_inputs(test.inputs)+" → "+fmt_action(after)+", but the file expects "+fmt_action(before)+": "+rule["sentence"]+"."
        else:
            before=None;kind="add";title="No test for "+fmt_inputs(test.inputs)
            reason,group=_addition(test,workflow,obligations,old_conditions,baseline_known,changed)
            reason+=". Expected "+fmt_action(after)+" ("+rule["sentence"]+")."
        rows.append(dict(test_id=test.test_id,revision=test.revision,title=title,kind=kind,group=group,priority=PRIORITY[group],attention=attention,
            inputs=[x.to_dict() for x in test.inputs],inputs_text=fmt_inputs(test.inputs),
            before=before.to_dict() if before else None,before_text=fmt_action(before) if before else None,
            after=after.to_dict(),after_text=fmt_action(after),reason=reason,rule=rule,source=source,original=original,
            review=decisions.get(test.test_id,"pending"),origin=test.origin.value,rationale=test.rationale))
    order={"check":0,"change":1,"add":2,"keep":3}
    rows.sort(key=lambda r:(r["priority"],order[r["kind"]],r["test_id"]))
    excluded=[]
    for item in (link.excluded if link else ()):
        row=suite_rows.get(item.row_id)
        excluded.append(dict(row_id=item.row_id,title=item.title,reason=item.reason,original=[c.to_dict() for c in row.cells] if row else []))
    summary={key:sum(r["kind"]==key for r in rows) for key in order}
    summary["excluded"]=len(excluded)
    labels=[(key,label if baseline_known or key!="affected" else "Does not match the rule") for key,label in GROUPS]
    return dict(baseline_known=baseline_known,changed=changed,changes=changes(workflow),rows=rows,excluded=excluded,summary=summary,groups=labels)

def suggest_sut(workflow):
    """Mock SUT settings that model the new rule. Deployment settings, editable; the point of a test is that they may differ."""
    rules=workflow.new_rules
    fields={c.field for r in rules for c in r.conditions}
    formula=next((a.formula for a in [workflow.new_table.default_action]+[r.action for r in rules] if a.formula),None)
    base=dict(profile="eligibility",fault="none",min_age=18,max_age=65,claim_threshold="150000000",deductible="10000000",currency="VND")
    if "age" in fields:
        lower=[c for r in rules for c in r.conditions if c.field=="age" and c.operator.value in ("ge","gt")]
        upper=[c for r in rules for c in r.conditions if c.field=="age" and c.operator.value in ("le","lt")]
        base["min_age"]=min((c.value.data+(1 if c.operator.value=="gt" else 0)) for c in lower) if lower else 0
        base["max_age"]=max((c.value.data-(1 if c.operator.value=="lt" else 0)) for c in upper) if upper else 120
        return dict(base,note="Eligibility mock configured from the new rule: ages "+str(base["min_age"])+"–"+str(base["max_age"])+".")
    if formula is not None:
        return dict(base,profile="deductible",deductible=format(formula.deductible.data,"f"),currency=formula.deductible.currency,
            note="Deductible mock configured from the new rule: "+fmt_value(formula.deductible)+".")
    if "claim_amount" in fields:
        threshold=next((c for r in rules for c in r.conditions if c.field=="claim_amount" and c.operator.value in ("gt","ge") and r.action.outcome.value=="review"),None)
        if threshold is not None:
            cutoff=threshold.value.data-(1 if threshold.operator.value=="ge" else 0)
            return dict(base,profile="claim_review",claim_threshold=format(cutoff,"f"),currency=threshold.value.currency,
                note="Claim-review mock configured from the new rule: review above "+fmt_value(threshold.value)+".")
    return dict(base,note="No mock profile matches these rules; configure the system under test by hand.")
