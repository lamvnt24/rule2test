"""Offline synthetic replay demo; stops before rule approval."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.seed_ai_samples import seed,ROOT
from scripts.extraction_cli import main
if __name__=="__main__":
    seed()
    folder=ROOT/"data"/"ai_samples"/"eligibility"
    sys.exit(main(["--db",str(ROOT/"data"/"extraction-demo.db"),"extract",
        "--v1",str(folder/"rules_v1.txt"),"--v2",str(folder/"rules_v2.txt"),
        "--tests",str(folder/"existing_tests.json"),"--actor","Synthetic BA"]))
