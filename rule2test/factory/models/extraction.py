"""Immutable extraction proposals, source inputs and hash-bound human decisions."""
from dataclasses import dataclass
import hashlib
from .common import Model,Metadata,require,nonempty,sha256

MAX_SOURCE_BYTES=64*1024
MAX_RESPONSE_BYTES=256*1024

@dataclass(frozen=True,kw_only=True)
class SourceText(Model):
    document_id: str
    label: str
    text: str
    def __post_init__(self):
        super().__post_init__();nonempty(self.document_id,"document_id");nonempty(self.text,"text")
        require(self.label in ("v1","v2"),"Expected v1 or v2 source label")
        require(len(self.text.encode("utf-8"))<=MAX_SOURCE_BYTES,"Source exceeds 64 KiB")
        require(len(self.text.splitlines())<=1000,"Source exceeds 1000 lines")
    @property
    def document_hash(self):return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

@dataclass(frozen=True,kw_only=True)
class ExtractionRequest(Model):
    sources: tuple[SourceText,...]
    existing_tests_json: str = "[]"
    def __post_init__(self):
        super().__post_init__()
        labels={s.label for s in self.sources}
        require(len(self.sources)==len(labels) and labels in ({"v1","v2"},{"v2"}),"Supply the new rule as v2, optionally with the current rule as v1")
        require(len({s.document_id for s in self.sources})==len(self.sources),"Source IDs must be unique")
        require(len({s.document_hash for s in self.sources})==len(self.sources),"Source versions have identical bytes; supply distinct versioned documents")
        require(len(self.existing_tests_json.encode("utf-8"))<=MAX_RESPONSE_BYTES,"Existing tests exceed 256 KiB")
    @property
    def baseline_known(self):
        """False when only the new rule was supplied: tests can be checked against it, but nothing can be said about what changed."""
        return any(s.label=="v1" for s in self.sources)

@dataclass(frozen=True,kw_only=True)
class ExtractionProposal(Model):
    proposal_id: str
    request: ExtractionRequest
    provider: str
    model: str
    simulated: bool
    prompt_version: str
    prompt_hash: str
    response_json: str
    status: str
    issues: tuple[str,...]
    elapsed_ms: int
    metadata: Metadata
    def __post_init__(self):
        super().__post_init__()
        for name in ("proposal_id","provider","model","prompt_version"):nonempty(getattr(self,name),name)
        sha256(self.prompt_hash)
        require(self.status in ("pending_review","needs_clarification","invalid_output","provider_error"),"Invalid extraction state")
        require(0<=self.elapsed_ms,"Negative latency")
        require(len(self.response_json.encode("utf-8"))<=MAX_RESPONSE_BYTES,"Response exceeds limit")
        require((self.status=="pending_review")== (not self.issues),"Only reviewable proposals have no blocking issues")
        for issue in self.issues:nonempty(issue,"issue")

@dataclass(frozen=True,kw_only=True)
class ExtractionReview(Model):
    proposal_id: str
    proposal_hash: str
    decision: str
    reason: str
    metadata: Metadata
    def __post_init__(self):
        super().__post_init__();nonempty(self.proposal_id,"proposal_id");sha256(self.proposal_hash)
        require(self.decision in ("approved","rejected"),"Expected approved or rejected")
        nonempty(self.reason,"reason")

@dataclass(frozen=True,kw_only=True)
class ExtractionPromotion(Model):
    proposal_id: str
    proposal_hash: str
    review_hash: str
    workflow_id: str
    metadata: Metadata
    def __post_init__(self):
        super().__post_init__()
        nonempty(self.proposal_id,"proposal_id");nonempty(self.workflow_id,"workflow_id")
        sha256(self.proposal_hash);sha256(self.review_hash)
