"""Explicit CPU embedding configuration must reach the Ollama request without changing global settings."""
import json,unittest
from io import BytesIO
from unittest.mock import patch
from factory.ai_config import AIProfile
from factory.providers.embedding.factory import configured_embedding
from factory.providers.embedding.ollama import OllamaEmbeddingProvider
from factory.exceptions import ValidationError

class CPUEmbeddingTests(unittest.TestCase):
    def test_cpu_request_and_distinct_index_identity(self):
        provider=OllamaEmbeddingProvider("embed:v1",2,"weights",device="cpu")
        auto=OllamaEmbeddingProvider("embed:v1",2,"weights")
        self.assertNotEqual(provider.identity,auto.identity)
        with patch("factory.providers.embedding.ollama.build_opener") as build:
            build.return_value.open.return_value=BytesIO(json.dumps(dict(model="embed:v1",embeddings=[[3,4]])).encode())
            self.assertEqual(provider.embed(("synthetic",)),((0.6,0.8),))
            self.assertEqual(json.loads(build.return_value.open.call_args.args[0].data)["options"],{"num_gpu":0})
    def test_profile_propagates_device(self):
        profile=AIProfile(mode="ollama",extraction_model="chat-cloud",extraction_digest="a"*64,
            suggestion_model="chat-cloud",suggestion_digest="a"*64,embedding_model="embed:v1",
            embedding_digest="b"*64,embedding_dimensions=2,embedding_device="cpu")
        self.assertEqual(configured_embedding(profile.environment()).device,"cpu")
        with self.assertRaises(ValidationError):AIProfile(mode="mock",embedding_device="invalid")

if __name__=="__main__":unittest.main()
