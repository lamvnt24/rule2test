"""Validate structured JSON/XLSX, create a workflow, or recover its original source."""
import sys,argparse,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.services.import_service import ImportService
from factory.services.workflow_service import WorkflowService
from factory.repositories.connection import Database
from factory.parsers.common import ImportFailure,strict_json,read_input
from factory.exceptions import FactoryError
from scripts.workflow_cli import summary

ROOT=Path(__file__).resolve().parents[1]

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,default=ROOT/"data"/"workflow.db")
    commands=parser.add_subparsers(dest="command",required=True)
    for name in ("validate","create"):
        sub=commands.add_parser(name);sub.add_argument("file",type=Path);sub.add_argument("--mapping",type=Path)
        if name=="create":sub.add_argument("--actor",required=True)
    source=commands.add_parser("source")
    source.add_argument("--workflow",required=True);source.add_argument("--hash",required=True)
    source.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command in ("validate","create"):
            mapping=strict_json(read_input(args.mapping).decode("utf-8-sig")) if args.mapping else None
            # Parse before opening SQLite. Invalid imports cannot create or migrate a database.
            data=read_input(args.file);bundle=ImportService.parse(data,args.file.name,mapping)
            if args.command=="validate":
                result=dict(valid=True,document=bundle.document.to_dict(),old_rules=len(bundle.old_rules),
                    new_rules=len(bundle.new_rules),existing_tests=len(bundle.existing_tests))
            else:
                service=WorkflowService(Database(args.db))
                w=service.create(bundle.old_table,bundle.old_rules,bundle.new_table,bundle.new_rules,bundle.existing_tests,
                    actor=args.actor,old_as_of=bundle.old_as_of,new_as_of=bundle.new_as_of,
                    source_documents=((bundle.document,data),))
                result=summary(w);result["documents"]=[d.to_dict() for d in w.documents]
        else:
            if not args.db.is_file():raise ValueError("Workflow database does not exist")
            service=ImportService(WorkflowService(Database(args.db)))
            document,data=service.source(args.workflow,args.hash)
            with args.output.open("xb") as stream:stream.write(data)
            result=dict(document=document.to_dict(),output=str(args.output),verified=True)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except ImportFailure as exc:
        print(json.dumps(dict(valid=False,issues=[i.to_dict() for i in exc.issues]),ensure_ascii=False,indent=2),file=sys.stderr);return 2
    except (FactoryError,OSError,ValueError,TypeError) as exc:
        print(json.dumps(dict(error=str(exc)),ensure_ascii=False),file=sys.stderr);return 2

if __name__=="__main__":sys.exit(main())
