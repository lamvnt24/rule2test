"""Build reviewed knowledge, search, propose inputs, and attach pending tests."""
import sys,json,argparse,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.repositories.connection import Database
from factory.services.knowledge_service import KnowledgeService
from factory.providers.embedding.factory import configured_embedding
from factory.services.retrieval_generation_service import RetrievalGenerationService
from factory.providers.vector.base import PythonVectorBackend
from factory.providers.vector.faiss import FaissVectorBackend
from factory.providers.llm.test_suggestions import MockTestSuggestionProvider,OllamaTestSuggestionProvider
from factory.models import content_hash
from factory.exceptions import FactoryError,ConfigurationError
from scripts.workflow_cli import summary

ROOT=Path(__file__).resolve().parents[1]
def suggestion_provider():
    name=os.environ.get("RULE2TEST_SUGGESTION_PROVIDER","mock")
    if name=="mock":return MockTestSuggestionProvider()
    if name=="ollama":return OllamaTestSuggestionProvider(os.environ.get("RULE2TEST_SUGGESTION_MODEL",""))
    raise ConfigurationError("Suggestion provider must be mock or ollama")

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,default=ROOT/"data"/"retrieval.db")
    parser.add_argument("--backend",choices=("python","faiss"),default="python")
    commands=parser.add_subparsers(dest="command",required=True)
    build=commands.add_parser("build");build.add_argument("--workflow",action="append",required=True);build.add_argument("--actor",required=True)
    search=commands.add_parser("search");search.add_argument("--index",required=True);search.add_argument("--query",required=True)
    search.add_argument("--field",action="append",default=[]);search.add_argument("--rule-id",action="append",default=[])
    search.add_argument("--kind",choices=("rule","test"));search.add_argument("--workflow",action="append",default=[]);search.add_argument("--top-k",type=int,default=5)
    propose=commands.add_parser("propose")
    for name in ("workflow","index","query","actor"):propose.add_argument("--"+name,required=True)
    propose.add_argument("--revision",required=True,type=int);propose.add_argument("--timeout",type=int,default=30)
    show=commands.add_parser("show");show.add_argument("--batch",required=True)
    attach=commands.add_parser("attach");attach.add_argument("--batch",required=True);attach.add_argument("--hash",required=True);attach.add_argument("--actor",required=True)
    args=parser.parse_args(argv)
    try:
        if not args.db.is_file():raise ValueError("Choose an existing workflow database, or run run_retrieval_demo.py first")
        db=Database(args.db);knowledge=KnowledgeService(db,embedding=configured_embedding(),backend=FaissVectorBackend() if args.backend=="faiss" else PythonVectorBackend())
        service=RetrievalGenerationService(db,knowledge=knowledge)
        if args.command=="build":
            index=knowledge.build(tuple(args.workflow),actor=args.actor)
            result=dict(index_id=index.index_id,index_hash=content_hash(index),records=len(index.records),embedding=index.embedding_identity,simulated=index.simulated)
        elif args.command=="search":
            hits=knowledge.search(args.index,args.query,fields=tuple(args.field),rule_ids=tuple(args.rule_id),kind=args.kind,workflow_ids=tuple(args.workflow),top_k=args.top_k)
            result=dict(backend=knowledge.backend.name,simulated=knowledge.get(args.index).simulated,hits=[h.to_dict() for h in hits])
        elif args.command=="propose":
            service.provider=suggestion_provider()
            batch=service.propose(args.workflow,args.revision,args.index,args.query,actor=args.actor,timeout_seconds=args.timeout)
            result=batch.to_dict();result["batch_hash"]=content_hash(batch)
        elif args.command=="show":
            batch=service.get(args.batch);result=batch.to_dict();result["batch_hash"]=content_hash(batch)
        else:result=summary(service.attach(args.batch,args.hash,actor=args.actor))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (FactoryError,ValueError,TypeError,OSError) as exc:
        print(json.dumps(dict(error=str(exc)),ensure_ascii=False),file=sys.stderr);return 2
if __name__=="__main__":sys.exit(main())
