"""Automated synthetic review demo; use workflow_cli.py for explicit human decisions."""
import sys,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.models import ApprovalDecision,WorkflowStatus,ExecutionStatus
from factory.repositories.connection import Database
from factory.services.workflow_service import WorkflowService
from factory.services.approval_service import ApprovalService
from factory.services.evidence_service import EvidenceService
from factory.providers.sut.mock import MockSUTAdapter
from factory.engines.insurance_engine import InsuranceEngine
from scripts.workflow_cli import create_demo

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,default=Path(__file__).resolve().parents[1]/"data"/"workflow-demo.db")
    args=parser.parse_args()
    db=Database(args.db);service=WorkflowService(db)
    w=create_demo(service,"Synthetic BA")
    w=service.analyze(w.workflow_id,w.revision,actor="Synthetic BA")
    service=WorkflowService(Database(args.db))
    restart_verified=service.get(w.workflow_id)==w
    w=service.start_review(w.workflow_id,w.revision,actor="Synthetic QA")
    review=ApprovalService(service.db)
    # Demonstrate an edit as a new test revision, then explicitly review every current test.
    test=w.tests[0]
    w=service.edit_test(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,
        inputs=test.inputs,expected=test.expected,actor="Synthetic QA",reason="Clarify boundary rationale")
    for test in w.tests:
        w=review.review(w.workflow_id,w.revision,test_id=test.test_id,test_revision=test.revision,
            decision=ApprovalDecision.APPROVED,reviewer="Synthetic QA",reason="Scripted synthetic review; not a real QA decision")
    w=review.finalize(w.workflow_id,w.revision,reviewer="Synthetic QA",reason="Synthetic review complete")
    run=service.execute(w.workflow_id,w.revision,MockSUTAdapter(InsuranceEngine(profile="eligibility")),actor="Synthetic QA")
    w=service.get(w.workflow_id)
    e=EvidenceService(service.db).create(w.workflow_id,w.revision,actor="Synthetic QA")
    reopened=WorkflowService(Database(args.db));final=reopened.get(w.workflow_id)
    saved=EvidenceService(reopened.db).get_evidence(w.workflow_id,e.evidence_id)
    print(json.dumps({"database":str(args.db.resolve()),"workflow_id":final.workflow_id,"revision":final.revision,
        "status":final.status.value,"restart_verified":restart_verified,"evidence_reload_verified":saved==e,
        "approval_mode":"scripted synthetic fixture","tests":len(final.tests),"passed":sum(x.status is ExecutionStatus.PASS for x in run.executions),
        "audit_events":len(reopened.events(w.workflow_id)),"run_id":run.run_id,"evidence_id":e.evidence_id,
        "evidence_hash":e.fingerprint},indent=2))
if __name__=="__main__":main()
