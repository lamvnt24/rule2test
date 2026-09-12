"""Phase-3 rule-change to evidence demo. Review decisions are explicit synthetic fixtures."""
import sys,json,argparse
from pathlib import Path
from dataclasses import replace
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.models import *
from factory.services.rule_delta_service import RuleDeltaService
from factory.services.impact_service import ImpactService
from factory.services.gap_service import GapService
from factory.services.generation_service import GenerationService
from factory.services.coverage_service import CoverageService
from factory.services.mutation_service import MutationService
from factory.engines.insurance_engine import InsuranceEngine
from factory.engines.test_executor import TestExecutor
from factory.providers.sut.mock import MockSUTAdapter
from tests.fixtures.engine_cases import scenario,approved_case

def run_demo():
    original_table,original_rules=scenario("eligibility")
    old_rule=replace(original_rules[0],conditions=(original_rules[0].conditions[0],
        replace(original_rules[0].conditions[1],value=Value(kind=ValueKind.INTEGER,data=60))))
    new_rule=replace(original_rules[0],version=2)
    def bind(rule):
        ref=RuleReference(rule_id=rule.rule_id,version=rule.version,rule_hash=content_hash(rule))
        return replace(original_table,version=rule.version,rows=(replace(original_table.rows[0],conditions=rule.conditions,rule=ref),)),(rule,)
    old_table,old_rules=bind(old_rule);new_table,new_rules=bind(new_rule)
    _,_,base,_=approved_case("eligibility",Value(kind=ValueKind.INTEGER,data=18),Action(outcome=Outcome.ALLOW))
    existing=tuple(replace(base,test_id="EXISTING-"+str(age),inputs=(TestInput(field="age",value=Value(kind=ValueKind.INTEGER,data=age)),),
        rules=(old_table.rows[0].rule,),expected=Action(outcome=Outcome.ALLOW if age<=60 else Outcome.DENY))
        for age in (18,60,61))
    metadata=Metadata(created_at=datetime.now(timezone.utc),created_by="Synthetic demo")
    delta=RuleDeltaService().compare(old_rules,new_rules)
    impact=ImpactService().analyze(old_table,old_rules,new_table,new_rules,existing)
    gaps=GapService().analyze(new_table,new_rules,existing)
    generator=GenerationService()
    generated=generator.generate(new_table,new_rules,gaps,metadata=metadata)
    revisions=generator.rebase(new_table,new_rules,existing,metadata=metadata)
    suite=revisions+generated.candidates
    approvals=tuple(Approval(approval_id="DEMO-APPROVAL-"+t.test_id,subject_kind=SubjectKind.TEST,
        subject_id=t.test_id,revision=t.revision,content_hash=content_hash(t),reviewer="Synthetic demo reviewer",
        decision=ApprovalDecision.APPROVED,decided_at=datetime.now(timezone.utc),
        reason="Scripted synthetic fixture; not a real QA approval") for t in suite)
    coverage_service=CoverageService()
    before=coverage_service.measure(new_table,new_rules,existing)
    after=coverage_service.measure(new_table,new_rules,suite)
    mutation=MutationService().analyze(new_table,new_rules,suite,previous_rules=old_rules)
    runs=[]
    for fault in ("none","boundary"):
        executor=TestExecutor(MockSUTAdapter(InsuranceEngine(profile="eligibility",fault=fault)))
        run_id="ANALYSIS-"+fault
        executions=tuple(executor.execute(test,approval,new_table,new_rules,run_id=run_id) for test,approval in zip(suite,approvals))
        executed=coverage_service.measure(new_table,new_rules,suite,executions=executions)
        evidence=Evidence(evidence_id="EV-"+run_id,run_id=run_id,rules=new_rules,tests=suite,
            approvals=approvals,executions=executions,decision_tables=(new_table,),
            metadata=Metadata(created_at=datetime.now(timezone.utc),created_by="Synthetic demo"))
        runs.append({"fault":fault,"passed":sum(e.status is ExecutionStatus.PASS for e in executions),
            "failed":sum(e.status is ExecutionStatus.FAIL for e in executions),
            "errors":sum(e.status is ExecutionStatus.ERROR for e in executions),
            "execution_boundary_percent":executed.boundary.percent,
            "evidence_hash":evidence.fingerprint,"evidence":evidence.to_dict()})
    return {"approval_mode":"synthetic fixture; services never approve tests",
        "delta":delta.to_dict(),"impact":[x.to_dict() for x in impact],"gaps":gaps.to_dict(),
        "candidates":generated.to_dict(),"baseline_coverage":before.to_dict(),"final_design_coverage":after.to_dict(),
        "baseline_boundary_percent":before.boundary.percent,"final_boundary_percent":after.boundary.percent,
        "mutation_score":mutation.score,"mutations":mutation.to_dict(),"runs":runs}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,help="Write full analysis and evidence JSON; refuses to overwrite an existing file")
    args=parser.parse_args()
    report=run_demo()
    if args.output:
        with args.output.open("x",encoding="utf-8") as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    summary={"rule_changes":len(report["delta"]["deltas"]),"related_tests":sum(x["related"] for x in report["impact"]),
        "changed_outcomes":sum(x["status"]=="changed" for x in report["impact"]),
        "generated_candidates":len(report["candidates"]["candidates"]),
        "unresolved_obligations":len(report["gaps"]["unresolved_ids"]),
        "boundary_before":report["baseline_boundary_percent"],"boundary_after":report["final_boundary_percent"],
        "mutation_score":report["mutation_score"],
        "approval_mode":report["approval_mode"],"runs":[{k:v for k,v in r.items() if k!="evidence"} for r in report["runs"]]}
    print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
