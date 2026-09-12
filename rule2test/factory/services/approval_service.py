"""Human review commands operate on stored tests, never client-supplied hashes."""
from dataclasses import replace
from datetime import datetime,timezone
from uuid import uuid4
from factory.models import Approval,ApprovalDecision,SubjectKind,WorkflowStatus,content_hash
from factory.models.common import nonempty
from factory.exceptions import ConflictError,NotFoundError
from factory.validators.test_validator import validate_approved_test
from factory.engines.oracle_engine import OracleEngine
from ._workflow_store import WorkflowStore

class ApprovalService(WorkflowStore):
    def review(self,workflow_id,expected_revision,*,test_id,test_revision,decision,reviewer,reason):
        nonempty(reviewer,"reviewer");nonempty(reason,"reason")
        with self.db.transaction() as c:
            w=self.load(c,workflow_id,expected_revision)
            if w.status not in (WorkflowStatus.IN_REVIEW,WorkflowStatus.APPROVED):raise ConflictError("Workflow is not in review")
            test=next((t for t in w.tests if t.test_id==test_id),None)
            if test is None:raise NotFoundError("Test is not part of this workflow")
            if type(test_revision) is not int or test.revision!=test_revision:raise ConflictError("Stale test revision")
            approval=Approval(approval_id=str(uuid4()),subject_kind=SubjectKind.TEST,subject_id=test.test_id,
                revision=test.revision,content_hash=content_hash(test),reviewer=reviewer,decision=decision,
                decided_at=datetime.now(timezone.utc),reason=reason)
            if decision is ApprovalDecision.APPROVED:
                validate_approved_test(test,approval,w.new_table,datetime.now(timezone.utc))
                if test.expected!=OracleEngine().evaluate(w.new_table,w.new_rules,test.inputs,as_of=w.new_as_of):
                    raise ConflictError("Expected differs from oracle; edit and review a new test revision")
            approvals=tuple(a for a in w.approvals if a.subject_id!=test_id)+(approval,)
            return self.commit(c,w,replace(w,approvals=approvals,status=WorkflowStatus.IN_REVIEW,evidence_id=None),
                               reviewer,"test_review",reason)

    @staticmethod
    def ready(w):
        decisions={a.subject_id:a for a in w.approvals}
        selected=[]
        for test in w.tests:
            a=decisions.get(test.test_id)
            if a is None or a.revision!=test.revision or a.content_hash!=content_hash(test):
                raise ConflictError("Every current test must have a current review decision")
            if a.decision is ApprovalDecision.CHANGES_REQUESTED:raise ConflictError("Requested changes remain unresolved")
            if a.decision is ApprovalDecision.APPROVED:
                validate_approved_test(test,a,w.new_table,datetime.now(timezone.utc))
                if test.expected!=OracleEngine().evaluate(w.new_table,w.new_rules,test.inputs,as_of=w.new_as_of):
                    raise ConflictError("Approved expected result is stale")
                selected.append((test,a))
        if not selected:raise ConflictError("At least one approved test is required")
        return tuple(selected)

    def finalize(self,workflow_id,expected_revision,*,reviewer,reason):
        with self.db.transaction() as c:
            w=self.load(c,workflow_id,expected_revision)
            if w.status is not WorkflowStatus.IN_REVIEW:raise ConflictError("Finalize requires IN_REVIEW")
            self.ready(w)
            return self.commit(c,w,replace(w,status=WorkflowStatus.APPROVED),reviewer,"review_finalized",reason)
