"""AI readiness and evaluation contracts; all test transports are explicitly mocked."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch, Mock
from contextlib import redirect_stdout, redirect_stderr
from factory.ai_config import AIProfile,read_profile
from factory.services.ai_readiness_service import inventory,readiness,require_ready
from factory.exceptions import ValidationError,ProviderError
from factory.repositories.connection import Database
from factory.providers.llm.mock import MockLLMProvider
from factory.providers.llm.prompt import document_message
from scripts.evaluate_ai import load_dataset,request_for,extraction_checks,evaluate,main

ROOT=Path(__file__).resolve().parents[2]
def live_profile():
    return AIProfile(mode="ollama",extraction_model="chat:latest",extraction_digest="a"*64,
                     suggestion_model="chat:latest",suggestion_digest="a"*64,
                     embedding_model="embed:latest",embedding_digest="b"*64,embedding_dimensions=3)
def listing():
    return dict(available=True,models=[dict(name="chat:latest",digest="a"*64),
                                       dict(name="embed:latest",digest="b"*64)])

class AIReadinessTests(unittest.TestCase):
    def test_profile_rejects_unknown_fields_and_mixed_claims(self):
        with self.assertRaises(ValidationError):AIProfile.from_dict(dict(mode="mock",api_key="secret"))
        with self.assertRaises(ValidationError):AIProfile(mode="mock",extraction_model="live")
        with self.assertRaises(ValidationError):replace(live_profile(),embedding_digest="unversioned")
        with self.assertRaises(ValidationError):AIProfile(mode="mock",timeout_seconds=True)
        self.assertEqual(AIProfile(mode="mock").providers()[0].simulated,True)
    def test_profile_roundtrip_and_environment_pin(self):
        profile=live_profile()
        self.assertEqual(AIProfile.from_json(profile.to_json()),profile)
        self.assertEqual(profile.environment()["RULE2TEST_EMBEDDING_REVISION"],"b"*64)
        self.assertEqual(profile.environment()["RULE2TEST_EXTRACTION_DIGEST"],"a"*64)
    def test_mock_readiness_makes_no_network_or_inference_calls(self):
        with patch("factory.services.ai_readiness_service.inventory") as network:
            result=readiness(AIProfile(mode="mock"),probe=True)
            network.assert_not_called()
        self.assertEqual(result["status"],"mock_only")
        self.assertFalse(result["live_ready"])
    def test_inventory_failure_is_sanitized(self):
        with patch("factory.services.ai_readiness_service.build_opener",side_effect=RuntimeError("private body")):
            result=inventory()
        self.assertFalse(result["available"])
        self.assertNotIn("private body",json.dumps(result))
    def test_metadata_match_is_not_inference_readiness(self):
        with patch("factory.services.ai_readiness_service.inventory",return_value=listing()):
            report=readiness(live_profile())
        self.assertEqual(report["status"],"configured")
        self.assertFalse(report["live_ready"])
        self.assertEqual(report["probes"],[])
    def test_changed_digest_blocks_before_probe(self):
        changed=listing();changed["models"][0]["digest"]="c"*64
        with patch("factory.services.ai_readiness_service.inventory",return_value=changed),patch.object(AIProfile,"providers") as providers:
            self.assertEqual(readiness(live_profile(),probe=True)["status"],"blocked")
            providers.assert_not_called()
            with self.assertRaises(ProviderError):require_ready(live_profile())
    def test_probes_require_chat_and_embedding_success(self):
        extraction=Mock();extraction.complete.return_value='{"ready":true}'
        suggestion=Mock();suggestion.client.complete.return_value='{"ready":true}'
        embedding=Mock();embedding.embed.return_value=((1.0,0.0,0.0),(0.0,1.0,0.0))
        with patch("factory.services.ai_readiness_service.inventory",return_value=listing()),patch.object(
            AIProfile,"providers",return_value=(extraction,embedding,suggestion)):
            self.assertTrue(readiness(live_profile(),probe=True)["live_ready"])
            embedding.embed.side_effect=RuntimeError("private")
            report=readiness(live_profile(),probe=True)
            self.assertFalse(report["live_ready"]);self.assertEqual(report["status"],"blocked")
            self.assertNotIn("private",json.dumps(report))
    def test_duplicate_json_profile_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"profile.json";path.write_text('{"mode":"mock","mode":"ollama"}')
            with self.assertRaises(ValueError):read_profile(path)

class AIEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix="rule2test-ai-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.dataset=load_dataset(ROOT/"data"/"ai_eval"/"cases.json")
    def test_truth_is_excluded_from_provider_message(self):
        case=copy.deepcopy(self.dataset["cases"][0])
        case["expected"]["secret_gold"]="DO_NOT_SEND_ANSWER_KEY"
        message=document_message(request_for(case))
        self.assertNotIn("DO_NOT_SEND_ANSWER_KEY",message)
        self.assertEqual(set(json.loads(message)),{"documents"})
    def test_mock_is_measured_as_limited_replay_not_real_accuracy(self):
        result=extraction_checks(Database(self.root/"test.db"),MockLLMProvider(),self.dataset,30)
        self.assertTrue(result["simulated"])
        self.assertEqual((result["matched"],result["total"]),(5,10))
        self.assertEqual(result["categories"]["paraphrase"]["matched"],0)
    def test_wrong_old_version_truth_cannot_pass_on_correct_new_version(self):
        data=copy.deepcopy(self.dataset)
        data["cases"]=data["cases"][:1]
        data["cases"][0]["expected"]["old"]["conditions"][1]["value"]=59
        result=extraction_checks(Database(self.root/"wrong.db"),MockLLMProvider(),data,30)
        self.assertEqual(result["matched"],0)
    def test_provider_failures_receive_no_semantic_credit(self):
        provider=MockLLMProvider()
        provider.extract=Mock(side_effect=RuntimeError("provider body"))
        result=extraction_checks(Database(self.root/"error.db"),provider,self.dataset,30)
        self.assertEqual(result["provider_errors"],10)
        self.assertEqual(result["matched"],0)
        self.assertNotIn("provider body",json.dumps(result))
    def test_blocked_live_configuration_never_creates_database(self):
        with patch("scripts.evaluate_ai.readiness",return_value=dict(status="blocked")):
            result=evaluate(live_profile(),self.dataset,self.root)
        self.assertEqual(result["status"],"blocked")
        self.assertEqual(result["stages"],{})
        self.assertFalse((self.root/"evaluation.db").exists())
    def test_evaluation_artifacts_do_not_approve_extracted_proposals(self):
        result=evaluate(AIProfile(mode="mock"),self.dataset,self.root)
        self.assertEqual(result["status"],"completed")
        self.assertTrue(result["simulated"])
        self.assertTrue(result["stages"]["suggestions"]["target_unmodified"])
        self.assertFalse(result["stages"]["suggestions"]["automatic_attachment"])
        from factory.repositories.connection import Database
        with Database(self.root/"evaluation.db").read() as c:
            for row in result["stages"]["extraction"]["results"]:
                count=c.execute("SELECT count(*) FROM wf_objects WHERE kind='extraction_review' AND entity_id=?",
                                (row["proposal_id"],)).fetchone()[0]
                self.assertEqual(count,0)
    def test_existing_run_directory_is_not_overwritten(self):
        marker=self.root/"marker.txt";marker.write_text("retain")
        with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            status=main(["--profile",str(ROOT/"data"/"ai_profiles"/"mock.json"),"--run-dir",str(self.root)])
        self.assertEqual(status,1);self.assertEqual(marker.read_text(),"retain")
    def test_dataset_duplicate_ids_and_identical_sources_rejected(self):
        for change in ("duplicate","same-source"):
            data=copy.deepcopy(self.dataset)
            if change=="duplicate":data["cases"][1]["id"]=data["cases"][0]["id"]
            else:data["cases"][0]["v2"]=data["cases"][0]["v1"]
            path=self.root/"invalid.json";path.write_text(json.dumps(data),encoding="utf-8")
            with self.assertRaises(ValidationError):load_dataset(path)

if __name__=="__main__":unittest.main()
