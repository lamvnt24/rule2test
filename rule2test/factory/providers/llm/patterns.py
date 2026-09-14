"""Pattern-based rule reading exposed through the extraction provider contract. No model, no network."""
import json
from factory.services.rule_interpreter import interpret,rows,INTERPRETER

LABELS={"v1":"Current rule","v2":"New rule"}

class PatternRuleProvider:
    name="pattern"
    model=INTERPRETER
    simulated=True  # not a live model; the workspace labels the result as pattern-based

    def extract(self,request,*,system_prompt,timeout_seconds):
        sources={s.label:s for s in request.sources}
        policies=[];rules={"v1":[],"v2":[]};citations=[];issues=[];shapes={}
        for label,version in (("v1",1),("v2",2)):
            source=sources.get(label)
            if source is None:continue
            finding,questions=interpret(source.text)
            if questions:
                issues.extend(LABELS[label]+": "+question for question in questions);continue
            shapes[label]=finding.shape
            policy,rule_rows=rows(finding,label,version)
            citations.append(dict(path="/policies/"+str(len(policies)),document_id=source.document_id,
                line=finding.conditions[0].line,quote=finding.conditions[0].quote))
            policies.append(policy)
            for index,(row,found) in enumerate(zip(rule_rows,finding.conditions)):
                rules[label].append(row)
                citations.append(dict(path="/rules_"+label+"/"+str(index),document_id=source.document_id,line=found.line,quote=found.quote))
        if not issues and len(shapes)==2 and shapes["v1"]!=shapes["v2"]:
            issues.append("The current rule is a "+shapes["v1"]+" rule but the new rule is a "+shapes["v2"]+" rule; both versions must describe the same rule.")
        if issues:
            return json.dumps(dict(status="needs_clarification",issues=issues[:20],policies=[],rules_v1=[],rules_v2=[],citations=[]),ensure_ascii=False)
        return json.dumps(dict(status="ready",issues=[],policies=policies,rules_v1=rules["v1"],rules_v2=rules["v2"],citations=citations),ensure_ascii=False)
