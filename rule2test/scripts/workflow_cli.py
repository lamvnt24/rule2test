"""Persistent workflow commands. Review decisions require an explicit user command."""
import sys,json,argparse
from pathlib import Path
from dataclasses import replace
from datetime import date
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.models import *
from factory.models.common import require
from factory.repositories.connection import Database
from factory.services.workflow_service import WorkflowService
from factory.services.approval_service import ApprovalService
from factory.services.evidence_service import EvidenceService
from factory.providers.sut.mock import MockSUTAdapter
from factory.engines.insurance_engine import InsuranceEngine
from factory.exceptions import FactoryError
from tests.fixtures.engine_cases import scenario,approved_case

ROOT=Path(__file__).resolve().parents[1]

def create_demo(service,actor):
    table,rules=scenario("eligibility")
    old=replace(rules[0],conditions=(rules[0].conditions[0],
        replace(rules[0].conditions[1],value=Value(kind=ValueKind.INTEGER,data=60))))
    new=replace(rules[0],version=2)
    def bind(rule):
        ref=RuleReference(rule_id=rule.rule_id,version=rule.version,rule_hash=content_hash(rule))
        return replace(table,version=rule.version,rows=(replace(table.rows[0],conditions=rule.conditions,rule=ref),)),(rule,)
    old_table,old_rules=bind(old);new_table,new_rules=bind(new)
    _,_,base,_=approved_case("eligibility",Value(kind=ValueKind.INTEGER,data=18),Action(outcome=Outcome.ALLOW))
    existing=tuple(replace(base,test_id="EXISTING-"+str(age),inputs=(TestInput(field="age",value=Value(kind=ValueKind.INTEGER,data=age)),),
        rules=(old_table.rows[0].rule,),expected=Action(outcome=Outcome.ALLOW if age<=60 else Outcome.DENY)) for age in (18,60,61))
    return service.create(old_table,old_rules,new_table,new_rules,existing,actor=actor)

def summary(w):
    decisions={a.subject_id:a.decision.value for a in w.approvals}
    return {"workflow_id":w.workflow_id,"revision":w.revision,"status":w.status.value,
        "active_run_id":w.active_run_id,"last_run_id":w.last_run_id,"evidence_id":w.evidence_id,
        "tests":[{"test_id":t.test_id,"revision":t.revision,"title":t.title,
            "inputs":[i.to_dict() for i in t.inputs],"expected":t.expected.to_dict(),
            "review":decisions.get(t.test_id,"pending")} for t in w.tests]}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,default=ROOT/"data"/"workflow.db")
    commands=parser.add_subparsers(dest="command",required=True)
    create=commands.add_parser("create-demo");create.add_argument("--actor",required=True)
    for name in ("show","history","run-show"):
        sub=commands.add_parser(name);sub.add_argument("--workflow",required=True)
        if name=="show":sub.add_argument("--full",action="store_true")
        if name=="run-show":sub.add_argument("--run",required=True)
    for name in ("analyze","start-review","review","finalize","edit-test","revise-rules","reopen-review","execute","recover","evidence"):
        sub=commands.add_parser(name)
        sub.add_argument("--workflow",required=True);sub.add_argument("--revision",required=True,type=int)
        sub.add_argument("--actor",required=True)
        if name in ("review","finalize","edit-test","revise-rules","reopen-review","recover"):sub.add_argument("--reason",required=True)
        if name in ("review","edit-test"):
            sub.add_argument("--test-id",required=True);sub.add_argument("--test-revision",required=True,type=int)
        if name=="review":sub.add_argument("--decision",required=True,choices=[d.value for d in ApprovalDecision])
        if name in ("edit-test","revise-rules"):sub.add_argument("--file",required=True,type=Path)
        if name=="evidence":sub.add_argument("--output",type=Path)
        if name=="execute":
            sub.add_argument("--profile",choices=("eligibility","claim_review","deductible"),default="eligibility")
            sub.add_argument("--fault",choices=("none","boundary","stale","deductible_off_by_one"),default="none")
            sub.add_argument("--min-age",type=int,default=18);sub.add_argument("--max-age",type=int,default=65)
            sub.add_argument("--claim-threshold",type=Decimal,default=Decimal(150000000))
            sub.add_argument("--deductible",type=Decimal,default=Decimal(10000000))
            sub.add_argument("--currency",default="VND")
    args=parser.parse_args(argv)
    try:
        db=Database(args.db);service=WorkflowService(db);review=ApprovalService(db);evidence=EvidenceService(db)
        command=args.command;result=None
        if command=="create-demo":w=create_demo(service,args.actor)
        elif command=="show":
            w=service.get(args.workflow)
            if args.full:result=w.to_dict()
        elif command=="history":result=service.events(args.workflow)
        elif command=="run-show":result=service.run(args.workflow,args.run).to_dict()
        elif command=="analyze":w=service.analyze(args.workflow,args.revision,actor=args.actor)
        elif command=="start-review":w=service.start_review(args.workflow,args.revision,actor=args.actor)
        elif command=="review":
            w=review.review(args.workflow,args.revision,test_id=args.test_id,test_revision=args.test_revision,
                decision=ApprovalDecision(args.decision),reviewer=args.actor,reason=args.reason)
        elif command=="finalize":w=review.finalize(args.workflow,args.revision,reviewer=args.actor,reason=args.reason)
        elif command=="edit-test":
            payload=json.loads(args.file.read_text(encoding="utf-8"))
            require(type(payload) is dict and set(payload)<={"inputs","expected","title"} and {"inputs","expected"}<=set(payload),"Edit JSON requires inputs and expected; optional title")
            w=service.edit_test(args.workflow,args.revision,test_id=args.test_id,test_revision=args.test_revision,
                inputs=tuple(TestInput.from_dict(x) for x in payload["inputs"]),expected=Action.from_dict(payload["expected"]),
                title=payload.get("title"),actor=args.actor,reason=args.reason)
        elif command=="revise-rules":
            payload=json.loads(args.file.read_text(encoding="utf-8"))
            require(type(payload) is dict and set(payload)<={"table","rules","as_of"} and {"table","rules"}<=set(payload),"Policy JSON requires table and rules; optional as_of")
            w=service.revise_rules(args.workflow,args.revision,table=DecisionTable.from_dict(payload["table"]),
                rules=tuple(Rule.from_dict(x) for x in payload["rules"]),as_of=date.fromisoformat(payload["as_of"]) if payload.get("as_of") else None,
                actor=args.actor,reason=args.reason)
        elif command=="reopen-review":w=service.reopen_review(args.workflow,args.revision,actor=args.actor,reason=args.reason)
        elif command=="execute":
            adapter=MockSUTAdapter(InsuranceEngine(profile=args.profile,fault=args.fault,min_age=args.min_age,max_age=args.max_age,
                claim_threshold=args.claim_threshold,deductible=args.deductible,currency=args.currency))
            run=service.execute(args.workflow,args.revision,adapter,actor=args.actor)
            current=service.get(args.workflow)
            result={"workflow_id":current.workflow_id,"revision":current.revision,"status":current.status.value,
                    "run_id":run.run_id,"passed":sum(e.status is ExecutionStatus.PASS for e in run.executions),
                    "failed":sum(e.status is ExecutionStatus.FAIL for e in run.executions),
                    "errors":sum(e.status is ExecutionStatus.ERROR for e in run.executions)}
        elif command=="recover":w=service.recover_interrupted_run(args.workflow,args.revision,actor=args.actor,reason=args.reason)
        elif command=="evidence":
            record=evidence.create(args.workflow,args.revision,actor=args.actor)
            if args.output:
                with args.output.open("x",encoding="utf-8") as stream:stream.write(record.to_json())
            current=service.get(args.workflow)
            result={"workflow_id":current.workflow_id,"revision":current.revision,"status":current.status.value,
                    "evidence_id":record.evidence_id,"evidence_hash":record.fingerprint}
        if result is None:result=summary(w)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (FactoryError,OSError,ValueError,TypeError) as exc:
        print("Error: "+str(exc),file=sys.stderr);return 2

if __name__=="__main__":sys.exit(main())
