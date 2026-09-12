"""Self-contained evidence snapshot with revision-consistent approval links."""
from dataclasses import dataclass
import hashlib
from .common import Model, Metadata, require, nonempty
from .rule import Rule
from .test_case import TestCase
from .approval import Approval, ApprovalDecision, SubjectKind
from .execution import Execution
from .decision_table import DecisionTable

def content_hash(model: Model) -> str:
    return hashlib.sha256(model.to_json().encode("utf-8")).hexdigest()

@dataclass(frozen=True,kw_only=True)
class Evidence(Model):
    evidence_id: str
    run_id: str
    rules: tuple[Rule,...]
    tests: tuple[TestCase,...]
    approvals: tuple[Approval,...]
    executions: tuple[Execution,...]
    metadata: Metadata
    decision_tables: tuple[DecisionTable,...] = ()
    def __post_init__(self):
        super().__post_init__();nonempty(self.evidence_id,"evidence_id");nonempty(self.run_id,"run_id")
        require(bool(self.executions),"Evidence requires executions")
        rules={(r.rule_id,r.version):r for r in self.rules}
        tests={(t.test_id,t.revision):t for t in self.tests}
        approvals={a.approval_id:a for a in self.approvals}
        require(len(rules)==len(self.rules) and len(tests)==len(self.tests) and len(approvals)==len(self.approvals),"Duplicate evidence entity")
        require(len({e.execution_id for e in self.executions})==len(self.executions),"Duplicate execution ID")
        for test in self.tests:
            for ref in test.rules:
                rule=rules.get((ref.rule_id,ref.version))
                require(rule is not None and content_hash(rule)==ref.rule_hash,"Rule reference/hash mismatch")
        tables={content_hash(t):t for t in self.decision_tables}
        require(len(tables)==len(self.decision_tables),"Duplicate decision table snapshot")
        for e in self.executions:
            if e.decision_table_hash is not None:
                require(e.decision_table_hash in tables,"Missing execution decision table snapshot")
                table=tables[e.decision_table_hash]
                require(set(row.rule for row in table.rows)==set(e.rules),"Execution/table rule references differ")
            require(e.run_id==self.run_id,"Execution run mismatch")
            test=tests.get((e.test_id,e.test_revision))
            require(test is not None,"Execution references missing test revision")
            require(content_hash(test)==e.test_hash,"Execution test hash mismatch")
            require(e.expected==test.expected and e.rules==test.rules,"Execution differs from test snapshot")
            approval=approvals.get(e.approval_id)
            require(approval is not None,"Execution requires approval snapshot")
            require(approval.decision is ApprovalDecision.APPROVED and approval.subject_kind is SubjectKind.TEST,"Execution requires approved test")
            require((approval.subject_id,approval.revision)==(test.test_id,test.revision),"Approval revision mismatch")
            require(approval.content_hash==e.test_hash,"Approval hash mismatch")
            require(approval.decided_at<=e.started_at,"Approval must precede execution")
            require(e.finished_at<=self.metadata.created_at,"Evidence cannot precede execution")
    @property
    def fingerprint(self):
        return content_hash(self)
