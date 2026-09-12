"""Shared unit-of-work helpers for workflow, review and evidence services."""
from dataclasses import replace
from datetime import datetime,timezone
from factory.models import Metadata
from factory.models.common import nonempty
from factory.exceptions import ConflictError
from factory.repositories.workflow_repository import WorkflowRepository
from factory.repositories.rule_repository import RuleRepository,DecisionTableRepository
from factory.repositories.test_repository import TestRepository
from factory.repositories.approval_repository import ApprovalRepository
from factory.repositories.evidence_repository import EvidenceRepository

class WorkflowStore:
    def __init__(self,database):
        self.db=database;self.workflows=WorkflowRepository()
        self.rules=RuleRepository();self.tables=DecisionTableRepository()
        self.tests=TestRepository();self.approvals=ApprovalRepository();self.evidence=EvidenceRepository()

    def load(self,c,workflow_id,expected_revision,*,allow_running=False):
        workflow=self.workflows.current(c,workflow_id)
        if type(expected_revision) is not int or workflow.revision!=expected_revision:
            raise ConflictError("Stale workflow revision; reload before editing or running")
        if workflow.active_run_id and not allow_running:raise ConflictError("Workflow has an active or unreconciled run")
        return workflow

    def commit(self,c,old,new,actor,event,detail):
        nonempty(actor,"actor");nonempty(detail,"reason")
        new=replace(new,revision=old.revision+1,metadata=Metadata(created_at=datetime.now(timezone.utc),created_by=actor))
        self.persist(c,new)
        self.workflows.save(c,new,old.revision)
        self.workflows.event(c,new,actor,event,detail)
        return new

    def persist(self,c,workflow):
        scope=workflow.workflow_id
        for rule in workflow.old_rules+workflow.new_rules:self.rules.put(c,scope,rule)
        for table in (workflow.old_table,workflow.new_table):self.tables.put(c,scope,table)
        for test in workflow.existing_tests+workflow.tests:self.tests.put(c,scope,test)
        for approval in workflow.approvals:self.approvals.put(c,scope,approval)

    def get(self,workflow_id):
        with self.db.read() as c:return self.workflows.current(c,workflow_id)
