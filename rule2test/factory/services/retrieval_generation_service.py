"""Retrieve reviewed context, validate candidate inputs, recompute expected and attach pending tests."""
from datetime import datetime,timezone
from dataclasses import replace
from uuid import uuid4
from factory.models import Metadata,TestCase,TestInput,TestKind,TestOrigin,SourceReference,WorkflowStatus,content_hash
from factory.models.common import require,nonempty
from factory.models.knowledge import RetrievalBatch
from factory.parsers.common import strict_json,document
from factory.repositories.knowledge_repository import RetrievalBatchRepository
from factory.repositories.document_repository import DocumentRepository
from factory.engines.oracle_engine import OracleEngine
from factory.validators.test_validator import input_map
from factory.exceptions import ConflictError,ProviderError
from factory.observability import span
from factory.providers.failure import classify
from .knowledge_service import KnowledgeService,SCOPE
from .workflow_service import WorkflowService
from .gap_service import GapService
from ._support import inputs_key,references,stable_id

class RetrievalGenerationService:
    def __init__(self,database,provider=None,knowledge=None):
        self.db=database;self.provider=provider;self.knowledge=knowledge or KnowledgeService(database)
        self.workflow=WorkflowService(database);self.repository=RetrievalBatchRepository()

    def propose(self,workflow_id,revision,index_id,query,*,actor,timeout_seconds=30):
        nonempty(actor,"actor")
        require(type(timeout_seconds) is int and 1<=timeout_seconds<=120,"Timeout must be 1..120 seconds")
        w=self.workflow.get(workflow_id)
        if w.revision!=revision or type(revision) is not int:raise ConflictError("Stale target workflow revision")
        if w.status not in (WorkflowStatus.ANALYZED,WorkflowStatus.IN_REVIEW):raise ConflictError("Analyze the target before retrieval proposals")
        fields=tuple(sorted({c.field for r in w.new_rules for c in r.conditions}))
        # Only records the target policy can express are useful here: a candidate whose inputs fall
        # outside `fields` is rejected below, so retrieving one would discard the whole batch.
        hits=self.knowledge.search(index_id,query,fields_within=fields,rule_ids=tuple(r.rule_id for r in w.new_rules),exclude_workflow=w.workflow_id,top_k=5)
        index=self.knowledge.get(index_id)
        require(self.provider is not None,"Suggestion provider is required")
        try:
            with span("suggestion_propose",component="service",provider=self.provider.name):
                raw=self.provider.suggest(w,hits,timeout_seconds=timeout_seconds) if hits else '{"candidates":[]}'
        except Exception as exc:
            # classify preserves an already-classified adapter failure instead of flattening it again.
            raise classify(exc,"Test suggestion provider failed; no candidates were saved") from exc
        require(type(raw) is str and len(raw.encode("utf-8"))<=262144,"Suggestion response exceeds 256 KiB")
        result=strict_json(raw)
        require(type(result) is dict and set(result)=={"candidates"},"Unexpected suggestion output fields")
        rows=result["candidates"]
        require(type(rows) is list and len(rows)<=20,"At most 20 candidates are supported")
        ids={h.record.record_id:h.record for h in hits}
        seen={inputs_key(t.inputs) for t in w.tests};candidates=[];duplicates=0
        meta=Metadata(created_at=datetime.now(timezone.utc),created_by=actor)
        gaps=GapService().analyze(w.new_table,w.new_rules,w.tests,as_of=w.new_as_of)
        index_hash=content_hash(index)
        for row in rows:
            require(type(row) is dict and set(row)=={"inputs","reference_ids","reason"},"Candidate permits inputs, reference_ids and reason only")
            refs=row["reference_ids"];reason=row["reason"];values=row["inputs"]
            require(type(refs) is list and 0<len(refs)<=5 and all(type(x) is str and x in ids for x in refs) and len(set(refs))==len(refs),"Candidate must cite distinct retrieved IDs")
            require(type(reason) is str and 0<len(reason.strip())<=1000,"Candidate requires bounded rationale")
            require(type(values) is list and 0<len(values)<=2,"Candidate requires 1..2 typed inputs")
            inputs=tuple(TestInput.from_dict(v) for v in values);input_map(inputs)
            require({x.field for x in inputs}<=set(fields),"Candidate uses fields outside current policy")
            key=inputs_key(inputs)
            expected=OracleEngine().evaluate(w.new_table,w.new_rules,inputs,as_of=w.new_as_of)
            if key in seen:duplicates+=1;continue
            seen.add(key)
            obligations=tuple(o.obligation_id for o in gaps.obligations if o.obligation_id in gaps.missing_ids and o.inputs is not None and inputs_key(o.inputs)==key)
            sources=tuple(SourceReference(document_id="knowledge-"+index.index_id+".json",document_hash=index_hash,
                quote=ids[ref].text,json_pointer="/records/"+str(next(i for i,r in enumerate(index.records) if r.record_id==ref))+"/text") for ref in refs)
            candidates.append(TestCase(test_id=stable_id("RAG-",[content_hash(w.new_table),key]),revision=1,title="Retrieved regression proposal",
                inputs=inputs,expected=expected,kind=TestKind.EXCEPTION if expected.outcome.value=="invalid" else (TestKind.BOUNDARY if obligations else TestKind.POSITIVE),
                origin=TestOrigin.DETERMINISTIC if self.provider.simulated else TestOrigin.LLM,rules=references(w.new_rules),
                rationale=("Mock proposal. " if self.provider.simulated else "LLM proposal. ")+reason+" Expected recomputed by current oracle; QA review required.",
                metadata=meta,obligation_ids=obligations,sources=sources))
        batch=RetrievalBatch(batch_id=str(uuid4()),workflow_id=w.workflow_id,workflow_revision=w.revision,table_hash=content_hash(w.new_table),
            index_id=index_id,index_hash=index_hash,query=query,hits=hits,provider=self.provider.name,
            simulated=self.provider.simulated or index.simulated,raw_response=raw,candidates=tuple(candidates),duplicate_count=duplicates,metadata=meta)
        with self.db.transaction() as c:
            current=self.workflow.load(c,workflow_id,revision)
            require(content_hash(current)==content_hash(w),"Target changed during proposal")
            live=self.knowledge.live_ids(c,index)
            require(all(h.record.record_id in live for h in hits),"Retrieved approval changed during proposal; search again")
            self.repository.put(c,SCOPE,batch)
        return batch

    def get(self,batch_id):
        with self.db.read() as c:return self.repository.get(c,SCOPE,batch_id,1)

    def attach(self,batch_id,batch_hash,*,actor):
        nonempty(actor,"actor")
        with self.db.transaction() as c:
            batch=self.repository.get(c,SCOPE,batch_id,1)
            if content_hash(batch)!=batch_hash:raise ConflictError("Batch hash mismatch")
            w=self.workflow.load(c,batch.workflow_id,batch.workflow_revision)
            if w.status not in (WorkflowStatus.ANALYZED,WorkflowStatus.IN_REVIEW):raise ConflictError("Target is not in design/review")
            require(content_hash(w.new_table)==batch.table_hash,"Current policy changed")
            require(bool(batch.candidates),"No novel candidates to attach")
            index=self.knowledge.repository.get(c,SCOPE,batch.index_id,1)
            require(content_hash(index)==batch.index_hash,"Knowledge index hash mismatch")
            live=self.knowledge.live_ids(c,index)
            require(all(h.record.record_id in live for h in batch.hits),"Reference approval is stale; create a new batch")
            existing={inputs_key(t.inputs) for t in w.tests};identifiers={t.test_id for t in w.tests}
            for test in batch.candidates:
                require(inputs_key(test.inputs) not in existing and test.test_id not in identifiers,"Duplicate target candidate")
                require(test.expected==OracleEngine().evaluate(w.new_table,w.new_rules,test.inputs,as_of=w.new_as_of),"Stale expected")
            documents=list(w.documents);archives=[]
            for name,model in (("knowledge-"+index.index_id+".json",index),("retrieval-"+batch.batch_id+".json",batch)):
                data=model.to_json().encode("utf-8");doc=document(data,name,"application/json")
                if doc not in documents:documents.append(doc);archives.append((doc,data))
            updated=replace(w,tests=w.tests+batch.candidates,documents=tuple(documents),status=WorkflowStatus.IN_REVIEW,evidence_id=None)
            updated=self.workflow.commit(c,w,updated,actor,"retrieval_candidates_added","Attached batch "+batch.batch_id+"; new tests require QA review")
            for doc,data in archives:DocumentRepository().put(c,w.workflow_id,doc,data)
            return updated
