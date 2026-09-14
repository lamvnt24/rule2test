"""Exact-fixture replay, NOT language understanding. Unknown inputs require clarification."""
import json
from factory.parsers.templates import demo_payload
from factory.providers.llm.synthetic import SOURCE_PAIRS

class MockLLMProvider:
    name="mock"
    model="synthetic-replay-v1"
    simulated=True
    @staticmethod
    def _lines(text):
        # The prompt and the citation validator are both line-oriented via splitlines(), so the
        # fixture match ignores the line terminator too. A CRLF checkout of the same fixture on
        # Windows must replay identically; anything that is not a known fixture still does not.
        return text.splitlines()

    def extract(self,request,*,system_prompt,timeout_seconds):
        sources={s.label:s for s in request.sources}
        profile=next((key for key,pair in SOURCE_PAIRS.items()
            if self._lines(sources["v1"].text)==self._lines(pair[0])
            and self._lines(sources["v2"].text)==self._lines(pair[1])),None)
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
