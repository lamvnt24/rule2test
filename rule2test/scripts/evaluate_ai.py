"""Evaluate all three AI roles against small synthetic truth sets, with durable artifacts."""
import argparse
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.ai_config import read_profile
from factory.models import content_hash
from factory.models.extraction import SourceText, ExtractionRequest
from factory.models.common import require
from factory.parsers.common import strict_json
from factory.providers.llm.prompt import PROMPT_VERSION
from factory.repositories.connection import Database
from factory.services.ai_readiness_service import readiness
from factory.services.extraction_service import ExtractionService
from factory.services.knowledge_service import KnowledgeService
from factory.services.retrieval_generation_service import RetrievalGenerationService
from factory.validators.extraction_validator import compile_proposal
from scripts.run_retrieval_demo import reviewed_source, target_workflow

ROOT=Path(__file__).resolve().parents[1]
QUERIES=(
    ("age eligibility 加入年齢","eligibility"),
    ("加入できる年齢の上限を調べる","eligibility"),
    ("Who is old enough to enroll?","eligibility"),
    ("claim_review 手動審査","claim_review"),
    ("請求を人による確認に回す金額の境目","claim_review"),
    ("When should a claim be reviewed manually?","claim_review"),
    ("deductible 免責金額","deductible"),
    ("保険金から差し引かれる自己負担額","deductible"),
    ("How much is deducted from the claim payment?","deductible"),
)

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def load_dataset(path):
    with Path(path).open("rb") as stream:raw=stream.read(1024*1024+1)
    require(len(raw)<=1024*1024,"Evaluation dataset exceeds 1 MiB")
    result=strict_json(raw.decode("utf-8"))
    require(type(result) is dict and result.get("schema_version")==1 and result.get("synthetic") is True,
            "Expected version 1 synthetic evaluation dataset")
    cases=result.get("cases")
    require(type(cases) is list and 1<=len(cases)<=100,"Dataset requires 1..100 cases")
    ids=set()
    for row in cases:
        require(type(row) is dict and set(row)=={"id","category","v1","v2","expected"},"Unexpected case schema")
        require(type(row["id"]) is str and row["id"] and row["id"] not in ids,"Duplicate or empty case ID")
        ids.add(row["id"])
        require(type(row["category"]) is str and row["category"],"Category is required")
        require(type(row["expected"]) is dict and row["expected"].get("status") in ("pending_review","needs_clarification"),
                "Expected truth status is required")
        if row["expected"]["status"]=="pending_review":
            require(set(row["expected"])=={"status","old","new"},"Ready truth requires both complete version projections")
        request_for(row)  # Validate text bounds before creating artifacts or invoking a provider.
    return result

def request_for(row):
    return ExtractionRequest(sources=(SourceText(document_id="v1.txt",label="v1",text=row["v1"]),
                                      SourceText(document_id="v2.txt",label="v2",text=row["v2"])))

def scalar(value):
    return format(value.normalize(),"f") if type(value) is Decimal else value

def projection(proposal):
    actual=dict(status=proposal.status)
    if proposal.status!="pending_review":return actual
    bundle,_=compile_proposal(proposal)
    def version(rules,table,as_of):
        if len(rules)!=1 or len(table.rows)!=1:
            return dict(unsupported_evaluation_shape=True,rule_count=len(rules),row_count=len(table.rows))
        rule=rules[0]
        if rule.effective_from is not None or rule.effective_to is not None or as_of is not None:
            return dict(unsupported_evaluation_shape=True,reason="Unexpected temporal semantics in undated fixture")
        conditions=[dict(field=c.field,operator=c.operator.value,value=scalar(c.value.data),currency=c.value.currency)
                    for c in rule.conditions]
        conditions.sort(key=lambda c:(c["field"],c["operator"]))
        return dict(conditions=conditions,outcome=rule.action.outcome.value,default=table.default_action.outcome.value,
                    deductible=scalar(rule.action.formula.deductible.data) if rule.action.formula else None,
                    amount=scalar(rule.action.amount.data) if rule.action.amount else None)
    actual.update(old=version(bundle.old_rules,bundle.old_table,bundle.old_as_of),new=version(bundle.new_rules,bundle.new_table,bundle.new_as_of))
    return actual

def extraction_checks(database, provider, dataset, timeout):
    service=ExtractionService(database,provider)
    rows=[]
    for case in dataset["cases"]:
        # The provider sees only source text. Gold truth is compared after it returns.
        proposal=service.propose(request_for(case),actor="Synthetic AI evaluator",timeout_seconds=timeout)
        actual=projection(proposal)
        rows.append(dict(case=case["id"],category=case["category"],matched=actual==case["expected"],
                         proposal_id=proposal.proposal_id,proposal_hash=content_hash(proposal),
                         actual=actual,expected=case["expected"],issues=list(proposal.issues),
                         elapsed_ms=proposal.elapsed_ms))
    categories={}
    for row in rows:
        group=categories.setdefault(row["category"],dict(matched=0,total=0))
        group["total"]+=1;group["matched"]+=row["matched"]
    return dict(status="completed",provider=provider.name,model=provider.model,simulated=provider.simulated,
                metric="fixture_replay_and_deliberate_limit_checks" if provider.simulated else "authored_semantic_spot_checks",
                matched=sum(r["matched"] for r in rows),total=len(rows),
                schema_and_citation_valid=sum(r["actual"]["status"] in ("pending_review","needs_clarification") for r in rows),
                provider_errors=sum(r["actual"]["status"]=="provider_error" for r in rows),
                categories=categories,median_elapsed_ms=statistics.median(r["elapsed_ms"] for r in rows),results=rows)

def retrieval_checks(knowledge,index,sources):
    rows=[]
    for query,profile in QUERIES:
        started=time.perf_counter()
        hits=knowledge.search(index.index_id,query,kind="test",top_k=3)
        expected=sources[profile].workflow_id
        rank=next((i+1 for i,h in enumerate(hits) if h.record.workflow_id==expected),None)
        rows.append(dict(query=query,expected_profile=profile,rank=rank,
                         hits=[dict(record_id=h.record.record_id,workflow_id=h.record.workflow_id,
                                    score=h.score,lexical=h.lexical_score,vector=h.vector_score) for h in hits],
                         elapsed_ms=round((time.perf_counter()-started)*1000)))
    return dict(status="completed",simulated=index.simulated,embedding_identity=index.embedding_identity,
                index_id=index.index_id,index_hash=content_hash(index),queries=len(rows),
                top1_correct=sum(r["rank"]==1 for r in rows),
                top1_accuracy=sum(r["rank"]==1 for r in rows)/len(rows),
                mrr_at_3=sum(1/r["rank"] if r["rank"] else 0 for r in rows)/len(rows),
                limitation="Hybrid ranking over only three approved test records; not embedding-only accuracy. Top-3 recall is not informative here.",
                results=rows)

def suggestion_checks(database,knowledge,index,sources,provider,timeout):
    target=target_workflow(database,sources["eligibility"])
    started=time.perf_counter()
    service=RetrievalGenerationService(database,provider,knowledge)
    batch=service.propose(target.workflow_id,target.revision,index.index_id,"age eligibility 加入年齢",
                          actor="Synthetic AI evaluator",timeout_seconds=timeout)
    # Fixed witness: old policy denies age 66; the target 18..70 policy allows it.
    witness=any(len(t.inputs)==1 and t.inputs[0].field=="age" and t.inputs[0].value.data==66
                and t.expected.outcome.value=="allow" for t in batch.candidates)
    return dict(status="completed",simulated=batch.simulated,provider=provider.name,
                batch_id=batch.batch_id,batch_hash=content_hash(batch),witness_age_66_allow_found=witness,
                novel_candidates=len(batch.candidates),duplicates_removed=batch.duplicate_count,
                all_candidates_grounded=all(bool(t.sources) for t in batch.candidates) if batch.candidates else None,
                target_unmodified=service.workflow.get(target.workflow_id)==target,
                automatic_approvals=False,automatic_attachment=False,
                elapsed_ms=round((time.perf_counter()-started)*1000),
                limitation="One fixed witness and schema/grounding checks; host computes expected outcomes. This is not general suggestion precision.",
                candidates=[t.to_dict() for t in batch.candidates])

def evaluate(profile,dataset,run_dir):
    report=dict(schema_version=1,run_id=run_dir.name,created_at=datetime.now(timezone.utc).isoformat(),
                profile=profile.to_dict(),profile_hash=content_hash(profile),mode=profile.mode,
                simulated=profile.mode=="mock",synthetic_data=True,prompt_version=PROMPT_VERSION,
                dataset_id=dataset["dataset_id"],dataset_hash=digest(dataset),stages={},
                unmeasured=["real reviewer acceptance","manual effort savings","production accuracy",
                            "token usage and monetary cost"],scripted_corpus_reviews=True)
    report["execution_locations"]={role:("cloud_via_local_gateway" if getattr(profile,role+"_model").endswith("-cloud") else "local") for role in ("extraction","suggestion","embedding")}
    report["digest_scope"]="Local artifact digests; cloud tags identify local gateway references, not pinned remote weights."
    before=readiness(profile)
    report["readiness_before"]=before
    if before["status"]=="blocked":
        report["status"]="blocked";report["reason"]="Local models unavailable or digest mismatch; no inference or fallback."
        return report
    extraction,embedding,suggestion=profile.providers()
    database=Database(run_dir/"evaluation.db")
    report["stages"]["extraction"]=extraction_checks(database,extraction,dataset,profile.timeout_seconds)
    try:
        # This is an independently seeded synthetic reference corpus. Extracted evaluation
        # proposals above are NEVER approved or promoted by the evaluator.
        sources={name:reviewed_source(database,name) for name in ("eligibility","claim_review","deductible")}
        knowledge=KnowledgeService(database,embedding=embedding)
        index=knowledge.build(tuple(w.workflow_id for w in sources.values()),actor="Synthetic corpus evaluator")
    except Exception:
        report["stages"]["retrieval"]=dict(status="error",error="Corpus/embedding setup failed; inspect model capability and configuration")
        report["stages"]["suggestions"]=dict(status="not_run",reason="No valid retrieval corpus")
    else:
        try:report["stages"]["retrieval"]=retrieval_checks(knowledge,index,sources)
        except Exception:report["stages"]["retrieval"]=dict(status="error",error="Retrieval evaluation failed; no ranking score assigned")
        try:report["stages"]["suggestions"]=suggestion_checks(database,knowledge,index,sources,suggestion,profile.timeout_seconds)
        except Exception:report["stages"]["suggestions"]=dict(status="error",error="Suggestion transport/schema/grounding validation failed; no success score assigned")
    after=readiness(profile)
    report["readiness_after"]=after
    report["model_identity_stable"]=before==after
    report["status"]="completed" if all(s["status"]=="completed" for s in report["stages"].values()) else "partial"
    if profile.mode=="ollama" and not report["model_identity_stable"]:
        report["status"]="invalidated"
        report["reason"]="Model inventory changed during evaluation; do not use these scores for model comparison."
    report["meaning"]="Completion means measurements were recorded, not that the model passed a quality threshold."
    return report

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile",type=Path,required=True)
    parser.add_argument("--dataset",type=Path,default=ROOT/"data"/"ai_eval"/"cases.json")
    parser.add_argument("--run-dir",type=Path)
    args=parser.parse_args(argv)
    try:
        profile=read_profile(args.profile);dataset=load_dataset(args.dataset)
        run_dir=args.run_dir or ROOT/"data"/"generated"/("ai-eval-"+uuid4().hex[:12])
        run_dir.mkdir(parents=True,exist_ok=False)
        report=evaluate(profile,dataset,run_dir)
        report["report_hash"]=digest(report)
        (run_dir/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        (run_dir/"dataset.json").write_text(json.dumps(dataset,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(dict(status=report["status"],simulated=report["simulated"],report=str(run_dir/"report.json"),
                             stages={name:{k:v for k,v in stage.items() if k in ("status","matched","total","top1_accuracy","witness_age_66_allow_found")}
                                     for name,stage in report["stages"].items()}),ensure_ascii=False))
        return 0 if report["status"]=="completed" else 2
    except Exception as exc:
        print("Evaluation could not complete: "+type(exc).__name__+". Check profile, dataset and a new writable run directory.",file=sys.stderr)
        return 1
if __name__=="__main__":raise SystemExit(main())

