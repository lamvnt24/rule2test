"""Extract -> inspect -> explicit rule review -> promote. Test review remains separate."""
import sys,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.models.extraction import SourceText,ExtractionRequest,MAX_SOURCE_BYTES
from factory.models import content_hash
from factory.parsers.common import read_input
from factory.providers.llm.factory import configured_provider
from factory.repositories.connection import Database
from factory.services.extraction_service import ExtractionService
from factory.exceptions import FactoryError,NotFoundError
from scripts.workflow_cli import summary as workflow_summary

ROOT=Path(__file__).resolve().parents[1]

def source(path,label):
    if path.suffix.lower()!=".txt":raise ValueError("Phase 6 accepts UTF-8 .txt sources; OCR/XLSX free-layout extraction is not implemented")
    with path.open("rb") as stream:data=stream.read(MAX_SOURCE_BYTES+1)
    if len(data)>MAX_SOURCE_BYTES:raise ValueError("Source exceeds 64 KiB")
    return SourceText(document_id=path.name,label=label,text=data.decode("utf-8"))

def request_from_files(v1,v2,tests=None):
    return ExtractionRequest(sources=(source(v1,"v1"),source(v2,"v2")),
        existing_tests_json=read_input(tests).decode("utf-8") if tests else "[]")

def summary(proposal):
    return dict(proposal_id=proposal.proposal_id,proposal_hash=content_hash(proposal),
        status=proposal.status,provider=proposal.provider,model=proposal.model,simulated=proposal.simulated,
        elapsed_ms=proposal.elapsed_ms,issues=list(proposal.issues),prompt_version=proposal.prompt_version,
        sources=[dict(document_id=s.document_id,document_hash=s.document_hash,label=s.label) for s in proposal.request.sources],
        next_step="Inspect with show --full. Review the interpretation against each source before approval.")

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,default=ROOT/"data"/"extraction.db")
    commands=parser.add_subparsers(dest="command",required=True)
    extract=commands.add_parser("extract")
    extract.add_argument("--v1",type=Path,required=True);extract.add_argument("--v2",type=Path,required=True)
    extract.add_argument("--tests",type=Path);extract.add_argument("--actor",required=True)
    extract.add_argument("--timeout",type=int,default=30)
    show=commands.add_parser("show");show.add_argument("--proposal",required=True);show.add_argument("--full",action="store_true")
    for name in ("review","promote"):
        sub=commands.add_parser(name);sub.add_argument("--proposal",required=True);sub.add_argument("--hash",required=True);sub.add_argument("--actor",required=True)
        if name=="review":
            sub.add_argument("--decision",choices=("approved","rejected"),required=True);sub.add_argument("--reason",required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=="extract":
            request=request_from_files(args.v1,args.v2,args.tests);provider=configured_provider()
            service=ExtractionService(Database(args.db),provider)
            result=summary(service.propose(request,actor=args.actor,timeout_seconds=args.timeout))
        else:
            if not args.db.is_file():raise ValueError("Extraction database does not exist")
            service=ExtractionService(Database(args.db))
            if args.command=="show":
                proposal=service.get(args.proposal);result=summary(proposal)
                if args.full:
                    result["proposal"]=proposal.to_dict()
                    if proposal.response_json:result["output"]=json.loads(proposal.response_json) if proposal.status in ("pending_review","needs_clarification") else proposal.response_json
                try:result["review"]=service.review_record(args.proposal).to_dict()
                except NotFoundError:result["review"]=None
            elif args.command=="review":
                result=service.review(args.proposal,args.hash,decision=args.decision,reviewer=args.actor,reason=args.reason).to_dict()
            else:result=workflow_summary(service.promote(args.proposal,args.hash,actor=args.actor))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (FactoryError,ValueError,TypeError,OSError) as exc:
        print(json.dumps(dict(error=str(exc)),ensure_ascii=False),file=sys.stderr);return 2

if __name__=="__main__":sys.exit(main())
