"""Explicit extraction configuration; mock is the offline default."""
import os
from factory.exceptions import ConfigurationError
from .mock import MockLLMProvider
from .ollama import OllamaLLMProvider

def configured_provider(env=None):
    env=os.environ if env is None else env
    name=env.get("RULE2TEST_EXTRACTION_PROVIDER","mock")
    if name=="mock":return MockLLMProvider()
    if name=="ollama":return OllamaLLMProvider(env.get("RULE2TEST_EXTRACTION_MODEL",""))
    raise ConfigurationError("Extraction provider must be mock or ollama; no automatic fallback")
