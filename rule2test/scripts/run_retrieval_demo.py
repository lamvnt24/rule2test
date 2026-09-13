"""Explicit synthetic reviews seed a tiny corpus; target proposals remain unapproved."""
import sys,json,argparse,hashlib
from pathlib import Path
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.models import *
from factory.models.extraction import SourceText,ExtractionRequest
from factory.providers.llm.synthetic import SOURCE_PAIRS
from factory.providers.llm.mock import MockLLMProvider
from factory.providers.llm.test_suggestions import MockTestSuggestionProvider
from factory.providers.vector.faiss import FaissVectorBackend
from factory.repositories.connection import Database
from factory.services.extraction_service import ExtractionService
from factory.services.workflow_service import WorkflowService
from factory.services.approval_service import ApprovalService
from factory.services.knowledge_service import KnowledgeService
from factory.services.retrieval_generation_service import RetrievalGenerationService
from factory.services.import_service import ImportService
from factory.engines.oracle_engine import OracleEngine
from factory.parsers.common import document
from factory.services._support import numeric
from factory.exceptions import FactoryError

ROOT=Path(__file__).resolve().parents[1]

def reviewed_source(db,profile):
    # These are scripted fixture approvals, never presented as a real SME decision.
    pair=SOURCE_PAIRS[profile]
    request=ExtractionRequest(sources=tuple(SourceText(document_id=label+".txt",label=label,text=text) for label,text in zip(("v1","v2"),pair)))
    extraction=ExtractionService(db,MockLLMProvider());workflow=WorkflowService(db)
    p=extraction.propose(request,actor="Synthetic fixture BA")
    extraction.review(p.proposal_id,content_hash(p),decision="approved",reviewer="Synthetic fixture SME",reason="Scripted fixture approval only")
    w=extraction.promote(p.proposal_id,content_hash(p),actor="Synthetic fixture BA")
    w=workflow.analyze(w.workflow_id,w.revision,actor="Synthetic fixture BA")
    w=workflow.start_review(w.workflow_id,w.revision,actor="Synthetic fixture QA")
    field="age" if profile=="eligibility" else "claim_amount"
    value={"eligibility":66,"claim_review":140000000,"deductible":20000000}[profile]
    inputs=(TestInput(field=field,value=numeric(field,value,"VND")),)
    expected=OracleEngine().evaluate(w.new_table,w.new_rules,inputs)
    test=w.tests[0]
    w=workflow.edit_test(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,inputs=inputs,expected=expected,
        actor="Synthetic fixture QA",reason="Synthetic reusable regression input",title=profile+" reviewed regression")
    test=next(t for t in w.tests if t.test_id==test.test_id)
    return ApprovalService(db).review(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,
        decision=ApprovalDecision.APPROVED,reviewer="Synthetic fixture QA",reason="Scripted test fixture approval only")

def target_workflow(db,source):
    workflow=WorkflowService(db)
    quote="Age from 18 through 70 inclusive is allowed; otherwise denied."
    raw=quote.encode();doc=document(raw,"target-v3.txt","text/plain")
    rule=replace(source.new_rules[0],version=3,conditions=(source.new_rules[0].conditions[0],
        replace(source.new_rules[0].conditions[1],value=Value(kind=ValueKind.INTEGER,data=70))),
        sources=(SourceReference(document_id=doc.document_id,document_hash=doc.document_hash,quote=quote,line_start=1,line_end=1),))
    ref=RuleReference(rule_id=rule.rule_id,version=rule.version,rule_hash=content_hash(rule))
    table=replace(source.new_table,version=3,rows=(replace(source.new_table.rows[0],conditions=rule.conditions,rule=ref),))
    imports=ImportService(workflow)
    archives=tuple(imports.source(source.workflow_id,d.document_hash) for d in source.documents)+((doc,raw),)
    w=workflow.create(source.new_table,source.new_rules,table,(rule,),actor="Synthetic target BA",source_documents=archives)
    w=workflow.analyze(w.workflow_id,w.revision,actor="Synthetic target BA")
    return workflow.start_review(w.workflow_id,w.revision,actor="Synthetic target QA")

def evaluate(knowledge,index,sources):
    # Labels are independently fixed to source workflow IDs, never inferred from returned rankings.
    gold=[("age eligibility 加入年齢",sources["eligibility"].workflow_id),
        ("claim_review 手動審査",sources["claim_review"].workflow_id),
        ("deductible 免責金額",sources["deductible"].workflow_id)]
    results=[]
    for query,wid in gold:
        hits=knowledge.search(index.index_id,query,kind="test",top_k=3)
        ids=[h.record.workflow_id for h in hits]
        rank=ids.index(wid)+1 if wid in ids else None
        results.append(dict(query=query,expected_workflow=wid,rank=rank))
    return dict(metric="synthetic_lexical_retrieval_checks",simulated=index.simulated,queries=len(gold),
        recall_at_3=sum(r["rank"] is not None for r in results)/len(gold),
        mrr_at_3=sum(1/r["rank"] if r["rank"] else 0 for r in results)/len(gold),results=results)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--db",type=Path,default=ROOT/"data"/"retrieval-demo.db")
    parser.add_argument("--backend",choices=("python","faiss"),default="python");args=parser.parse_args(argv)
    try:
        db=Database(args.db);sources={p:reviewed_source(db,p) for p in SOURCE_PAIRS}
        knowledge=KnowledgeService(db,backend=FaissVectorBackend() if args.backend=="faiss" else None)
        index=knowledge.build(tuple(w.workflow_id for w in sources.values()),actor="Synthetic corpus curator")
        target=target_workflow(db,sources["eligibility"])
        batch=RetrievalGenerationService(db,MockTestSuggestionProvider(),knowledge).propose(target.workflow_id,target.revision,index.index_id,"age eligibility 加入年齢",actor="Synthetic target BA")
        result=dict(index_id=index.index_id,index_hash=content_hash(index),records=len(index.records),backend=knowledge.backend.name,
            target_workflow=target.workflow_id,target_revision=target.revision,batch_id=batch.batch_id,batch_hash=content_hash(batch),
            simulated=True,scripted_source_reviews=True,retrieved=len(batch.hits),novel_candidates=len(batch.candidates),
            duplicates_removed=batch.duplicate_count,candidates=[t.to_dict() for t in batch.candidates],
            evaluation=evaluate(knowledge,index,sources),next_step="Inspect retrieval_cli.py show --batch, then attach explicitly. Target tests have no new approvals.")
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (FactoryError,ValueError,TypeError,OSError) as exc:print("Error: "+str(exc),file=sys.stderr);return 2
if __name__=="__main__":sys.exit(main())
