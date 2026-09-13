"""Immutable retrieval corpus and grounded test proposal batches."""
from dataclasses import dataclass
from .common import Model,Metadata,require,nonempty,sha256
from .rule import Rule
from .test_case import TestCase
import math

@dataclass(frozen=True,kw_only=True)
class KnowledgeRecord(Model):
    record_id: str
    workflow_id: str
    kind: str
    table_hash: str
    proof_id: str
    proof_hash: str
    fields: tuple[str,...]
    rule_ids: tuple[str,...]
    text: str
    rule: Rule | None = None
    test: TestCase | None = None
    def __post_init__(self):
        super().__post_init__()
        for key in ("record_id","workflow_id","proof_id","text"):nonempty(getattr(self,key),key)
        sha256(self.table_hash);sha256(self.proof_hash)
        require(self.kind in ("rule","test"),"Unknown knowledge kind")
        require((self.rule is not None)==(self.kind=="rule") and (self.test is not None)==(self.kind=="test"),"Knowledge snapshot mismatch")

@dataclass(frozen=True,kw_only=True)
class KnowledgeVector(Model):
    values: tuple[float,...]
    def __post_init__(self):
        super().__post_init__();require(bool(self.values) and all(math.isfinite(x) for x in self.values),"Vector must be nonempty and finite")

@dataclass(frozen=True,kw_only=True)
class KnowledgeIndex(Model):
    index_id: str
    embedding_identity: str
    dimensions: int
    simulated: bool
    records: tuple[KnowledgeRecord,...]
    vectors: tuple[KnowledgeVector,...]
    metadata: Metadata
    def __post_init__(self):
        super().__post_init__();nonempty(self.index_id,"index_id");nonempty(self.embedding_identity,"embedding identity")
        require(1<=self.dimensions<=4096,"Invalid dimensions")
        require(len(self.records)==len(self.vectors)<=500,"Index supports at most 500 records")
        require(len({r.record_id for r in self.records})==len(self.records),"Duplicate record ID")
        require(all(len(v.values)==self.dimensions for v in self.vectors),"Index dimension mismatch")

@dataclass(frozen=True,kw_only=True)
class RetrievalHit(Model):
    record: KnowledgeRecord
    score: float
    lexical_score: float
    vector_score: float
    rule_id_match: bool

@dataclass(frozen=True,kw_only=True)
class RetrievalBatch(Model):
    batch_id: str
    workflow_id: str
    workflow_revision: int
    table_hash: str
    index_id: str
    index_hash: str
    query: str
    hits: tuple[RetrievalHit,...]
    provider: str
    simulated: bool
    raw_response: str
    candidates: tuple[TestCase,...]
    duplicate_count: int
    metadata: Metadata
    def __post_init__(self):
        super().__post_init__()
        for key in ("batch_id","workflow_id","index_id","provider","query"):nonempty(getattr(self,key),key)
        sha256(self.table_hash);sha256(self.index_hash)
        require(self.workflow_revision>0 and self.duplicate_count>=0,"Invalid batch counters")
        require(len(self.hits)<=20 and len(self.candidates)<=20 and len(self.raw_response.encode())<=262144,"Batch exceeds bounds")
