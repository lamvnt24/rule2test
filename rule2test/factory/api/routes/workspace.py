"""Versioned REST routes over the typed services. No duplicate business rule engine."""
import json
from dataclasses import dataclass
from datetime import date
from factory.models import *
from factory.models.common import require
from factory.models.extraction import SourceText,ExtractionRequest
from factory.parsers.templates import demo_payload,json_bytes
from factory.parsers.json_parser import JsonParser
from factory.providers.llm.synthetic import SOURCE_PAIRS
from factory.services.import_service import ImportService
from factory.services.coverage_service import CoverageService
from factory.services.quality_gate_service import QualityGateService,canonical_report
from factory.services.mutation_service import MutationService
from factory.repositories.knowledge_repository import KnowledgeRepository,RetrievalBatchRepository
from factory.repositories.suite_repository import SuiteRepository,SuiteLinkRepository,SCOPE as SUITES
from factory.services.change_proposal_service import build as change_proposal,suggest_sut
from factory.services.rule_delta_service import RuleDeltaService
from factory.services.extraction_service import ExtractionService
from factory.providers.llm.patterns import PatternRuleProvider
from factory.validators.extraction_validator import compile_proposal
from factory.observability import span
from factory.exceptions import NotFoundError
from ..schemas.requests import body_keys,actor,upload
from .suites import SuiteRoutes

@dataclass
class Download:
    data: bytes
    media_type: str
    filename: str

def workflow_summary(w,link=None,suite=None):
    decisions={a.subject_id:a.decision.value for a in w.approvals}
    title=w.new_rules[0].title if w.new_rules else w.new_table.table_id
    if suite is not None:title+=" · "+suite.title
    return dict(workflow_id=w.workflow_id,revision=w.revision,status=w.status.value,title=title,
        tests=len(w.tests),pending=sum(t.test_id not in decisions or decisions[t.test_id]=="changes_requested" for t in w.tests),
        approved=sum(v=="approved" for v in decisions.values()),created_by=w.metadata.created_by,
        suite_id=link.suite_id if link else None,proposal_id=link.proposal_id if link else None,created_at=w.metadata.created_at.isoformat())

def linked(c,workflow_id):
    """(link, suite) for a workflow created from a test-case file, else (None, None)."""
    try:link=SuiteLinkRepository().get(c,SUITES,workflow_id,1)
    except NotFoundError:return None,None
    try:return link,SuiteRepository().get(c,SUITES,link.suite_id,1)
    except NotFoundError:return link,None

def metrics(report):
    return dict(mode=report.mode,**{key:dict(covered=getattr(report,key).covered,total=getattr(report,key).total,percent=getattr(report,key).percent)
        for key in ("rule","branch","boundary","exception")},unresolved_ids=report.unresolved_ids)

class WorkspaceRoutes:
    def __init__(self,app):self.app=app

    def get(self,path,query):
        app=self.app
        if path=="/api/v1/ai-status":return app.ai_status()
        if path=="/api/v1/diagnostics":return app.diagnostics()
        if path=="/api/v1/workflows":
            with app.db.read() as c:
                ids=[r[0] for r in c.execute("SELECT workflow_id FROM wf_heads ORDER BY rowid DESC LIMIT 100")]
                return [workflow_summary(app.workflow.workflows.current(c,wid),*linked(c,wid)) for wid in ids]
        if path=="/api/v1/proposals":
            with app.db.read() as c:
                rows=c.execute("SELECT payload,hash FROM wf_objects WHERE scope='extraction' AND kind='extraction_proposal' ORDER BY rowid DESC LIMIT 100")
                result=[]
                for row in rows:
                    p=app.extraction().proposals.decode(row)
                    try:review=app.extraction().reviews.get(c,"extraction",p.proposal_id,1).decision
                    except NotFoundError:review=None
                    result.append(dict(self.proposal_summary(p),review=review))
                return result
        if path.startswith("/api/v1/suites") or path.startswith("/api/v1/rules/"):return SuiteRoutes(app).get(path,query)
        if path=="/api/v1/indexes":
            with app.db.read() as c:
                rows=c.execute("SELECT payload,hash FROM wf_objects WHERE scope='knowledge' AND kind='knowledge_index' ORDER BY rowid DESC LIMIT 100")
                result=[]
                for row in rows:
                    index=KnowledgeRepository().decode(row)
                    result.append(dict(index_id=index.index_id,records=len(index.records),simulated=index.simulated,embedding=index.embedding_identity,created_by=index.metadata.created_by))
                return result
        if path=="/api/v1/batches":
            with app.db.read() as c:
                rows=c.execute("SELECT payload,hash FROM wf_objects WHERE scope='knowledge' AND kind='retrieval_batch' ORDER BY rowid DESC LIMIT 100")
                result=[]
                for row in rows:
                    b=RetrievalBatchRepository().decode(row)
                    result.append(dict(batch_id=b.batch_id,workflow_id=b.workflow_id,candidates=len(b.candidates),simulated=b.simulated))
                return result
        parts=path.strip("/").split("/")
        if len(parts)>=4 and parts[:3]==["api","v1","workflows"]:
            wid=parts[3]
            if len(parts)==4:
                with app.db.read() as c:
                    w=app.workflow.workflows.current(c,wid);link,suite=linked(c,wid)
                    baseline=True
                    if link is not None:
                        try:baseline=app.extraction().proposals.get(c,"extraction",link.proposal_id,1).request.baseline_known
                        except NotFoundError:baseline=True
                coverage=None
                if w.tests:
                    with span("coverage_measure",component="service",workflow_id=wid,count=len(w.tests)):
                        coverage=metrics(CoverageService().measure(w.new_table,w.new_rules,w.tests,as_of=w.new_as_of))
                with span("change_proposal",component="service",workflow_id=wid,count=len(w.tests)):
                    proposal=change_proposal(w,link=link,suite=suite,baseline_known=baseline)
                return dict(workflow=w.to_dict(),summary=workflow_summary(w,link,suite),coverage=coverage,proposal=proposal,
                    sut_suggestion=suggest_sut(w),link=link.to_dict() if link else None,suite=dict(suite_id=suite.suite_id,title=suite.title,sheet=suite.sheet) if suite else None)
            if len(parts)==5 and parts[4] in ("quality-gate","quality-gate-report"):
                with span("quality_gate_evaluate",component="service",workflow_id=wid):
                    report=QualityGateService(app.db).evaluate(wid)
                if parts[4]=="quality-gate-report":
                    return Download(canonical_report(report).encode("utf-8"),"application/json","quality-gate-"+wid+".json")
                return report
            if len(parts)==5 and parts[4]=="history":return app.workflow.events(wid)
            if len(parts)==5 and parts[4]=="mutation":
                w=app.workflow.get(wid)
                with span("mutation_analyze",component="service",workflow_id=wid,count=len(w.tests)):
                    report=MutationService().analyze(w.new_table,w.new_rules,w.tests,as_of=w.new_as_of,previous_rules=w.old_rules)
                return dict(report=report.to_dict(),score=report.score)
            if len(parts)==6 and parts[4]=="runs":
                run=app.workflow.run(wid,parts[5])
                with app.db.read() as c:approved=app.workflow.workflows.get(c,wid,wid,run.workflow_revision)
                selected=tuple(t for t,a in app.review.ready(approved))
                coverage=CoverageService().measure(approved.new_table,approved.new_rules,selected,
                    as_of=approved.new_as_of,executions=run.executions)
                return dict(**run.to_dict(),coverage=metrics(coverage))
            if len(parts)==6 and parts[4]=="evidence":
                evidence=app.evidence.get_evidence(wid,parts[5])
                return Download(evidence.to_json().encode("utf-8"),"application/json","evidence-"+evidence.evidence_id+".json")
            if len(parts)==6 and parts[4]=="sources":
                document,data=ImportService(app.workflow).source(wid,parts[5])
                return Download(data,document.media_type,document.document_id)
        if len(parts)==4 and parts[:3]==["api","v1","proposals"]:
            p=app.extraction().get(parts[3])
            try:review=app.extraction().review_record(p.proposal_id).to_dict()
            except NotFoundError:review=None
            output=json.loads(p.response_json) if p.status in ("pending_review","needs_clarification") else p.response_json
            compiled=None
            if p.status=="pending_review":
                bundle,_=compile_proposal(p)
                compiled=dict(old_rules=[r.to_dict() for r in bundle.old_rules],new_rules=[r.to_dict() for r in bundle.new_rules],
                    old_default=bundle.old_table.default_action.to_dict(),new_default=bundle.new_table.default_action.to_dict(),
                    delta=RuleDeltaService().compare(bundle.old_rules,bundle.new_rules).to_dict(),baseline_known=p.request.baseline_known)
            return dict(summary=self.proposal_summary(p),proposal=p.to_dict(),output=output,review=review,compiled=compiled)
        if len(parts)==4 and parts[:3]==["api","v1","batches"]:
            # Inspection does not need a currently configured embedding model.
            with app.db.read() as c:b=RetrievalBatchRepository().get(c,"knowledge",parts[3],1)
            return dict(batch=b.to_dict(),batch_hash=content_hash(b))
        if len(parts)==4 and parts[:3]==["api","v1","samples"]:
            profile=parts[3]
            require(profile in SOURCE_PAIRS,"Unknown sample")
            pair=SOURCE_PAIRS[profile]
            return dict(v1=pair[0],v2=pair[1],existing_tests=demo_payload(profile)["tests"],synthetic=True)
        raise NotFoundError("API route not found")

    @staticmethod
    def proposal_summary(p):
        new=next((s for s in p.request.sources if s.label=="v2"),None)
        first=next((line.strip() for line in new.text.splitlines() if line.strip()),"") if new else ""
        return dict(proposal_id=p.proposal_id,proposal_hash=content_hash(p),status=p.status,provider=p.provider,model=p.model,
            simulated=p.simulated,issues=p.issues,created_by=p.metadata.created_by,created_at=p.metadata.created_at.isoformat(),
            baseline_known=p.request.baseline_known,title=(first[:70]+"…") if len(first)>70 else first)

    def post(self,path,body):
        app=self.app
        if path=="/api/v1/demo":
            body_keys(body,("profile","actor"));who=actor(body)
            require(body["profile"] in SOURCE_PAIRS,"Unknown demo profile")
            data=json_bytes(demo_payload(body["profile"]));b=JsonParser().parse(data,body["profile"]+".json")
            w=app.workflow.create(b.old_table,b.old_rules,b.new_table,b.new_rules,b.existing_tests,actor=who,
                old_as_of=b.old_as_of,new_as_of=b.new_as_of,source_documents=((b.document,data),))
            return workflow_summary(w)
        if path=="/api/v1/import":
            body_keys(body,("filename","content_base64","actor"),("mapping",));who=actor(body)
            name,data=upload(body);b=ImportService.parse(data,name,body.get("mapping"))
            w=app.workflow.create(b.old_table,b.old_rules,b.new_table,b.new_rules,b.existing_tests,actor=who,
                old_as_of=b.old_as_of,new_as_of=b.new_as_of,source_documents=((b.document,data),))
            return workflow_summary(w)
        if path=="/api/v1/extract":
            body_keys(body,("sources","actor"),("existing_tests_json","timeout","engine"))
            require(body.get("engine","provider") in ("provider","pattern"),"engine must be provider or pattern")
            request=ExtractionRequest(sources=tuple(SourceText.from_dict(s) for s in body["sources"]),existing_tests_json=body.get("existing_tests_json","[]"))
            service=ExtractionService(app.db,PatternRuleProvider()) if body.get("engine")=="pattern" else app.extraction(provider=True)
            p=service.propose(request,actor=actor(body),timeout_seconds=body.get("timeout",app.ai_timeout()))
            return self.proposal_summary(p)
        if path.startswith("/api/v1/suites"):return SuiteRoutes(app).post(path,body)
        if path=="/api/v1/indexes":
            body_keys(body,("workflow_ids","actor"))
            index=app.knowledge().build(tuple(body["workflow_ids"]),actor=actor(body))
            return dict(index_id=index.index_id,records=len(index.records),simulated=index.simulated)
        if path=="/api/v1/search":
            body_keys(body,("index_id","query"),("fields","rule_ids","kind","workflow_ids","top_k"))
            hits=app.knowledge().search(body["index_id"],body["query"],fields=tuple(body.get("fields",[])),
                rule_ids=tuple(body.get("rule_ids",[])),kind=body.get("kind"),workflow_ids=tuple(body.get("workflow_ids",[])),top_k=body.get("top_k",5))
            return dict(hits=[h.to_dict() for h in hits])
        if path=="/api/v1/suggestions":
            body_keys(body,("workflow_id","revision","index_id","query","actor"),("timeout",))
            b=app.retrieval(provider=True).propose(body["workflow_id"],body["revision"],body["index_id"],body["query"],
                actor=actor(body),timeout_seconds=body.get("timeout",app.ai_timeout()))
            return dict(batch_id=b.batch_id,batch_hash=content_hash(b),candidates=len(b.candidates),simulated=b.simulated)
        parts=path.strip("/").split("/")
        if len(parts)==5 and parts[:3]==["api","v1","proposals"]:
            pid=parts[3];action=parts[4]
            if action=="review":
                body_keys(body,("proposal_hash","decision","reason","actor"))
                return app.extraction().review(pid,body["proposal_hash"],decision=body["decision"],reviewer=actor(body),reason=body["reason"]).to_dict()
            if action=="promote":
                body_keys(body,("proposal_hash","actor"))
                return workflow_summary(app.extraction().promote(pid,body["proposal_hash"],actor=actor(body)))
        if len(parts)==5 and parts[:3]==["api","v1","batches"] and parts[4]=="attach":
            body_keys(body,("batch_hash","actor"))
            return workflow_summary(app.retrieval().attach(parts[3],body["batch_hash"],actor=actor(body)))
        if len(parts)==5 and parts[:3]==["api","v1","workflows"]:
            wid=parts[3];action=parts[4]
            common=("revision","actor")
            extras={"analyze":(),"start-review":(),"finalize":("reason",),"reopen-review":("reason",),"recover":("reason",),
                "review":("tests","decision","reason"),"edit-test":("test_id","test_revision","inputs","expected","title","reason"),
                "revise-rules":("table","rules","as_of","reason"),"execute":("sut",),"evidence":()}
            require(action in extras,"Unknown workflow action")
            body_keys(body,common+extras[action]);who=actor(body);revision=body["revision"]
            with span("workflow_"+action.replace("-","_"),component="service",workflow_id=wid,revision=revision):
                if action=="analyze":w=app.workflow.analyze(wid,revision,actor=who)
                elif action=="start-review":w=app.workflow.start_review(wid,revision,actor=who)
                elif action=="review":
                    w=app.review.review_many(wid,revision,tests=body["tests"],decision=ApprovalDecision(body["decision"]),reviewer=who,reason=body["reason"])
                elif action=="finalize":w=app.review.finalize(wid,revision,reviewer=who,reason=body["reason"])
                elif action=="reopen-review":w=app.workflow.reopen_review(wid,revision,actor=who,reason=body["reason"])
                elif action=="recover":w=app.workflow.recover_interrupted_run(wid,revision,actor=who,reason=body["reason"])
                elif action=="edit-test":
                    w=app.workflow.edit_test(wid,revision,test_id=body["test_id"],test_revision=body["test_revision"],
                        inputs=tuple(TestInput.from_dict(x) for x in body["inputs"]),expected=Action.from_dict(body["expected"]),
                        title=body["title"],actor=who,reason=body["reason"])
                elif action=="revise-rules":
                    w=app.workflow.revise_rules(wid,revision,table=DecisionTable.from_dict(body["table"]),rules=tuple(Rule.from_dict(x) for x in body["rules"]),
                        as_of=date.fromisoformat(body["as_of"]) if body["as_of"] else None,actor=who,reason=body["reason"])
                elif action=="execute":
                    run=app.workflow.execute(wid,revision,app.adapter(body["sut"]),actor=who)
                    return dict(workflow=workflow_summary(app.workflow.get(wid)),run=run.to_dict())
                else:
                    evidence=app.evidence.create(wid,revision,actor=who)
                    return dict(workflow=workflow_summary(app.workflow.get(wid)),evidence_id=evidence.evidence_id,evidence_hash=evidence.fingerprint)
                return workflow_summary(w)
        raise NotFoundError("API route not found")


