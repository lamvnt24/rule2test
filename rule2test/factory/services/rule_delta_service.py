"""Rule deltas use canonical semantics; formatting changes remain visible separately."""
from factory.models import RuleDelta, DeltaKind
from factory.models.analysis import DeltaAnalysis
from factory.models.common import require
from ._support import stable_id, value_key

def semantic_signature(rule):
    conditions=sorted((c.field,c.operator.value,value_key(c.value)) for c in rule.conditions)
    action=rule.action
    amount=value_key(action.amount) if action.amount else None
    formula=(action.formula.field,value_key(action.formula.deductible)) if action.formula else None
    return (conditions,(action.outcome.value,amount,formula),rule.effective_from,rule.effective_to)

class RuleDeltaService:
    def compare(self,old_rules,new_rules):
        old={r.rule_id:r for r in old_rules};new={r.rule_id:r for r in new_rules}
        require(len(old)==len(old_rules) and len(new)==len(new_rules),"Duplicate rule ID in version")
        deltas=[];presentation=[]
        for key in sorted(old.keys()|new.keys()):
            before=old.get(key);after=new.get(key)
            if before and after:
                require(after.version>=before.version,"Rule version cannot decrease")
                if before!=after: require(after.version>before.version,"Changed snapshot must increase version")
                if semantic_signature(before)==semantic_signature(after):
                    if before!=after:presentation.append(key)
                    continue
                kind=DeltaKind.MODIFIED
                changed=tuple(k for k in ("title","conditions","action","sources","effective_from","effective_to") if getattr(before,k)!=getattr(after,k))
            else:
                kind=DeltaKind.ADDED if after else DeltaKind.REMOVED;changed=()
            identifier=stable_id("DELTA-",[before.to_dict() if before else None,after.to_dict() if after else None])
            deltas.append(RuleDelta(delta_id=identifier,kind=kind,before=before,after=after,changed_fields=changed,
                                    explanation=kind.value+" rule "+key+(": "+", ".join(changed) if changed else "")))
        return DeltaAnalysis(deltas=tuple(deltas),presentation_only_rule_ids=tuple(presentation))
