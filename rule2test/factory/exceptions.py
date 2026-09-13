"""Stable application error vocabulary, independent of HTTP."""
class FactoryError(Exception):
    """Base error safe to translate at a transport boundary."""
class ValidationError(FactoryError, ValueError):
    """Input violates the domain contract."""
class ConfigurationError(FactoryError, ValueError):
    """Application configuration is invalid."""
class NotFoundError(FactoryError):
    """Referenced entity does not exist."""
class ConflictError(FactoryError):
    """Revision or state transition conflicts with persisted state."""
class ProviderError(FactoryError):
    """External provider failed. kind classifies the failure; the message stays free of provider payloads."""
    KINDS=("unreachable","timeout","http_status","oversized_response","malformed_json","schema_rejected",
           "model_mismatch","capability_unsupported","redirect_blocked","invalid_request","unclassified")
    def __init__(self,message,*,kind="unclassified",remediation=""):
        super().__init__(message)
        if kind not in self.KINDS:raise ValueError("Unknown provider failure kind: "+str(kind))
        self.kind=kind;self.remediation=remediation
    def to_dict(self):
        return dict(error=str(self),kind=self.kind,remediation=self.remediation,retried=False,fallback_used=False)
