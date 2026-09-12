"""Create synthetic Japanese source pairs, existing tests and separate evaluation truth."""
import sys,json,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.providers.llm.synthetic import SOURCE_PAIRS
from factory.parsers.templates import demo_payload

ROOT=Path(__file__).resolve().parents[1]
TRUTH={
    "eligibility":{"status":"pending_review","field":"age","old_values":[18,60],"new_values":[18,65],"operators":["ge","le"],"outcome":"allow","default":"deny","old_deductible":None,"new_deductible":None},
    "claim_review":{"status":"pending_review","field":"claim_amount","old_values":["100000000"],"new_values":["150000000"],"operators":["gt"],"outcome":"review","default":"allow","old_deductible":None,"new_deductible":None},
    "deductible":{"status":"pending_review","field":"claim_amount","old_values":["0"],"new_values":["0"],"operators":["ge"],"outcome":"payout","default":"invalid","old_deductible":"5000000","new_deductible":"10000000"},
}
def seed(directory=None):
    directory=Path(directory or ROOT/"data"/"ai_samples").resolve()
    planned={}
    for profile,pair in SOURCE_PAIRS.items():
        planned[profile+"/rules_v1.txt"]=pair[0];planned[profile+"/rules_v2.txt"]=pair[1]
        planned[profile+"/existing_tests.json"]=json.dumps(demo_payload(profile)["tests"],ensure_ascii=False,indent=2)+"\n"
        planned[profile+"/ground_truth.json"]=json.dumps(TRUTH[profile],ensure_ascii=False,indent=2)+"\n"
    planned["ambiguous/rules_v1.txt"]=SOURCE_PAIRS["eligibility"][0]
    planned["ambiguous/rules_v2.txt"]="合成資料：加入資格（新版）\n高齢者の加入条件を緩和する。上限年齢は未定。\n"
    planned["ambiguous/existing_tests.json"]="[]\n"
    planned["ambiguous/ground_truth.json"]='{"status":"needs_clarification"}\n'
    for name in planned:
        target=directory/name
        if target.is_symlink() or not target.resolve().is_relative_to(directory):raise ValueError("Sample target escapes sample directory")
    written=[]
    for name,text in planned.items():
        target=directory/name
        if target.exists():continue
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("x",encoding="utf-8",newline="") as stream:stream.write(text)
        written.append(str(target))
    return written

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--directory",type=Path)
    args=parser.parse_args(argv)
    try:
        paths=seed(args.directory);print(f"Created {len(paths)} files; existing files preserved.");return 0
    except (OSError,ValueError) as exc:print("Error: "+str(exc),file=sys.stderr);return 2

if __name__=="__main__":sys.exit(main())
