"""Provider boundary: return untrusted JSON text; never construct approvals."""
from typing import Protocol
from factory.models.extraction import ExtractionRequest

class LLMProvider(Protocol):
    name: str
    model: str
    simulated: bool
    def extract(self,request: ExtractionRequest,*,system_prompt: str,timeout_seconds: int) -> str:
        """Enforce transport timeout; return raw output for independent validation."""
        ...
