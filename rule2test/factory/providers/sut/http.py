"""HTTP JSON adapter with bounded response, socket timeout and no redirects/retries."""
import json, urllib.request, urllib.error
from urllib.parse import urlsplit
from factory.providers.sut.base import SUTAdapter
from factory.providers.failure import classify, failure
from factory.models import Action
from factory.observability import metrics, span
from factory.exceptions import ConfigurationError, ProviderError, ValidationError

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl): return None

class HttpSUTAdapter(SUTAdapter):
    def __init__(self,endpoint,*,max_response_bytes=65536):
        try:
            url=urlsplit(endpoint)
            port=url.port
        except (ValueError,TypeError) as exc: raise ConfigurationError("Invalid SUT endpoint") from exc
        if url.scheme not in ("http","https") or not url.hostname or url.username or url.password or url.fragment:
            raise ConfigurationError("Expected HTTP(S) endpoint without credentials or fragment")
        if type(max_response_bytes) is not int or not 1<=max_response_bytes<=1000000:
            raise ConfigurationError("Invalid response size limit")
        self.endpoint=endpoint;self.max_response_bytes=max_response_bytes
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
    @property
    def name(self): return "http-sut-v1"
    def execute(self,inputs,*,timeout_seconds):
        if not 0<timeout_seconds<=300: raise failure("invalid_request","Invalid SUT timeout")
        payload=json.dumps({"inputs":[item.to_dict() for item in inputs]},ensure_ascii=False).encode("utf-8")
        request=urllib.request.Request(self.endpoint,data=payload,headers={"Content-Type":"application/json","Accept":"application/json"},method="POST")
        with span("http_sut_execute",component="sut",provider="http-sut-v1",count=len(inputs),timeout_seconds=timeout_seconds):
            try:
                with self.opener.open(request,timeout=timeout_seconds) as response:
                    if response.status!=200: raise failure("http_status","SUT returned unexpected status")
                    if response.headers.get_content_type()!="application/json": raise failure("schema_rejected","SUT must return application/json")
                    data=response.read(self.max_response_bytes+1)
                if len(data)>self.max_response_bytes: raise failure("oversized_response","SUT response exceeds size limit")
                action=Action.from_json(data.decode("utf-8"))
                if action.formula is not None: raise failure("schema_rejected","SUT must return concrete actual, not a formula")
                metrics.increment("provider_calls_total",provider="http-sut",operation="execute",outcome="ok")
                return action
            except urllib.error.HTTPError as exc:
                code=exc.code
                exc.close()
                error=failure("http_status","SUT HTTP status "+str(code))
                metrics.increment("provider_calls_total",provider="http-sut",operation="execute",outcome="error",kind=error.kind)
                raise error from None
            except Exception as exc:
                error=classify(exc,"SUT connection or timeout error" if isinstance(exc,(urllib.error.URLError,TimeoutError,OSError))
                    else "SUT response violates Action schema")
                metrics.increment("provider_calls_total",provider="http-sut",operation="execute",outcome="error",kind=error.kind)
                raise error from None
