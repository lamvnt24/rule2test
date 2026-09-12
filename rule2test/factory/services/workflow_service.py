"""Durable workflow orchestration. No client may supply execution rules or expected values."""
from dataclasses import replace
from datetime import datetime,timezone
from uuid import uuid4
from factory.models import Metadata,WorkflowStatus,TestOrigin,content_hash
from factory.models.workflow import Workflow,WorkflowAnalysis,ExecutionRun
from factory.models.common import require,nonempty
from factory.exceptions import ConflictError,NotFoundError
from factory.validators.rule_validator import validate_table
from factory.services._support import unique_tests,references
from factory.engines.test_executor import TestExecutor
from factory.repositories.document_repository import DocumentRepository
from ._workflow_store import WorkflowStore
from .approval_service import ApprovalService
from .rule_delta_service import RuleDeltaService
from .impact_service import ImpactService
from .gap_service import GapService
from .generation_service import GenerationService
from .coverage_service import CoverageService

class WorkflowService(WorkflowStore):
    def prepare_create(self,old_table,old_rules,new_table,new_rules,existing_tests=(),*,actor,old_as_of=None,new_as_of=None,source_documents=()):
        nonempty(actor,"actor")
        validate_table(old_table,old_rules,old_as_of);validate_table(new_table,new_rules,new_as_of)
        RuleDeltaService().compare(old_rules,new_rules);unique_tests(existing_tests)
        for test in existing_tests:
            require(set(test.rules)<=set(references(old_rules)),"Existing tests must reference the supplied old snapshots")
        for document,data in source_documents:DocumentRepository.validate(document,data)
        if source_documents:
            documents={(d.document_id,d.document_hash) for d,_ in source_documents}
            sources=tuple(s for r in old_rules+new_rules for s in r.sources)+tuple(s for t in existing_tests for s in t.sources)
            require(all((s.document_id,s.document_hash) in documents for s in sources),"Source reference is not archived")
        w=Workflow(workflow_id=str(uuid4()),revision=1,status=WorkflowStatus.DRAFT,old_table=old_table,
            old_rules=old_rules,new_table=new_table,new_rules=new_rules,existing_tests=existing_tests,
            tests=(),approvals=(),metadata=Metadata(created_at=datetime.now(timezone.utc),created_by=actor),
            old_as_of=old_as_of,new_as_of=new_as_of,documents=tuple(d for d,_ in source_documents))
        return w

    def persist_created(self,c,w,*,actor,source_documents=()):
        require(w.revision==1 and w.status is WorkflowStatus.DRAFT,"Expected a new draft")
        require(w.documents==tuple(d for d,_ in source_documents),"Document manifest mismatch")
        self.persist(c,w);self.workflows.save(c,w,None);self.workflows.event(c,w,actor,"created","Workflow created")
        for document,data in source_documents:DocumentRepository().put(c,w.workflow_id,document,data)

    def create(self,old_table,old_rules,new_table,new_rules,existing_tests=(),*,actor,old_as_of=None,new_as_of=None,source_documents=()):
        w=self.prepare_create(old_table,old_rules,new_table,new_rules,existing_tests,actor=actor,
            old_as_of=old_as_of,new_as_of=new_as_of,source_documents=source_documents)
        with self.db.transaction() as c:self.persist_created(c,w,actor=actor,source_documents=source_documents)
        return w

    def analyze(self,workflow_id,expected_revision,*,actor):
        with self.db.transaction() as c:
            w=self.load(c,workflow_id,expected_revision)
            if w.status is not WorkflowStatus.DRAFT:raise ConflictError("Analysis requires DRAFT")
            gaps=GapService().analyze(w.new_table,w.new_rules,w.existing_tests,as_of=w.new_as_of)
            meta=Metadata(created_at=datetime.now(timezone.utc),created_by=actor)
            generator=GenerationService()
            candidates=generator.generate(w.new_table,w.new_rules,gaps,metadata=meta,as_of=w.new_as_of)
            revisions=generator.rebase(w.new_table,w.new_rules,w.existing_tests,metadata=meta,as_of=w.new_as_of)
            analysis=WorkflowAnalysis(delta=RuleDeltaService().compare(w.old_rules,w.new_rules),
                impact=ImpactService().analyze(w.old_table,w.old_rules,w.new_table,w.new_rules,w.existing_tests,
                    old_as_of=w.old_as_of,new_as_of=w.new_as_of),gaps=gaps,
                baseline_coverage=CoverageService().measure(w.new_table,w.new_rules,w.existing_tests,as_of=w.new_as_of))
            return self.commit(c,w,replace(w,tests=revisions+candidates.candidates,analysis=analysis,status=WorkflowStatus.ANALYZED),
                               actor,"analyzed","Generated revision and candidate proposals; no approvals created")

    def start_review(self,workflow_id,expected_revision,*,actor):
        with self.db.transaction() as c:
            w=self.load(c,workflow_id,expected_revision)
            if w.status is not WorkflowStatus.ANALYZED:raise ConflictError("Review requires ANALYZED")
            return self.commit(c,w,replace(w,status=WorkflowStatus.IN_REVIEW),actor,"review_started","Review opened")

    def edit_test(self,workflow_id,expected_revision,*,test_id,test_revision,inputs,expected,actor,reason,title=None):
        nonempty(reason,"reason")
        with self.db.transaction() as c:
            w=self.load(c,workflow_id,expected_revision)
            if w.status not in (WorkflowStatus.IN_REVIEW,WorkflowStatus.APPROVED,WorkflowStatus.EXECUTED,WorkflowStatus.EVIDENCED):
                raise ConflictError("Test editing requires a reviewed workflow")
            current=next((t for t in w.tests if t.test_id==test_id),None)
            if current is None:raise NotFoundError("Test not found")
            if type(test_revision) is not int or test_revision!=current.revision:raise ConflictError("Stale test revision")
            edited=replace(current,revision=current.revision+1,inputs=inputs,expected=expected,
                title=current.title if title is None else title,origin=TestOrigin.HUMAN,rationale=reason,
                obligation_ids=(),metadata=Metadata(created_at=datetime.now(timezone.utc),created_by=actor))
            tests=tuple(edited if t.test_id==test_id else t for t in w.tests)
            approvals=tuple(a for a in w.approvals if a.subject_id!=test_id)
            return self.commit(c,w,replace(w,tests=tests,approvals=approvals,status=WorkflowStatus.IN_REVIEW,evidence_id=None),
                               actor,"test_edited",reason)

    def revise_rules(self,workflow_id,expected_revision,*,table,rules,actor,reason,as_of=None):
        with self.db.transaction() as c:
            w=self.load(c,workflow_id,expected_revision)
            validate_table(table,rules,as_of);RuleDeltaService().compare(w.new_rules,rules)
            require(table.table_id==w.new_table.table_id and table.version>w.new_table.version,
                    "A policy revision must retain the table ID and increase its version")
            existing=w.tests or w.existing_tests
            return self.commit(c,w,replace(w,old_table=w.new_table,old_rules=w.new_rules,old_as_of=w.new_as_of,
                new_table=table,new_rules=rules,new_as_of=as_of,existing_tests=existing,tests=(),approvals=(),
                analysis=None,status=WorkflowStatus.DRAFT,evidence_id=None),actor,"rules_revised",reason)

    def reopen_review(self,workflow_id,expected_revision,*,actor,reason):
        with self.db.transaction() as c:
            w=self.load(c,workflow_id,expected_revision)
            if w.status not in (WorkflowStatus.APPROVED,WorkflowStatus.EXECUTED,WorkflowStatus.EVIDENCED):
                raise ConflictError("Only a reviewed/completed workflow can be reopened")
            return self.commit(c,w,replace(w,status=WorkflowStatus.IN_REVIEW,approvals=(),evidence_id=None),
                               actor,"review_reopened",reason)

    def execute(self,workflow_id,expected_revision,adapter,*,actor,timeout_seconds=10):
        nonempty(actor,"actor")
        executor=TestExecutor(adapter,timeout_seconds=timeout_seconds)
        with self.db.transaction() as c:
            w=self.load(c,workflow_id,expected_revision)
            if w.status is not WorkflowStatus.APPROVED:raise ConflictError("Execution requires APPROVED")
            selected=ApprovalService.ready(w)  # Validate the entire suite before any outbound call.
            run=ExecutionRun(run_id=str(uuid4()),workflow_id=workflow_id,workflow_revision=w.revision,
                status="running",executions=(),started_at=datetime.now(timezone.utc))
            running=self.commit(c,w,replace(w,status=WorkflowStatus.EXECUTING,active_run_id=run.run_id),
                                actor,"execution_started","Approved suite reserved for one execution run")
            self.workflows.save_run(c,run,create=True)
        try:
            for test,approval in selected:
                # Recheck the run reservation immediately before the next external call.
                with self.db.read() as c:
                    current=self.workflows.current(c,workflow_id)
                    if current.active_run_id!=run.run_id or current.status is not WorkflowStatus.EXECUTING:
                        raise ConflictError("Run has been interrupted or replaced")
                execution=executor.execute(test,approval,w.new_table,w.new_rules,run_id=run.run_id,as_of=w.new_as_of)
                with self.db.transaction() as c:
                    current=self.workflows.current(c,workflow_id)
                    if current.active_run_id!=run.run_id or current.status is not WorkflowStatus.EXECUTING:
                        raise ConflictError("Run reservation no longer active; reconcile external effects")
                    run=replace(run,executions=run.executions+(execution,))
                    self.workflows.save_run(c,run)
            with self.db.transaction() as c:
                current=self.workflows.current(c,workflow_id)
                if current.active_run_id!=run.run_id:raise ConflictError("Run reservation changed")
                run=replace(run,status="completed");self.workflows.save_run(c,run)
                self.commit(c,current,replace(current,status=WorkflowStatus.EXECUTED,active_run_id=None,last_run_id=run.run_id,evidence_id=None),
                            actor,"execution_completed","Execution journal committed")
            return run
        except Exception:
            with self.db.transaction() as c:
                current=self.workflows.current(c,workflow_id)
                if current.active_run_id==run.run_id:
                    journal=self.workflows.get_run(c,workflow_id,run.run_id)
                    self.workflows.save_run(c,replace(journal,status="interrupted",error="Run interrupted; reconcile SUT effects before retry"))
                    self.commit(c,current,replace(current,status=WorkflowStatus.INTERRUPTED),
                                actor,"execution_interrupted","Explicit operator recovery is required; no automatic retry")
            raise

    def recover_interrupted_run(self,workflow_id,expected_revision,*,actor,reason):
        """Operator explicitly acknowledges external reconciliation; does not replay tests."""
        nonempty(reason,"reason")
        with self.db.transaction() as c:
            w=self.load(c,workflow_id,expected_revision,allow_running=True)
            if w.status not in (WorkflowStatus.EXECUTING,WorkflowStatus.INTERRUPTED) or not w.active_run_id:
                raise ConflictError("No active or interrupted run to recover")
            run=self.workflows.get_run(c,workflow_id,w.active_run_id)
            self.workflows.save_run(c,replace(run,status="interrupted",error="Operator recovery: "+reason))
            return self.commit(c,w,replace(w,status=WorkflowStatus.IN_REVIEW,active_run_id=None,approvals=(),evidence_id=None),
                               actor,"run_recovered",reason)

    def run(self,workflow_id,run_id):
        with self.db.read() as c:return self.workflows.get_run(c,workflow_id,run_id)

    def events(self,workflow_id):
        with self.db.read() as c:return self.workflows.events(c,workflow_id)