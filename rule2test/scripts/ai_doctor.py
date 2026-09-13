"""Inspect local models, pin an explicit profile, or probe configured AI capabilities."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.ai_config import AIProfile, read_profile
from factory.services.ai_readiness_service import inventory, readiness
from factory.exceptions import FactoryError

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile",type=Path)
    parser.add_argument("--chat-model")
    parser.add_argument("--embedding-model")
    parser.add_argument("--dimensions",type=int)
    parser.add_argument("--embedding-device",choices=("auto","cpu"),default="auto")
    parser.add_argument("--write-profile",type=Path)
    parser.add_argument("--probe",action="store_true")
    args=parser.parse_args(argv)
    try:
        if args.write_profile:
            if args.profile or not args.chat_model or not args.embedding_model or not args.dimensions:
                raise ValueError("Profile creation requires chat-model, embedding-model and dimensions, without --profile")
            listing=inventory()
            installed={m["name"]:m["digest"] for m in listing["models"]}
            if args.chat_model not in installed or args.embedding_model not in installed:
                raise ValueError("Use exact installed model names from ai_doctor.py inventory; no models are downloaded")
            profile=AIProfile(mode="ollama",extraction_model=args.chat_model,extraction_digest=installed[args.chat_model],
                              suggestion_model=args.chat_model,suggestion_digest=installed[args.chat_model],
                              embedding_model=args.embedding_model,embedding_digest=installed[args.embedding_model],
                              embedding_dimensions=args.dimensions,embedding_device=args.embedding_device)
            report=readiness(profile,probe=True)
            if not report["live_ready"]:
                print(json.dumps(report,ensure_ascii=False,indent=2));return 2
            with args.write_profile.open("x",encoding="utf-8") as stream:stream.write(profile.to_json())
        elif args.profile:
            report=readiness(read_profile(args.profile),probe=args.probe)
        else:
            if args.probe:raise ValueError("--probe requires --profile or --write-profile")
            report=inventory()
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 2 if report.get("available") is False or report.get("status")=="blocked" else 0
    except (FactoryError,ValueError,TypeError,OSError) as exc:
        print(str(exc),file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())

