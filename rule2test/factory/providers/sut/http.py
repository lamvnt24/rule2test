"""HTTP JSON adapter with bounded response, socket timeout and no redirects/retries."""
import json, urllib.request, urllib.error
from urllib.parse import urlsplit
from factory.providers.sut.base import SUTAdapter
from factory.models import Action
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
        if not 0<timeout_seconds<=300: raise ProviderError("Invalid SUT timeout")
        payload=json.dumps({"inputs":[item.to_dict() for item in inputs]},ensure_ascii=False).encode("utf-8")
        request=urllib.request.Request(self.endpoint,data=payload,headers={"Content-Type":"application/json","Accept":"application/json"},method="POST")
        try:
            with self.opener.open(request,timeout=timeout_seconds) as response:
                if response.status!=200: raise ProviderError("SUT returned unexpected status")
                if response.headers.get_content_type()!="application/json": raise ProviderError("SUT must return application/json")
                data=response.read(self.max_response_bytes+1)
            if len(data)>self.max_response_bytes: raise ProviderError("SUT response exceeds size limit")
            action=Action.from_json(data.decode("utf-8"))
            if action.formula is not None: raise ProviderError("SUT must return concrete actual, not a formula")
            return action
        except urllib.error.HTTPError as exc:
            code=exc.code
            exc.close()
            raise ProviderError("SUT HTTP status "+str(code)) from None
        except (urllib.error.URLError,TimeoutError,OSError) as exc:
            raise ProviderError("SUT connection or timeout error") from None
        except (ValidationError,UnicodeError) as exc:
            raise ProviderError("SUT response violates Action schema") from None
