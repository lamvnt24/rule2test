"""Curate reviewed snapshots; hybrid search revalidates current approval before returning a hit."""
from datetime import datetime,timezone
import math
from uuid import uuid4
from factory.models import Metadata,content_hash,ApprovalDecision
from factory.models.common import require,nonempty
from factory.models.knowledge import KnowledgeRecord,KnowledgeVector,KnowledgeIndex,RetrievalHit
from factory.repositories.knowledge_repository import KnowledgeRepository
from factory.repositories.workflow_repository import WorkflowRepository
from factory.repositories.extraction_repository import PromotionRepository,ProposalRepository,ExtractionReviewRepository
from factory.validators.extraction_validator import compile_proposal
from factory.validators.test_validator import validate_approved_test
from factory.providers.embedding.mock import MockEmbeddingProvider,tokens
from factory.providers.vector.base import PythonVectorBackend,normalized
from factory.exceptions import ValidationError
from ._support import stable_id

SCOPE="knowledge"

class KnowledgeService:
    def __init__(self,database,embedding=None,backend=None):
        self.db=database;self.embedding=embedding or MockEmbeddingProvider();self.backend=backend or PythonVectorBackend()
        self.repository=KnowledgeRepository();self.workflows=WorkflowRepository()

    def _records(self,c,w):
        records=[];table_hash=content_hash(w.new_table)
        def add(kind,obj,proof_id,proof_hash):
            fields=tuple(sorted({x.field for x in (obj.conditions if kind=="rule" else obj.inputs)}))
            rule_ids=(obj.rule_id,) if kind=="rule" else tuple(r.rule_id for r in obj.rules)
            text=obj.title+" "+(" ".join(s.quote for s in obj.sources) if kind=="rule" else obj.rationale)
            text+=" "+" ".join(fields)+" "+" ".join(rule_ids)
            text+=" "+str([x.to_dict() for x in (obj.conditions if kind=="rule" else obj.inputs)])
            require(len(text)<=100000,"Knowledge text exceeds 100000 characters")
            records.append(KnowledgeRecord(record_id=stable_id("KB-",[w.workflow_id,kind,content_hash(obj),proof_hash]),
                workflow_id=w.workflow_id,kind=kind,table_hash=table_hash,proof_id=proof_id,proof_hash=proof_hash,
                fields=fields,rule_ids=rule_ids,text=text,rule=obj if kind=="rule" else None,test=obj if kind=="test" else None))
        # A reviewed test does not imply rule approval. Rules require a phase-6 promotion proof.
        rows=c.execute("SELECT payload,hash FROM wf_objects WHERE scope='extraction' AND kind='extraction_promotion' AND json_extract(payload,'$.workflow_id')=?",(w.workflow_id,))
        for row in rows:
            promotion=PromotionRepository().decode(row)
            proposal=ProposalRepository().get(c,"extraction",promotion.proposal_id,1)
            review=ExtractionReviewRepository().get(c,"extraction",promotion.proposal_id,1)
            require(promotion.proposal_hash==content_hash(proposal)==review.proposal_hash and promotion.review_hash==content_hash(review),"Rule approval proof mismatch")
            if review.decision!="approved":continue
            bundle,_=compile_proposal(proposal)
            if content_hash(bundle.new_table)!=table_hash:continue
            for rule in w.new_rules:
                if rule in bundle.new_rules:add("rule",rule,proposal.proposal_id,content_hash(review))
        approvals={a.subject_id:a for a in w.approvals}
        for test in w.tests:
            approval=approvals.get(test.test_id)
            if not approval or approval.decision is not ApprovalDecision.APPROVED:continue
            try:validate_approved_test(test,approval,w.new_table,datetime.now(timezone.utc))
            except ValidationError:continue
            add("test",test,approval.approval_id,content_hash(approval))
        return tuple(records)

    def build(self,workflow_ids,*,actor):
        nonempty(actor,"actor")
        require(0<len(workflow_ids)<=20 and len(set(workflow_ids))==len(workflow_ids),"Choose 1..20 distinct workflow IDs")
        with self.db.read() as c:
            records=tuple(record for wid in sorted(workflow_ids) for record in self._records(c,self.workflows.current(c,wid)))
        require(len(records)<=500,"Corpus exceeds 500 reviewed records; narrow the workflows")
        vectors=self.embedding.embed(tuple(r.text for r in records))
        require(len(vectors)==len(records),"Embedding row count mismatch")
        vectors=tuple(KnowledgeVector(values=normalized(v,self.embedding.dimensions)) for v in vectors)
        index=KnowledgeIndex(index_id=str(uuid4()),embedding_identity=self.embedding.identity,dimensions=self.embedding.dimensions,
            simulated=self.embedding.simulated,records=records,vectors=vectors,metadata=Metadata(created_at=datetime.now(timezone.utc),created_by=actor))
        with self.db.transaction() as c:self.repository.put(c,SCOPE,index)
        return index

    def get(self,index_id):
        with self.db.read() as c:return self.repository.get(c,SCOPE,index_id,1)

    def live_ids(self,c,index):
        result=set()
        for wid in sorted({r.workflow_id for r in index.records}):
            current={r.record_id:r for r in self._records(c,self.workflows.current(c,wid))}
            result.update(r.record_id for r in index.records if r.workflow_id==wid and current.get(r.record_id)==r)
        return result

    def search(self,index_id,query,*,fields=(),rule_ids=(),kind=None,workflow_ids=(),exclude_workflow=None,top_k=5):
        nonempty(query,"query")
        require(len(query)<=2000 and type(top_k) is int and 1<=top_k<=20,"Query/top_k exceeds bounds")
        require(kind in (None,"rule","test"),"Unknown record kind")
        require(set(fields)<={"age","claim_amount"},"Unsupported field filter")
        index=self.get(index_id)
        require(index.embedding_identity==self.embedding.identity and index.dimensions==self.embedding.dimensions and index.simulated==self.embedding.simulated,"Embedding identity mismatch; rebuild with the selected provider")
        with self.db.read() as c:live=self.live_ids(c,index)
        selected=[i for i,r in enumerate(index.records) if r.record_id in live and r.workflow_id!=exclude_workflow
            and (not fields or set(fields)<=set(r.fields)) and (kind is None or r.kind==kind)
            and (not workflow_ids or r.workflow_id in workflow_ids)]
        if not selected:return ()
        embedded=self.embedding.embed((query,))
        require(len(embedded)==1,"Query embedding count mismatch")
        vector_scores=self.backend.scores(tuple(index.vectors[i].values for i in selected),embedded[0])
        require(len(vector_scores)==len(selected),"Vector score count mismatch")
        require(all(type(s) is float and math.isfinite(s) for s in vector_scores),"Backend returned invalid scores")
        query_tokens=tokens(query);hits=[]
        for i,score in zip(selected,vector_scores):
            record=index.records[i];lexical=len(query_tokens&tokens(record.text))/max(1,len(query_tokens))
            exact=bool(set(rule_ids)&set(record.rule_ids))
            # No unrelated vector-only fallback for zero/negative evidence.
            score=max(-1.0,min(1.0,score))
            if not lexical and score<=0 and not exact:continue
            combined=0.45*lexical+0.35*max(0.0,score)+0.20*exact
            hits.append(RetrievalHit(record=record,score=float(combined),lexical_score=float(lexical),vector_score=float(score),rule_id_match=exact))
        return tuple(sorted(hits,key=lambda h:(-h.score,h.record.record_id))[:top_k])
