"""Exact-fixture replay, NOT language understanding. Unknown inputs require clarification."""
import json
from factory.parsers.templates import demo_payload
from factory.providers.llm.synthetic import SOURCE_PAIRS

class MockLLMProvider:
    name="mock"
    model="synthetic-replay-v1"
    simulated=True
    def extract(self,request,*,system_prompt,timeout_seconds):
        sources={s.label:s for s in request.sources}
        profile=next((key for key,pair in SOURCE_PAIRS.items()
            if sources["v1"].text==pair[0] and sources["v2"].text==pair[1]),None)
        if profile is None:
            return json.dumps(dict(status="needs_clarification",
                issues=["Mock only replays the three exact synthetic source pairs; review or configure a real provider."],
                policies=[],rules_v1=[],rules_v2=[],citations=[]))
        template=demo_payload(profile)
        result=dict(status="ready",issues=[],policies=template["policies"],rules_v1=template["rules_v1"],
            rules_v2=template["rules_v2"],citations=[])
        for index,policy in enumerate(result["policies"]):
            source=sources[policy["label"]]
            result["citations"].append(dict(path="/policies/"+str(index),document_id=source.document_id,line=3,quote=source.text.splitlines()[2]))
        for label in ("v1","v2"):
            source=sources[label];quote=source.text.splitlines()[1]
            for index,row in enumerate(result["rules_"+label]):
                row["quote"]=quote
                result["citations"].append(dict(path="/rules_"+label+"/"+str(index),document_id=source.document_id,line=2,quote=quote))
        return json.dumps(result,ensure_ascii=False)
