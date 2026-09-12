"""Build evidence from durable approved snapshots and completed execution journals."""
from dataclasses import replace
from datetime import datetime,timezone
from uuid import uuid4
from factory.models import Evidence,Metadata,WorkflowStatus
from factory.exceptions import ConflictError
from ._workflow_store import WorkflowStore
from .approval_service import ApprovalService

class EvidenceService(WorkflowStore):
    def create(self,workflow_id,expected_revision,*,actor):
        with self.db.transaction() as c:
            w=self.load(c,workflow_id,expected_revision)
            if w.status is WorkflowStatus.EVIDENCED:
                return self.evidence.get(c,workflow_id,w.evidence_id,1)
            if w.status is not WorkflowStatus.EXECUTED or not w.last_run_id:raise ConflictError("Evidence requires a completed execution")
            run=self.workflows.get_run(c,workflow_id,w.last_run_id)
            if run.status!="completed":raise ConflictError("Interrupted runs cannot become completed evidence")
            approved=self.workflows.get(c,workflow_id,workflow_id,run.workflow_revision)
            selected=ApprovalService.ready(approved)
            expected_ids={(t.test_id,t.revision) for t,a in selected}
            if {(e.test_id,e.test_revision) for e in run.executions}!=expected_ids:
                raise ConflictError("Execution journal is incomplete")
            evidence=Evidence(evidence_id=str(uuid4()),run_id=run.run_id,rules=approved.new_rules,
                tests=tuple(t for t,a in selected),approvals=tuple(a for t,a in selected),executions=run.executions,
                decision_tables=(approved.new_table,),metadata=Metadata(created_at=datetime.now(timezone.utc),created_by=actor))
            self.evidence.put(c,workflow_id,evidence)
            self.commit(c,w,replace(w,status=WorkflowStatus.EVIDENCED,evidence_id=evidence.evidence_id),
                        actor,"evidence_created","Evidence persisted from approved snapshot and execution journal")
            return evidence

    def get_evidence(self,workflow_id,evidence_id):
        with self.db.read() as c:return self.evidence.get(c,workflow_id,evidence_id,1)
