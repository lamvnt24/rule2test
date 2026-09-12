"""Persisted workflow snapshots and execution journals."""
from dataclasses import dataclass
from datetime import date,datetime
from .common import Model,Metadata,WorkflowStatus,require,nonempty,aware
from .import_document import ImportDocument
from .rule import Rule
from .decision_table import DecisionTable
from .test_case import TestCase
from .approval import Approval
from .execution import Execution
from .analysis import DeltaAnalysis,ImpactRecord,GapAnalysis,CoverageReport

@dataclass(frozen=True,kw_only=True)
class WorkflowAnalysis(Model):
    delta: DeltaAnalysis
    impact: tuple[ImpactRecord,...]
    gaps: GapAnalysis
    baseline_coverage: CoverageReport

@dataclass(frozen=True,kw_only=True)
class Workflow(Model):
    workflow_id: str
    revision: int
    status: WorkflowStatus
    old_table: DecisionTable
    old_rules: tuple[Rule,...]
    new_table: DecisionTable
    new_rules: tuple[Rule,...]
    existing_tests: tuple[TestCase,...]
    tests: tuple[TestCase,...]
    approvals: tuple[Approval,...]
    metadata: Metadata
    old_as_of: date | None = None
    new_as_of: date | None = None
    analysis: WorkflowAnalysis | None = None
    active_run_id: str | None = None
    last_run_id: str | None = None
    evidence_id: str | None = None
    documents: tuple[ImportDocument,...] = ()
    def to_dict(self):
        result=super().to_dict()
        if not self.documents:result.pop("documents")
        return result
    def __post_init__(self):
        super().__post_init__();nonempty(self.workflow_id,"workflow_id")
        require(self.revision>0,"Workflow revision must be positive")
        require(len({d.document_hash for d in self.documents})==len(self.documents),"Duplicate source document")
        running=self.status in (WorkflowStatus.EXECUTING,WorkflowStatus.INTERRUPTED)
        require(running==(self.active_run_id is not None),"Run reservation must match workflow state")
        if self.status is WorkflowStatus.DRAFT:
            require(not self.tests and not self.approvals and self.analysis is None,"DRAFT cannot contain reviewed analysis")
        else:
            require(self.analysis is not None,"Non-draft workflow requires analysis")
        if self.status in (WorkflowStatus.EXECUTED,WorkflowStatus.EVIDENCED):
            require(self.last_run_id is not None,"Completed workflow requires a run")
        if self.status is WorkflowStatus.EVIDENCED:
            require(self.evidence_id is not None,"EVIDENCED requires evidence ID")
        require(len({t.test_id for t in self.tests})==len(self.tests),"One current revision per test is required")
        require(len({t.test_id for t in self.existing_tests})==len(self.existing_tests),"Duplicate existing test ID")

@dataclass(frozen=True,kw_only=True)
class ExecutionRun(Model):
    run_id: str
    workflow_id: str
    workflow_revision: int
    status: str
    executions: tuple[Execution,...]
    started_at: datetime
    error: str | None = None
    def __post_init__(self):
        super().__post_init__();nonempty(self.run_id,"run_id");nonempty(self.workflow_id,"workflow_id")
        require(self.status in ("running","completed","interrupted"),"Invalid run status")
        require(self.workflow_revision>0,"Run requires a positive workflow revision")
        aware(self.started_at)
        require(all(e.run_id==self.run_id and e.started_at>=self.started_at for e in self.executions),"Journal execution context mismatch")
        if self.status=="completed":require(bool(self.executions),"Completed run cannot be empty")
        require(len({e.test_id for e in self.executions})==len(self.executions),"Duplicate test execution")