"""Aggregate every number this repository has actually measured. Nothing is computed, estimated or invented here."""
import argparse,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.parsers.common import strict_json

ROOT=Path(__file__).resolve().parents[1]
SUMMARY=ROOT/"data"/"generated"/"benchmark-summary.json"
DOCUMENT=ROOT/"docs"/"BENCHMARKS.md"

def read(relative):
    path=ROOT/relative
    if not path.exists():return None
    with path.open("rb") as stream:raw=stream.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:return None
    try:return strict_json(raw.decode("utf-8"))
    except (ValueError,UnicodeError):return None

def entry(name,value,source,measures,excludes,created=""):
    return dict(name=name,value=value,source=source,measures=measures,does_not_prove=excludes,created_at=created)

def gate_rows():
    source="data/generated/quality-gate-benchmark.json";report=read(source)
    if report is None:return []
    return [entry("Quality-gate contract cases matched",f"{report['matched']}/{report['total']}",source,
        "Six synthetic workflows reach the GO/NO-GO verdict the contract requires, including the deliberate NO-GO fixtures.",
        "Not seeded-gap recall, not real-model quality, and not production release authorization.")]

def evaluation_rows(run,label):
    source="data/generated/"+run+"/report.json";report=read(source)
    if report is None:return []
    created=report.get("created_at","");rows=[]
    stages=report.get("stages",{})
    extraction=stages.get("extraction")
    if extraction:
        categories=", ".join(f"{k} {v['matched']}/{v['total']}" for k,v in sorted(extraction.get("categories",{}).items()))
        rows.append(entry(label+" — extraction cases matched",f"{extraction['matched']}/{extraction['total']}",source,
            f"Authored Japanese single-rule spot checks against separate ground truth ({extraction.get('model','')}). Breakdown: {categories}.",
            "Ten authored cases only. Not representative Japanese document accuracy and not an SME-reviewed benchmark.",created))
        rows.append(entry(label+" — schema and citation valid",f"{extraction['schema_and_citation_valid']}/{extraction['total']}",source,
            "Outputs that survived strict JSON, schema and exact-line citation validation before truth comparison.",
            "A valid citation proves the quote exists, not that the interpretation is semantically correct.",created))
        if extraction.get("median_elapsed_ms") is not None:
            rows.append(entry(label+" — median extraction latency",f"{extraction['median_elapsed_ms']:.0f} ms",source,
                "Host-measured wall-clock time per case on the machine that produced this artifact.",
                "Includes cold model loading and host validation. Not a throughput or cost measurement.",created))
    retrieval=stages.get("retrieval")
    if retrieval and retrieval.get("status")=="completed":
        rows.append(entry(label+" — retrieval top-1",f"{retrieval['top1_correct']}/{retrieval['queries']}",source,
            f"Hybrid lexical+vector ranking put the expected workflow first. MRR@3 {retrieval['mrr_at_3']:.3f}.",
            "Only three approved test records are indexed, so this measures ranking on a tiny corpus, not embedding quality.",created))
    suggestions=stages.get("suggestions")
    if suggestions and suggestions.get("status")=="completed":
        rows.append(entry(label+" — age-66 ALLOW witness found",str(suggestions["witness_age_66_allow_found"]),source,
            "One fixed witness: the retrieved age-66 input is recomputed as ALLOW against the new 18..70 policy.",
            "A single witness plus grounding checks. The host oracle computes the expected outcome, so this is not model reasoning accuracy.",created))
        rows.append(entry(label+" — evaluated proposals auto-approved",str(suggestions.get("automatic_approvals",False)),source,
            "The evaluator never approves, promotes or attaches anything it generated.",
            "Nothing. This is a guardrail check, not a performance measurement.",created))
    return rows

def analysis_rows():
    source="data/generated/phase3-analysis-report.json";report=read(source)
    if report is None:return []
    return [entry("Designed boundary coverage, baseline to final",
        f"{report['baseline_boundary_percent']}% → {report['final_boundary_percent']}%",source,
        "Boundary obligations covered by the existing suite versus the suite after generated candidates, on the synthetic eligibility scenario.",
        "Designed coverage on one synthetic scenario. Coverage is not a pass rate and not release approval.",),
        entry("Mutation score on the same scenario",f"{report['mutation_score']}%",source,
        "Specification mutants killed by the designed suite.",
        "A small fixed mutant set on one scenario; not a general fault-detection rate.")]

def suite_rows(skip_tests):
    # Never drop the row silently: an omitted measurement must read as omitted, not as absent.
    if skip_tests:
        return [entry("Automated test suite","not run in this collection","tests/",
            "The collector was invoked with --skip-tests, so no suite result was recorded.",
            "Nothing. Run scripts/collect_benchmarks.py without --skip-tests for the real figure.")]
    result=subprocess.run([sys.executable,"-B","-m","unittest","discover","-s","tests"],cwd=ROOT,capture_output=True,text=True)
    tail=[line for line in result.stderr.splitlines() if line.startswith("Ran ")]
    if not tail:return []
    outcome="passing" if result.returncode==0 else "FAILING"
    count=tail[0].split()[1]
    return [entry("Automated test suite",count+" "+outcome,"tests/",
        "Unit, integration and evaluation tests on the machine producing this summary ("+tail[0].lower()+").",
        "Test count is not a quality metric; it does not measure insurance-domain correctness.")]

def collect(skip_tests=False):
    rows=gate_rows()+analysis_rows()
    rows+=evaluation_rows("phase10-mock-evaluation","Offline mock replay")
    rows+=evaluation_rows("phase10-cloud-evaluation","Live cloud model, prompt v1")
    rows+=evaluation_rows("phase10-cloud-prompt-v2","Live cloud model, prompt v2")
    rows+=suite_rows(skip_tests)
    return dict(schema_version=1,synthetic=True,entries=rows,
        scope="Every value is copied verbatim from an artifact in this repository; this script computes no new measurement.",
        unmeasured=["real reviewer acceptance","manual effort savings","production accuracy",
                    "token usage and monetary cost","independent SME-reviewed labels"],
        caveats=["The mock replay and the live model numbers are not comparable: mock extraction matches only exact fixtures.",
                 "Prompt v2 was written after inspecting prompt v1 failures, so it is not independent held-out validation.",
                 "Latency figures describe one machine and one run, including cold model loading."])

def markdown(summary):
    lines=["# Benchmarks","",
        "Every number below is copied from an artifact in this repository. The collector computes nothing.",
        "Regenerate with `py -3 -B scripts/collect_benchmarks.py --force`.","",
        "| Measurement | Value | What it measures | What it does not prove | Source |","| --- | --- | --- | --- | --- |"]
    for row in summary["entries"]:
        lines.append("| "+" | ".join((row["name"],"**"+row["value"]+"**",row["measures"],row["does_not_prove"],"`"+row["source"]+"`"))+" |")
    lines+=["","## How to read these numbers",""]
    lines+=["- "+text for text in summary["caveats"]]
    lines+=["","## Explicitly unmeasured",""]
    lines+=["- "+text for text in summary["unmeasured"]]
    lines+=["","Synthetic results are not production measurements. A GO verdict is a local regression assessment,",
        "not release authorization. See [quality gate](QUALITY_GATE.md) and [live AI](LIVE_AI.md).",""]
    return "\n".join(lines)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force",action="store_true",help="Overwrite the existing summary and document")
    parser.add_argument("--skip-tests",action="store_true",help="Do not run the test suite for the suite row")
    args=parser.parse_args(argv)
    try:
        summary=collect(args.skip_tests)
        if not summary["entries"]:
            print("No measurement artifacts found under data/generated.",file=sys.stderr);return 2
        for target,text in ((SUMMARY,json.dumps(summary,ensure_ascii=False,indent=2)),(DOCUMENT,markdown(summary))):
            if target.exists() and not args.force:
                print(f"{target} already exists; pass --force to replace it.",file=sys.stderr);return 2
            target.write_text(text,encoding="utf-8");print("Wrote "+str(target.relative_to(ROOT)))
        print(f"{len(summary['entries'])} measurements aggregated.")
        return 0
    except (OSError,ValueError,TypeError) as exc:
        print(type(exc).__name__+": "+str(exc),file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
