"""Classify transport failures into a stable kind. Never retries, repairs output or falls back to mock."""
import socket,urllib.error
from factory.exceptions import ProviderError,ValidationError

REMEDIATION={
    "unreachable":"Start the local provider service and confirm the endpoint; nothing is downloaded or started automatically.",
    "timeout":"Raise RULE2TEST_AI_TIMEOUT_SECONDS (1..120) or choose a smaller model; no automatic retry is performed.",
    "http_status":"Inspect the provider service log for the rejected request; the response body is deliberately not shown.",
    "oversized_response":"Reduce the source size or choose a model with shorter output; the bounded read protects the host.",
    "malformed_json":"The model did not return a single JSON object; no prose stripping or output repair is attempted.",
    "schema_rejected":"Output parsed but violated the required contract; inspect the stored proposal issues.",
    "model_mismatch":"Use the exact installed model tag from scripts/ai_doctor.py; digests and tags must match.",
    "capability_unsupported":"The selected model does not support this operation; choose a chat or embedding model accordingly.",
    "redirect_blocked":"Redirects are disabled by design; point the setting at the provider endpoint directly.",
    "invalid_request":"The host refused to send the request; correct the configured values before calling again.",
    "unclassified":"Inspect the diagnostics log for this trace; no automatic recovery was attempted.",
}

def failure(kind,message):
    return ProviderError(message,kind=kind,remediation=REMEDIATION[kind])

def classify(exc,message):
    """Map a transport exception to a ProviderError without leaking its payload or address."""
    if isinstance(exc,ProviderError):return exc
    if isinstance(exc,urllib.error.HTTPError):
        code=exc.code
        try:exc.close()
        except Exception:pass
        return failure("http_status",message+" (HTTP "+str(code)+")")
    if isinstance(exc,(socket.timeout,TimeoutError)):return failure("timeout",message)
    if isinstance(exc,urllib.error.URLError):
        return failure("timeout" if isinstance(exc.reason,(socket.timeout,TimeoutError)) else "unreachable",message)
    if isinstance(exc,(ConnectionError,socket.gaierror)):return failure("unreachable",message)
    if isinstance(exc,ValidationError):return failure("schema_rejected",message)
    if isinstance(exc,(UnicodeError,ValueError)):return failure("malformed_json",message)
    if isinstance(exc,OSError):return failure("unreachable",message)
    return failure("unclassified",message)
