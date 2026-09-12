"""Review decisions bind an exact revision and content hash."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from .common import Model, require, nonempty, sha256, aware
class ApprovalDecision(str,Enum):
    APPROVED="approved"
    REJECTED="rejected"
    CHANGES_REQUESTED="changes_requested"
class SubjectKind(str,Enum):
    RULE="rule"
    TEST="test"
    DECISION_TABLE="decision_table"

@dataclass(frozen=True,kw_only=True)
class Approval(Model):
    approval_id: str
    subject_kind: SubjectKind
    subject_id: str
    revision: int
    content_hash: str
    reviewer: str
    decision: ApprovalDecision
    decided_at: datetime
    reason: str
    def __post_init__(self):
        super().__post_init__()
        for key in ("approval_id","subject_id","reviewer","reason"): nonempty(getattr(self,key),key)
        require(self.revision>0,"Revision must be positive");sha256(self.content_hash);aware(self.decided_at)
