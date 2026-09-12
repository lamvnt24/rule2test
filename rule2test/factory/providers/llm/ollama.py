"""Optional local Ollama adapter. No model download, cloud call or mock fallback."""
import json
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from factory.exceptions import ConfigurationError,ProviderError
from factory.models.extraction import MAX_RESPONSE_BYTES
from factory.parsers.common import strict_json
from .prompt import document_message

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ProviderError("Provider redirects are disabled")

class OllamaLLMProvider:
    name="ollama"
    simulated=False
    def __init__(self,model):
        if type(model) is not str or not model.strip():raise ConfigurationError("Set RULE2TEST_EXTRACTION_MODEL to an installed Ollama model")
        self.model=model
    def extract(self,request,*,system_prompt,timeout_seconds):
        body=json.dumps(dict(model=self.model,stream=False,format="json",
            messages=[dict(role="system",content=system_prompt),dict(role="user",content=document_message(request))],
            options=dict(temperature=0)),ensure_ascii=False).encode("utf-8")
        req=Request("http://127.0.0.1:11434/api/chat",data=body,headers={"Content-Type":"application/json"},method="POST")
        try:
            opener=build_opener(ProxyHandler({}),NoRedirect())
            with opener.open(req,timeout=timeout_seconds) as response:
                data=response.read(MAX_RESPONSE_BYTES+1)
            if len(data)>MAX_RESPONSE_BYTES:raise ProviderError("Provider response exceeds 256 KiB")
            payload=strict_json(data.decode("utf-8"))
            if type(payload) is not dict or payload.get("done") is not True:raise ProviderError("Provider response is incomplete")
            message=payload.get("message")
            if type(message) is not dict or message.get("tool_calls"):raise ProviderError("Tool calls are unsupported")
            content=message.get("content")
            if type(content) is not str or not content.strip():raise ProviderError("Provider returned no JSON content")
            return content
        except ProviderError:raise
        except Exception as exc:raise ProviderError("Ollama request failed; check the local server and configured model") from exc
