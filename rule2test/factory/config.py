"""Environment configuration. No .env auto-loading or secret logging."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from factory.exceptions import ConfigurationError

@dataclass(frozen=True,kw_only=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    database_path: Path = Path("data/factory.db")
    llm_provider: str = "mock"
    openai_api_key: str | None = field(default=None,repr=False)
    openai_model: str | None = None
    ollama_model: str | None = None
    request_timeout_seconds: int = 60
    def __post_init__(self):
        for name in ("host","llm_provider"):
            if type(getattr(self,name)) is not str: raise ConfigurationError(name+" must be a string")
        for name in ("openai_api_key","openai_model","ollama_model"):
            if getattr(self,name) is not None and type(getattr(self,name)) is not str: raise ConfigurationError(name+" must be a string")
        if self.host not in ("127.0.0.1","localhost","::1"): raise ConfigurationError("Base project must bind loopback")
        if type(self.port) is not int or not 1<=self.port<=65535: raise ConfigurationError("Invalid port")
        if not isinstance(self.database_path,Path): raise ConfigurationError("database_path must be Path")
        if type(self.request_timeout_seconds) is not int or not 1<=self.request_timeout_seconds<=300: raise ConfigurationError("Timeout must be 1..300 seconds")
        if self.llm_provider not in ("mock","openai","ollama"): raise ConfigurationError("Unknown LLM provider")
        if self.llm_provider=="openai" and (not self.openai_api_key or not self.openai_api_key.strip() or not self.openai_model or not self.openai_model.strip()):
            raise ConfigurationError("OpenAI provider requires key and model")
        if self.llm_provider=="ollama" and (not self.ollama_model or not self.ollama_model.strip()):
            raise ConfigurationError("Ollama provider requires model")
    @classmethod
    def from_env(cls, env=None):
        env=os.environ if env is None else env
        try:
            return cls(host=env.get("RULE2TEST_HOST","127.0.0.1"),port=int(env.get("RULE2TEST_PORT","8000")),
                database_path=Path(env.get("RULE2TEST_DATABASE_PATH","data/factory.db")),
                llm_provider=env.get("RULE2TEST_LLM_PROVIDER","mock"),
                openai_api_key=env.get("OPENAI_API_KEY"),openai_model=env.get("OPENAI_MODEL"),
                ollama_model=env.get("OLLAMA_MODEL"),
                request_timeout_seconds=int(env.get("RULE2TEST_REQUEST_TIMEOUT_SECONDS","60")))
        except (ValueError,TypeError) as exc: raise ConfigurationError(str(exc)) from exc
