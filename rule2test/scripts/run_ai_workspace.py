"""Start the existing workspace using an explicit AI profile; never falls back to mock."""
import argparse, os, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.ai_config import read_profile
from factory.services.ai_readiness_service import require_ready
from factory.exceptions import FactoryError

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile",type=Path,required=True)
    parser.add_argument("--db",type=Path,default=Path(__file__).resolve().parents[1]/"data"/"workspace.db")
    parser.add_argument("--port",type=int,default=8000)
    args=parser.parse_args(argv)
    try:
        profile=read_profile(args.profile)
        require_ready(profile)
        os.environ.update(profile.environment())
        from factory.server import main as serve
        print("AI mode: "+profile.mode+"; model digests checked at startup; human review remains required.",flush=True)
        serve(["--db",str(args.db),"--port",str(args.port)])
        return 0
    except (FactoryError,ValueError,TypeError,OSError) as exc:
        print(str(exc),file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
