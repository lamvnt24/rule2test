"""Explicit all-mock or all-Ollama profiles; unknown fields and mixed modes are rejected."""
from dataclasses import dataclass
from pathlib import Path
from factory.models.common import Model, require, nonempty, sha256
from factory.parsers.common import strict_json
from factory.providers.llm.factory import configured_provider
from factory.providers.embedding.factory import configured_embedding
from factory.providers.llm.test_suggestions import MockTestSuggestionProvider, OllamaTestSuggestionProvider

@dataclass(frozen=True, kw_only=True)
class AIProfile(Model):
    mode: str
    extraction_model: str = ""
    extraction_digest: str = ""
    suggestion_model: str = ""
    suggestion_digest: str = ""
    embedding_model: str = ""
    embedding_digest: str = ""
    embedding_device: str = "auto"
    embedding_dimensions: int = 128
    timeout_seconds: int = 60
    schema_version: int = 1

    def __post_init__(self):
        super().__post_init__()
        require(self.schema_version == 1, "Unsupported AI profile version")
        require(self.mode in ("mock", "ollama"), "Mode must be mock or ollama")
        require(self.embedding_device in ("auto","cpu"), "Embedding device must be auto or cpu")
        require(1 <= self.timeout_seconds <= 120, "Timeout must be 1..120 seconds")
        require(1 <= self.embedding_dimensions <= 4096, "Dimensions must be 1..4096")
        if self.mode == "ollama":
            for role in ("extraction", "suggestion", "embedding"):
                nonempty(getattr(self, role + "_model"), role + " model")
                sha256(getattr(self, role + "_digest"), role + " digest")
        else:
            require(not any(getattr(self, role + suffix) for role in ("extraction","suggestion","embedding")
                            for suffix in ("_model","_digest")), "Mock profile cannot declare live models")
            require(self.embedding_dimensions == 128, "Mock embeddings have 128 dimensions")

    def environment(self):
        return dict(RULE2TEST_EXTRACTION_PROVIDER=self.mode,
                    RULE2TEST_EXTRACTION_MODEL=self.extraction_model,
                    RULE2TEST_EXTRACTION_DIGEST=self.extraction_digest,
                    RULE2TEST_SUGGESTION_PROVIDER=self.mode,
                    RULE2TEST_SUGGESTION_MODEL=self.suggestion_model,
                    RULE2TEST_SUGGESTION_DIGEST=self.suggestion_digest,
                    RULE2TEST_EMBEDDING_PROVIDER=self.mode,
                    RULE2TEST_EMBEDDING_MODEL=self.embedding_model,
                    RULE2TEST_EMBEDDING_DIMENSIONS=str(self.embedding_dimensions),
                    RULE2TEST_EMBEDDING_DEVICE=self.embedding_device,
                    RULE2TEST_EMBEDDING_REVISION=self.embedding_digest,
                    RULE2TEST_AI_TIMEOUT_SECONDS=str(self.timeout_seconds))

    def providers(self):
        env = self.environment()
        extraction = configured_provider(env)
        embedding = configured_embedding(env)
        suggestion = MockTestSuggestionProvider() if self.mode == "mock" else OllamaTestSuggestionProvider(self.suggestion_model)
        if self.mode == "ollama":
            embedding.timeout_seconds = self.timeout_seconds
        return extraction, embedding, suggestion

def read_profile(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(16385)
    require(len(raw) <= 16384, "AI profile exceeds 16 KiB")
    return AIProfile.from_dict(strict_json(raw.decode("utf-8")))

