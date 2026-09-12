"""Execution records distinguish business failures from infrastructure errors."""
from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum
from .common import Model, RuleReference, require, nonempty, aware, sha256
from .rule import Action
class ExecutionStatus(str,Enum):
    PASS="pass"
    FAIL="fail"
    ERROR="error"
    SKIPPED="skipped"

@dataclass(frozen=True,kw_only=True)
class Execution(Model):
    execution_id: str
    run_id: str
    test_id: str
    test_revision: int
    test_hash: str
    rules: tuple[RuleReference,...]
    approval_id: str
    expected: Action
    actual: Action | None
    status: ExecutionStatus
    adapter: str
    started_at: datetime
    finished_at: datetime
    error: str | None = None
    decision_table_hash: str | None = None
    evaluation_date: date | None = None
    def __post_init__(self):
        super().__post_init__()
        if self.decision_table_hash is not None: sha256(self.decision_table_hash,"decision_table_hash")
        require(self.expected.formula is None,"Execution expected must be concrete")
        require(self.actual is None or self.actual.formula is None,"Execution actual must be concrete")
        for key in ("execution_id","run_id","test_id","approval_id","adapter"): nonempty(getattr(self,key),key)
        require(self.test_revision>0,"Test revision must be positive");sha256(self.test_hash)
        require(bool(self.rules),"Execution requires rule references")
        aware(self.started_at);aware(self.finished_at);require(self.finished_at>=self.started_at,"Execution ends before it starts")
        if self.status in (ExecutionStatus.PASS,ExecutionStatus.FAIL):
            require(self.actual is not None and self.error is None,"Completed test requires actual and no infrastructure error")
            require((self.expected==self.actual)==(self.status is ExecutionStatus.PASS),"Status contradicts expected/actual")
        else:
            require(self.actual is None,"Error/skipped execution has no actual")
            require(self.error is not None and bool(self.error.strip()),"Error/skipped execution requires reason")
