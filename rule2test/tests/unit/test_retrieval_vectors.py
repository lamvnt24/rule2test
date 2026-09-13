import unittest,importlib.util,math
from factory.providers.embedding.mock import MockEmbeddingProvider,tokens
from factory.providers.vector.base import PythonVectorBackend,normalized
from factory.providers.vector.faiss import FaissVectorBackend
from factory.exceptions import ValidationError

class RetrievalVectorTests(unittest.TestCase):
    def test_embedding_is_deterministic_normalized_and_labeled_mock(self):
        p=MockEmbeddingProvider();self.assertTrue(p.simulated)
        a=p.embed(("age eligibility","加入年齢",""))
        self.assertEqual(a,p.embed(("age eligibility","加入年齢","")))
        self.assertAlmostEqual(sum(x*x for x in a[0]),1.0)
        self.assertEqual(a[2],(0.0,)*128);self.assertTrue(tokens("加入年齢"))
    def test_bad_dimensions_nan_infinity_and_integer_values_rejected(self):
        for vector in ((1.0,), (float("nan"),0.0),(float("inf"),0.0),(1,0)):
            with self.subTest(vector=vector),self.assertRaises(ValidationError):normalized(vector,2)
    def test_cosine_order_and_zero_vector(self):
        scores=PythonVectorBackend().scores(((2.0,0.0),(0.0,2.0),(-1.0,0.0),(0.0,0.0)),(1.0,0.0))
        self.assertEqual(scores,(1.0,0.0,-1.0,0.0))
    @unittest.skipUnless(importlib.util.find_spec("faiss"),"Install requirements-retrieval.txt")
    def test_real_faiss_matches_python_scores(self):
        vectors=MockEmbeddingProvider().embed(("age boundary","claim amount","免責金額",""))
        query=MockEmbeddingProvider().embed(("age",))[0]
        expected=PythonVectorBackend().scores(vectors,query)
        actual=FaissVectorBackend().scores(vectors,query)
        for a,b in zip(actual,expected):self.assertAlmostEqual(a,b,places=6)
    def test_empty_vector_index(self):
        self.assertEqual(PythonVectorBackend().scores((),(1.0,0.0)),())
        self.assertEqual(FaissVectorBackend().scores((),(1.0,0.0)),())

class OllamaEmbeddingTests(unittest.TestCase):
    def test_http_contract_and_normalization(self):
        import json
        from io import BytesIO
        from unittest.mock import patch
        from factory.providers.embedding.ollama import OllamaEmbeddingProvider
        body=json.dumps(dict(model="local:v1",embeddings=[[3,4]])).encode()
        with patch("factory.providers.embedding.ollama.build_opener") as build:
            build.return_value.open.return_value=BytesIO(body)
            provider=OllamaEmbeddingProvider("local:v1",2,"weights-v1")
            self.assertEqual(provider.embed(("age",)),((0.6,0.8),))
            req=build.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url,"http://127.0.0.1:11434/api/embed")
            self.assertFalse(json.loads(req.data)["truncate"]);self.assertFalse(provider.simulated)
    def test_bad_output_and_transport_error_are_safe(self):
        import json
        from io import BytesIO
        from unittest.mock import patch
        from factory.providers.embedding.ollama import OllamaEmbeddingProvider
        from factory.exceptions import ProviderError
        provider=OllamaEmbeddingProvider("local:v1",2,"weights-v1")
        for body in (b"bad",json.dumps(dict(model="other",embeddings=[[1,0]])).encode(),
            json.dumps(dict(model="local:v1",embeddings=[[True,0]])).encode(),
            json.dumps(dict(model="local:v1",embeddings=[[1]])).encode()):
            with patch("factory.providers.embedding.ollama.build_opener") as build:
                build.return_value.open.return_value=BytesIO(body)
                with self.assertRaises(ProviderError):provider.embed(("age",))
        with patch("factory.providers.embedding.ollama.build_opener") as build:
            build.return_value.open.side_effect=TimeoutError("secret")
            with self.assertRaises(ProviderError) as ctx:provider.embed(("age",))
            self.assertNotIn("secret",str(ctx.exception))
    def test_configuration_identity_and_empty_input(self):
        from factory.providers.embedding.factory import configured_embedding
        from factory.providers.embedding.ollama import OllamaEmbeddingProvider
        from factory.exceptions import ConfigurationError
        self.assertTrue(configured_embedding({}).simulated)
        with self.assertRaises(ConfigurationError):configured_embedding({"RULE2TEST_EMBEDDING_PROVIDER":"ollama"})
        with self.assertRaises(ConfigurationError):configured_embedding({"RULE2TEST_EMBEDDING_PROVIDER":"unknown"})
        one=OllamaEmbeddingProvider("local:v1",2,"revision-a")
        two=OllamaEmbeddingProvider("local:v1",2,"revision-b")
        self.assertNotEqual(one.identity,two.identity);self.assertEqual(one.embed(()),())
