"""Run phase-2 synthetic approvals and independent mock execution from any cwd."""
import sys, json
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.models import Action, Outcome, Value, ValueKind, Evidence, Metadata
from factory.engines.insurance_engine import InsuranceEngine
from factory.engines.test_executor import TestExecutor
from factory.providers.sut.mock import MockSUTAdapter
from tests.fixtures.engine_cases import approved_case,money

def main():
    results=[]
    for profile,value,expected,fault in [
        ("eligibility",Value(kind=ValueKind.INTEGER,data=65),Action(outcome=Outcome.ALLOW),"boundary"),
        ("claim_review",money(150000000),Action(outcome=Outcome.ALLOW),"boundary"),
        ("deductible",money(10000000),Action(outcome=Outcome.PAYOUT,amount=money(0)),"deductible_off_by_one")]:
        table,rules,test,approval=approved_case(profile,value,expected)
        for mode in ("none",fault):
            run_id=profile+"-"+mode
            execution=TestExecutor(MockSUTAdapter(InsuranceEngine(profile=profile,fault=mode))).execute(test,approval,table,rules,run_id=run_id)
            evidence=Evidence(evidence_id="EV-"+run_id,run_id=run_id,rules=rules,tests=(test,),approvals=(approval,),
                executions=(execution,),metadata=Metadata(created_at=datetime.now(timezone.utc),created_by="Synthetic demo"),
                decision_tables=(table,))
            results.append({"profile":profile,"fault":mode,"status":execution.status.value,
                "expected":execution.expected.to_dict(),"actual":execution.actual.to_dict() if execution.actual else None,
                "evidence_hash":evidence.fingerprint})
    print(json.dumps({"approval_mode":"synthetic fixture, not real QA approval","runs":results},indent=2))
if __name__=="__main__":main()
