"""Application-scoped SQLite services, server-owned provider configuration and local diagnostics."""
import os,platform,sqlite3,sys
from decimal import Decimal
from pathlib import Path
from factory.repositories.connection import Database
from factory.services.workflow_service import WorkflowService
from factory.services.approval_service import ApprovalService
from factory.services.evidence_service import EvidenceService
from factory.services.extraction_service import ExtractionService
from factory.services.knowledge_service import KnowledgeService
from factory.services.retrieval_generation_service import RetrievalGenerationService
from factory.providers.llm.factory import configured_provider
from factory.providers.embedding.factory import configured_embedding
from factory.providers.llm.test_suggestions import MockTestSuggestionProvider,OllamaTestSuggestionProvider
from factory.providers.vector.base import PythonVectorBackend
from factory.providers.vector.faiss import FaissVectorBackend
from factory.providers.sut.mock import MockSUTAdapter
from factory.engines.insurance_engine import InsuranceEngine
from factory.parsers._builder import decimal
from factory.exceptions import ConfigurationError
from factory.observability import logger as diagnostics_log,metrics
from .schemas.requests import body_keys

from factory.paths import resources,database
ROOT=resources()  # Read-only bundled assets; writable paths come from factory.paths.
DEFAULT_AI_TIMEOUT_SECONDS=60
# Reported by /api/v1/diagnostics. Secrets are listed only as set/unset and never by value.
SETTINGS=("RULE2TEST_EXTRACTION_PROVIDER","RULE2TEST_EXTRACTION_MODEL","RULE2TEST_EXTRACTION_DIGEST",
    "RULE2TEST_SUGGESTION_PROVIDER","RULE2TEST_SUGGESTION_MODEL","RULE2TEST_SUGGESTION_DIGEST",
    "RULE2TEST_EMBEDDING_PROVIDER","RULE2TEST_EMBEDDING_MODEL","RULE2TEST_EMBEDDING_REVISION",
    "RULE2TEST_EMBEDDING_DIMENSIONS","RULE2TEST_EMBEDDING_DEVICE","RULE2TEST_VECTOR_BACKEND",
    "RULE2TEST_AI_TIMEOUT_SECONDS","RULE2TEST_LOG_LEVEL","RULE2TEST_LOG_FILE")
SECRETS=("OPENAI_API_KEY","OLLAMA_MODEL","OPENAI_MODEL")

class Application:
    def __init__(self,db_path):
        self.db=Database(db_path)
        self.workflow=WorkflowService(self.db);self.review=ApprovalService(self.db);self.evidence=EvidenceService(self.db)

    def extraction(self,*,provider=False):
        return ExtractionService(self.db,configured_provider() if provider else None)

    def knowledge(self):
        name=os.environ.get("RULE2TEST_VECTOR_BACKEND","python")
        if name not in ("python","faiss"):raise ConfigurationError("Vector backend must be python or faiss")
        return KnowledgeService(self.db,embedding=configured_embedding(),backend=FaissVectorBackend() if name=="faiss" else PythonVectorBackend())

    def retrieval(self,*,provider=False):
        selected=None
        if provider:
            name=os.environ.get("RULE2TEST_SUGGESTION_PROVIDER","mock")
            if name=="mock":selected=MockTestSuggestionProvider()
            elif name=="ollama":selected=OllamaTestSuggestionProvider(os.environ.get("RULE2TEST_SUGGESTION_MODEL",""))
            else:raise ConfigurationError("Suggestion provider must be mock or ollama")
        return RetrievalGenerationService(self.db,provider=selected,knowledge=self.knowledge())

    @staticmethod
    def adapter(config):
        body_keys(config,("profile","fault","min_age","max_age","claim_threshold","deductible","currency"))
        return MockSUTAdapter(InsuranceEngine(profile=config["profile"],fault=config["fault"],
            min_age=config["min_age"],max_age=config["max_age"],claim_threshold=decimal(config["claim_threshold"]),
            deductible=decimal(config["deductible"]),currency=config["currency"]))

    @staticmethod
    def providers():
        return dict(extraction=os.environ.get("RULE2TEST_EXTRACTION_PROVIDER","mock"),
            embedding=os.environ.get("RULE2TEST_EMBEDDING_PROVIDER","mock"),
            suggestions=os.environ.get("RULE2TEST_SUGGESTION_PROVIDER","mock"),
            vector=os.environ.get("RULE2TEST_VECTOR_BACKEND","python"),sut="independent mock",
            reviewer_identity="self-declared")


    @staticmethod
    def ai_timeout():
        try:
            timeout=int(os.environ.get("RULE2TEST_AI_TIMEOUT_SECONDS",str(DEFAULT_AI_TIMEOUT_SECONDS)))
            if not 1<=timeout<=120:raise ValueError()
            return timeout
        except ValueError as exc:raise ConfigurationError("AI timeout must be 1..120 seconds") from exc

    @staticmethod
    def ai_status():
        from factory.ai_config import AIProfile
        from factory.services.ai_readiness_service import inventory,readiness
        configured=Application.providers()
        roles=[configured[k] for k in ("extraction","embedding","suggestions")]
        models={role:os.environ.get("RULE2TEST_"+prefix+"_MODEL","") for role,prefix in
                (("extraction","EXTRACTION"),("embedding","EMBEDDING"),("suggestions","SUGGESTION"))}
        if set(roles)=={"ollama"}:
            try:
                profile=AIProfile(mode="ollama",extraction_model=models["extraction"],
                    extraction_digest=os.environ.get("RULE2TEST_EXTRACTION_DIGEST",""),
                    suggestion_model=models["suggestions"],suggestion_digest=os.environ.get("RULE2TEST_SUGGESTION_DIGEST",""),
                    embedding_model=models["embedding"],embedding_digest=os.environ.get("RULE2TEST_EMBEDDING_REVISION",""),
                    embedding_dimensions=int(os.environ.get("RULE2TEST_EMBEDDING_DIMENSIONS","0")),
                    embedding_device=os.environ.get("RULE2TEST_EMBEDDING_DEVICE","auto"),
                    timeout_seconds=Application.ai_timeout())
                result=readiness(profile)
            except (ValueError,TypeError):
                result=dict(status="unpinned_configuration",live_ready=False,inventory=inventory(),
                    note="Use ai_doctor.py to create a digest-pinned profile, then run_ai_workspace.py.")
        else:
            result=dict(status="mock_only" if set(roles)=={"mock"} else "mixed_configuration",live_ready=False,
                inventory=inventory(),note="Metadata inspection only. No inference, downloads or automatic provider switch.")
        return dict(configured=configured,models=models,readiness=result)

    @staticmethod
    def optional_dependencies():
        available={}
        for name,extra in (("openpyxl","excel"),("defusedxml","excel"),("faiss","retrieval"),("playwright","browser")):
            try:
                __import__(name);available[name]=dict(installed=True,extra=extra)
            except Exception:available[name]=dict(installed=False,extra=extra)
        return available

    @staticmethod
    def effective_configuration():
        """Every setting the process actually uses, with secrets reported as set/unset only."""
        declared={name:os.environ.get(name,"") for name in SETTINGS}
        return dict(settings={k:(v if v else "(default)") for k,v in declared.items()},
            secrets={name:("set" if os.environ.get(name,"").strip() else "unset") for name in SECRETS},
            defaults=dict(ai_timeout_seconds=DEFAULT_AI_TIMEOUT_SECONDS,vector_backend="python",providers="mock"),
            runtime=dict(python=platform.python_version(),sqlite=sqlite3.sqlite_version,platform=sys.platform),
            note="Process environment only. The .env.example template is never loaded automatically.")

    def diagnostics(self):
        with self.db.read() as connection:
            versions=sorted(row[0] for row in connection.execute("SELECT version FROM wf_schema_migrations"))
            workflows=connection.execute("SELECT count(*) FROM wf_heads").fetchone()[0]
        return dict(schema_version=1,providers=self.providers(),configuration=self.effective_configuration(),
            optional_dependencies=self.optional_dependencies(),logging=diagnostics_log.configuration(),
            database=dict(path=self.db.path.name,migrations=versions,workflows=workflows,
                writable=os.access(self.db.path.parent,os.W_OK)),
            metrics=metrics.snapshot(),
            scope="Local demo diagnostics for this process only.",
            limitation="Counters reset on restart, are never persisted or exported, and never contain document text, prompts, reviewer names or session tokens.")
