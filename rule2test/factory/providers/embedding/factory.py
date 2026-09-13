"""Select mock by default; no silent fallback from a real embedding model."""
import os
from factory.exceptions import ConfigurationError
from .mock import MockEmbeddingProvider
from .ollama import OllamaEmbeddingProvider

def configured_embedding(env=None):
    env=os.environ if env is None else env
    name=env.get("RULE2TEST_EMBEDDING_PROVIDER","mock")
    if name=="mock":return MockEmbeddingProvider()
    if name!="ollama":raise ConfigurationError("Embedding provider must be mock or ollama")
    try:
        return OllamaEmbeddingProvider(env.get("RULE2TEST_EMBEDDING_MODEL",""),int(env.get("RULE2TEST_EMBEDDING_DIMENSIONS","0")),
            env.get("RULE2TEST_EMBEDDING_REVISION",""),timeout_seconds=int(env.get("RULE2TEST_AI_TIMEOUT_SECONDS","30")),device=env.get("RULE2TEST_EMBEDDING_DEVICE","auto"))
    except (ValueError,TypeError) as exc:raise ConfigurationError("Configure embedding model, dimensions, revision and timeout") from exc

