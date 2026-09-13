"""Ollama gateway adapter: local JSON mode or explicit -cloud tag with host validation."""
import json
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from factory.exceptions import ConfigurationError,ProviderError
from factory.models.extraction import MAX_RESPONSE_BYTES
from factory.observability import metrics,span
from factory.parsers.common import strict_json
from factory.providers.failure import classify,failure
from .prompt import document_message

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise failure("redirect_blocked","Provider redirects are disabled")

class OllamaLLMProvider:
    name="ollama"
    simulated=False
    def __init__(self,model):
        if type(model) is not str or not model.strip():raise ConfigurationError("Set RULE2TEST_EXTRACTION_MODEL to an installed Ollama model")
        self.model=model
    def extract(self,request,*,system_prompt,timeout_seconds):
        return self.complete(system_prompt=system_prompt,user_message=document_message(request),timeout_seconds=timeout_seconds)
    def complete(self,*,system_prompt,user_message,timeout_seconds):
        cloud=self.model.endswith("-cloud")
        instructions=system_prompt
        if cloud:
            instructions+="\nReturn only the requested JSON object, without Markdown fences or explanatory prose."
        payload=dict(model=self.model,stream=False,
            messages=[dict(role="system",content=instructions),dict(role="user",content=user_message)],
            options=dict(temperature=0))
        if not cloud:payload["format"]="json"
        body=json.dumps(payload,ensure_ascii=False).encode("utf-8")
        req=Request("http://127.0.0.1:11434/api/chat",data=body,headers={"Content-Type":"application/json"},method="POST")
        with span("ollama_chat",component="provider",provider="ollama",model=self.model,bytes=len(body),timeout_seconds=timeout_seconds):
            try:
                opener=build_opener(ProxyHandler({}),NoRedirect())
                with opener.open(req,timeout=timeout_seconds) as response:
                    data=response.read(MAX_RESPONSE_BYTES+1)
                if len(data)>MAX_RESPONSE_BYTES:raise failure("oversized_response","Provider response exceeds 256 KiB")
                payload=strict_json(data.decode("utf-8"))
                if type(payload) is not dict or payload.get("done") is not True:raise failure("schema_rejected","Provider response is incomplete")
                message=payload.get("message")
                if type(message) is not dict or message.get("tool_calls"):raise failure("capability_unsupported","Tool calls are unsupported")
                content=message.get("content")
                if type(content) is not str or not content.strip():raise failure("schema_rejected","Provider returned no JSON content")
                metrics.increment("provider_calls_total",provider="ollama",operation="chat",outcome="ok")
                return content
            except Exception as exc:
                error=classify(exc,"Ollama request failed; check the local server and configured model")
                metrics.increment("provider_calls_total",provider="ollama",operation="chat",outcome="error",kind=error.kind)
                raise error from exc
