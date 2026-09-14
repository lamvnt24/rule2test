"""Link an imported test-case suite to confirmed rules: the rows become the workflow's existing tests.

Only rows a person confirmed (or the interpreter read without questions) and that use a field the
rules mention are linked; every other row is listed with the reason, never silently dropped.
"""
from datetime import datetime,timezone
from factory.models import Metadata,TestCase,TestKind,TestOrigin,SourceReference,ValueKind,Outcome,content_hash
from factory.models.common import nonempty
from factory.models.extraction import ExtractionPromotion
from factory.models.test_suite import SuiteLink,ExcludedRow
from factory.parsers.common import document
from factory.repositories.extraction_repository import PromotionRepository
from factory.repositories.suite_repository import SuiteLinkRepository,SCOPE
from factory.services._support import references
from factory.services.extraction_service import ExtractionService,SCOPE as EXTRACTION
from factory.services.suite_service import SuiteService
from factory.services.workflow_service import WorkflowService
from factory.validators.extraction_validator import compile_proposal
from factory.exceptions import ConflictError,NotFoundError
from .text_patterns import field_name

class LinkPromotionRepository(PromotionRepository):
    """Same audit record as a promotion, one per (proposal, workflow), so one rule proposal can serve several suites."""
    def identity(self,model):return model.proposal_id+"/"+model.workflow_id,1

def rule_fields(rules,tables=()):
    fields={c.field for r in rules for c in r.conditions}
    fields.update(a.formula.field for a in [t.default_action for t in tables]+[r.action for r in rules] if a.formula)
    return fields

def test_kind(row):
    if row.expected.outcome is Outcome.INVALID or any(x.value.kind not in (ValueKind.INTEGER,ValueKind.MONEY) for x in row.inputs):return TestKind.EXCEPTION
    return TestKind.NEGATIVE if row.expected.outcome is Outcome.DENY else TestKind.POSITIVE

def plan(suite,old_rules,new_rules,tables,metadata):
    """(linked TestCases, ExcludedRows). Pure: the same suite and rules always give the same plan."""
    fields=rule_fields(old_rules+new_rules,tables)
    refs=references(old_rules);linked=[];excluded=[]
    for row in suite.rows:
        if row.status=="skipped":
            excluded.append(ExcludedRow(row_id=row.row_id,title=row.title,reason="Skipped when the file was imported."));continue
        if row.status!="ready":
            excluded.append(ExcludedRow(row_id=row.row_id,title=row.title,reason="Not confirmed at import: "+(row.questions[0] if row.questions else "the reading was not confirmed")));continue
        used={x.field for x in row.inputs}
        if not used&fields:
            excluded.append(ExcludedRow(row_id=row.row_id,title=row.title,
                reason="Uses "+", ".join(field_name(f) for f in sorted(used))+" but these rules only decide on "+", ".join(field_name(f) for f in sorted(fields))+", so they cannot affect it."));continue
        data=row.cell("test_data");title=row.cell("title");expected=row.cell("expected")
        quoted=data if data and data.text else title
        sources=[]
        for cell in (quoted,expected):
            if cell and cell.text:
                sources.append(SourceReference(document_id=suite.document.document_id,document_hash=suite.document.document_hash,quote=cell.text,sheet=suite.sheet,cell=cell.cell))
        context=" ".join(part for part in (
            ("Preconditions: "+row.cell("preconditions").text) if row.cell("preconditions") and row.cell("preconditions").text else "",
            ("Steps: "+row.cell("steps").text) if row.cell("steps") and row.cell("steps").text else "") if part)
        rationale=("Imported from "+suite.title+" · sheet "+suite.sheet+" · row "+str(row.row_number)+". "+context).strip()[:2000]
        linked.append(TestCase(test_id=row.row_id,revision=1,title=row.title,inputs=row.inputs,expected=row.expected,kind=test_kind(row),
            origin=TestOrigin.EXISTING,rules=refs,rationale=rationale,metadata=metadata,sources=tuple(dict.fromkeys(sources))))
    return tuple(linked),tuple(excluded)

class LinkService:
    def __init__(self,database):
        self.db=database;self.suites=SuiteService(database);self.extraction=ExtractionService(database)
        self.workflow=WorkflowService(database);self.links=SuiteLinkRepository();self.promotions=LinkPromotionRepository()

    def link(self,suite_id,proposal_id,proposal_hash,*,actor):
        nonempty(actor,"actor")
        with self.db.transaction() as c:
            suite=self.suites.suites.get(c,SCOPE,suite_id,1)
            suite_doc,suite_data=self.suites.archive.get(c,suite_id,suite.document.document_hash)
            proposal=self.extraction.proposals.get(c,EXTRACTION,proposal_id,1)
            if content_hash(proposal)!=proposal_hash:raise ConflictError("The rules changed; reload before linking")
            if proposal.status!="pending_review":raise ConflictError("These rules cannot be used: "+"; ".join(proposal.issues))
            try:review=self.extraction.reviews.get(c,EXTRACTION,proposal_id,1)
            except NotFoundError as exc:raise ConflictError("Confirm the rules before linking them to test cases") from exc
            if review.decision!="approved" or review.proposal_hash!=proposal_hash:raise ConflictError("The rules were not confirmed")
            bundle,compiled=compile_proposal(proposal)
            meta=Metadata(created_at=datetime.now(timezone.utc),created_by=actor)
            linked,excluded=plan(suite,bundle.old_rules,bundle.new_rules,(bundle.old_table,bundle.new_table),meta)
            documents=[(suite_doc,suite_data),(bundle.document,compiled)]
            for source in proposal.request.sources:
                raw=source.text.encode("utf-8");documents.append((document(raw,source.document_id,"text/plain"),raw))
            for name,model in (("proposal",proposal),("review",review)):
                raw=model.to_json().encode("utf-8");documents.append((document(raw,name+"-"+proposal_id+".json","application/json"),raw))
            docs=tuple(documents)
            w=self.workflow.prepare_create(bundle.old_table,bundle.old_rules,bundle.new_table,bundle.new_rules,linked,actor=actor,
                old_as_of=bundle.old_as_of,new_as_of=bundle.new_as_of,source_documents=docs)
            self.workflow.persist_created(c,w,actor=actor,source_documents=docs)
            self.workflow.workflows.event(c,w,actor,"suite_linked","Linked "+str(len(linked))+" of "+str(len(suite.rows))+" test cases from "+suite.title+" to rules "+proposal_id)
            self.promotions.put(c,EXTRACTION,ExtractionPromotion(proposal_id=proposal_id,proposal_hash=proposal_hash,review_hash=content_hash(review),
                workflow_id=w.workflow_id,metadata=meta))
            link=SuiteLink(workflow_id=w.workflow_id,suite_id=suite_id,proposal_id=proposal_id,proposal_hash=proposal_hash,
                linked=tuple(t.test_id for t in linked),excluded=excluded,metadata=meta)
            self.links.put(c,SCOPE,link)
        # Analysis and review opening are separate revisions; a failure there leaves an inspectable draft.
        w=self.workflow.analyze(w.workflow_id,w.revision,actor=actor)
        w=self.workflow.start_review(w.workflow_id,w.revision,actor=actor)
        return w,link

    def link_for(self,c,workflow_id):
        try:return self.links.get(c,SCOPE,workflow_id,1)
        except NotFoundError:return None
