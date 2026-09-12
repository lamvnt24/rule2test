"""Restore only the six known synthetic fixture files; databases and evidence are untouched."""
import sys,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.seed_demo import seed,DEMO_DIR

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--directory",type=Path,default=DEMO_DIR)
    args=parser.parse_args(argv)
    try:
        for path in seed(args.directory,overwrite=True):print("Restored "+path)
        return 0
    except (OSError,ValueError,ImportError) as exc:print("Error: "+str(exc),file=sys.stderr);return 2

if __name__=="__main__":sys.exit(main())
