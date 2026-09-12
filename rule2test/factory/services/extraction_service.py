"""Durable AI proposal -> explicit hash-bound review -> atomic DRAFT promotion."""
import hashlib,time
from datetime import datetime,timezone
from uuid import uuid4
from dataclasses import replace
from factory.models import Metadata,content_hash
from factory.models.common import require,nonempty
from factory.models.extraction import ExtractionProposal,ExtractionReview,ExtractionPromotion,MAX_RESPONSE_BYTES
from factory.parsers.common import document,strict_json
from factory.exceptions import ConflictError,NotFoundError
from factory.repositories.extraction_repository import ProposalRepository,ExtractionReviewRepository,PromotionRepository
from factory.validators.extraction_validator import validate_response,compile_proposal
from factory.providers.llm.prompt import SYSTEM_PROMPT,PROMPT_VERSION,document_message
from .workflow_service import WorkflowService

SCOPE="extraction"

class ExtractionService:
    def __init__(self,database,provider=None):
        self.db=database;self.provider=provider
        self.proposals=ProposalRepository();self.reviews=ExtractionReviewRepository();self.promotions=PromotionRepository()

    def propose(self,request,*,actor,timeout_seconds=30):
        nonempty(actor,"actor")
        require(type(timeout_seconds) is int and 1<=timeout_seconds<=120,"Timeout must be 1..120 seconds")
        require(self.provider is not None,"Configure an extraction provider")
        tests=strict_json(request.existing_tests_json)
        require(type(tests) is list and len(tests)<=1000,"Existing tests must be an array of at most 1000 rows")
        started=time.monotonic();raw="";status="provider_error";issues=("Provider request failed; check provider configuration.",)
        try:
            raw=self.provider.extract(request,system_prompt=SYSTEM_PROMPT,timeout_seconds=timeout_seconds)
        except Exception:
            # No provider exception body is persisted: it may contain credentials or transport details.
            raw=""
        else:
            status="invalid_output";issues=("Output failed JSON/schema/citation validation.",)
            try:
                result,_=validate_response(raw,request)
                status="pending_review" if result["status"]=="ready" else "needs_clarification"
                issues=tuple(result["issues"])
            except (ValueError,TypeError,KeyError,RecursionError) as exc:
                issues=("Output validation failed: "+str(exc)[:400],)
        try:bounded=type(raw) is str and len(raw.encode("utf-8"))<=MAX_RESPONSE_BYTES
        except UnicodeError:bounded=False
        if not bounded:
            raw="";status="invalid_output";issues=("Provider output exceeded the size limit or was not text.",)
        proposal=ExtractionProposal(proposal_id=str(uuid4()),request=request,provider=self.provider.name,
            model=self.provider.model,simulated=self.provider.simulated,prompt_version=PROMPT_VERSION,
            prompt_hash=hashlib.sha256((SYSTEM_PROMPT+"\n"+document_message(request)).encode("utf-8")).hexdigest(),
            response_json=raw,status=status,issues=issues,elapsed_ms=int((time.monotonic()-started)*1000),
            metadata=Metadata(created_at=datetime.now(timezone.utc),created_by=actor))
        if status=="pending_review":
            try:compile_proposal(proposal)
            except (ValueError,TypeError,KeyError,RecursionError) as exc:
                proposal=replace(proposal,status="invalid_output",issues=("Domain validation failed: "+str(exc)[:400],))
        with self.db.transaction() as c:self.proposals.put(c,SCOPE,proposal)
        return proposal

    def get(self,proposal_id):
        with self.db.read() as c:return self.proposals.get(c,SCOPE,proposal_id,1)

    def review(self,proposal_id,proposal_hash,*,decision,reviewer,reason):
        nonempty(reviewer,"reviewer");nonempty(reason,"reason")
        with self.db.transaction() as c:
            proposal=self.proposals.get(c,SCOPE,proposal_id,1)
            if content_hash(proposal)!=proposal_hash:raise ConflictError("Proposal hash changed; reload before review")
            if proposal.status!="pending_review":raise ConflictError("Only a validated proposal can be reviewed")
            compile_proposal(proposal)
            review=ExtractionReview(proposal_id=proposal_id,proposal_hash=proposal_hash,decision=decision,reason=reason,
                metadata=Metadata(created_at=datetime.now(timezone.utc),created_by=reviewer))
            try:existing=self.reviews.get(c,SCOPE,proposal_id,1)
            except NotFoundError:existing=None
            if existing:
                if (existing.proposal_hash,existing.decision,existing.reason,existing.metadata.created_by)!=(proposal_hash,decision,reason,reviewer):
                    raise ConflictError("Review is immutable; create a new proposal for corrections")
                return existing
            self.reviews.put(c,SCOPE,review)
            return review

    def promote(self,proposal_id,proposal_hash,*,actor):
        nonempty(actor,"actor");workflow=WorkflowService(self.db)
        with self.db.transaction() as c:
            proposal=self.proposals.get(c,SCOPE,proposal_id,1)
            if content_hash(proposal)!=proposal_hash:raise ConflictError("Proposal hash changed")
            if proposal.status!="pending_review":raise ConflictError("Proposal is not reviewable")
            try:review=self.reviews.get(c,SCOPE,proposal_id,1)
            except NotFoundError as exc:raise ConflictError("Explicit rule review is required") from exc
            if review.decision!="approved" or review.proposal_hash!=proposal_hash:raise ConflictError("Rule proposal is not approved")
            try:promotion=self.promotions.get(c,SCOPE,proposal_id,1)
            except NotFoundError:promotion=None
            if promotion:
                require(promotion.proposal_hash==proposal_hash and promotion.review_hash==content_hash(review),"Promotion audit hash mismatch")
                return workflow.workflows.current(c,promotion.workflow_id)
            bundle,data=compile_proposal(proposal)
            documents=[(bundle.document,data)]
            for source in proposal.request.sources:
                raw=source.text.encode("utf-8")
                documents.append((document(raw,source.document_id,"text/plain"),raw))
            for name,model in (("proposal",proposal),("review",review)):
                raw=model.to_json().encode("utf-8")
                documents.append((document(raw,name+"-"+proposal_id+".json","application/json"),raw))
            docs=tuple(documents)
            w=workflow.prepare_create(bundle.old_table,bundle.old_rules,bundle.new_table,bundle.new_rules,bundle.existing_tests,
                actor=actor,old_as_of=bundle.old_as_of,new_as_of=bundle.new_as_of,source_documents=docs)
            workflow.persist_created(c,w,actor=actor,source_documents=docs)
            workflow.workflows.event(c,w,actor,"extraction_promoted","Approved extraction "+proposal_id+" hash "+proposal_hash)
            promotion=ExtractionPromotion(proposal_id=proposal_id,proposal_hash=proposal_hash,review_hash=content_hash(review),
                workflow_id=w.workflow_id,metadata=Metadata(created_at=datetime.now(timezone.utc),created_by=actor))
            self.promotions.put(c,SCOPE,promotion)
            return w

    def review_record(self,proposal_id):
        with self.db.read() as c:return self.reviews.get(c,SCOPE,proposal_id,1)
