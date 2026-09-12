"""Compare fixed synthetic truth after extraction; mock results are replay checks only."""
import sys,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.extraction_cli import request_from_files
from factory.providers.llm.factory import configured_provider
from factory.repositories.connection import Database
from factory.services.extraction_service import ExtractionService
from factory.validators.extraction_validator import compile_proposal
from factory.parsers.common import strict_json,read_input
from factory.exceptions import FactoryError

ROOT=Path(__file__).resolve().parents[1]
def evaluate(service,directory):
    results=[]
    for folder in sorted(Path(directory).iterdir()):
        if not folder.is_dir():continue
        request=request_from_files(folder/"rules_v1.txt",folder/"rules_v2.txt",folder/"existing_tests.json")
        proposal=service.propose(request,actor="Synthetic evaluator")
        # Truth is loaded only after the provider returns and is never passed to the provider.
        expected=strict_json(read_input(folder/"ground_truth.json").decode("utf-8"))
        actual={"status":proposal.status}
        if proposal.status=="pending_review":
            bundle,_=compile_proposal(proposal);old=bundle.old_rules[0];new=bundle.new_rules[0]
            def values(rule):return [str(c.value.data) if c.value.currency else c.value.data for c in rule.conditions]
            actual.update(field=new.conditions[0].field,old_values=values(old),new_values=values(new),
                operators=[c.operator.value for c in new.conditions],outcome=new.action.outcome.value,
                default=bundle.new_table.default_action.outcome.value,
                old_deductible=str(old.action.formula.deductible.data) if old.action.formula else None,
                new_deductible=str(new.action.formula.deductible.data) if new.action.formula else None)
        results.append(dict(sample=folder.name,proposal_id=proposal.proposal_id,matched=actual==expected,
            actual=actual,elapsed_ms=proposal.elapsed_ms))
    return dict(provider=service.provider.name,model=service.provider.model,simulated=service.provider.simulated,
        metric="mock_fixture_replay_checks" if service.provider.simulated else "synthetic_semantic_spot_checks",
        matched=sum(r["matched"] for r in results),total=len(results),results=results,
        limitations="Small fixture checks, not general extraction accuracy. Mock is scripted. Cost/token usage is unavailable.")

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",type=Path,default=ROOT/"data"/"ai_samples")
    parser.add_argument("--db",type=Path,default=ROOT/"data"/"extraction-eval.db")
    args=parser.parse_args(argv)
    try:
        result=evaluate(ExtractionService(Database(args.db),configured_provider()),args.directory)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result["total"] and result["matched"]==result["total"] else 1
    except (FactoryError,ValueError,TypeError,OSError) as exc:print("Error: "+str(exc),file=sys.stderr);return 2

if __name__=="__main__":sys.exit(main())
