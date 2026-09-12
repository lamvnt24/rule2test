"""Run structured import -> durable DRAFT -> analysis -> pending human review."""
import sys,argparse,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.services.import_service import ImportService
from factory.services.workflow_service import WorkflowService
from factory.repositories.connection import Database
from factory.exceptions import FactoryError
from scripts.workflow_cli import summary

ROOT=Path(__file__).resolve().parents[1]
def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file",type=Path,default=ROOT/"data"/"demo"/"eligibility.xlsx")
    parser.add_argument("--db",type=Path,default=ROOT/"data"/"import-demo.db")
    args=parser.parse_args(argv)
    try:
        # Validate before creating the database; use ImportService.create for one read at commit time.
        ImportService().validate(args.file)
        workflow=WorkflowService(Database(args.db));imports=ImportService(workflow)
        w=imports.create(args.file,actor="Synthetic BA")
        w=workflow.analyze(w.workflow_id,w.revision,actor="Synthetic BA")
        w=workflow.start_review(w.workflow_id,w.revision,actor="Synthetic QA")
        document,data=imports.source(w.workflow_id,w.documents[0].document_hash)
        result=summary(w)
        result["documents"]=[document.to_dict()]
        result["source_archive_verified"]=len(data)==document.size_bytes
        result["source_example"]=w.new_rules[0].sources[0].to_dict()
        result["existing_test_count"]=len(w.existing_tests)
        result["pending_review_count"]=len(w.tests)
        result["next_step"]="Review each test using scripts/workflow_cli.py; no approval or SUT execution was performed."
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (FactoryError,OSError,ValueError,TypeError) as exc:
        print("Error: "+str(exc),file=sys.stderr);return 2

if __name__=="__main__":sys.exit(main())
