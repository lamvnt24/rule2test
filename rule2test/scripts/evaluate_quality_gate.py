"""Six independent synthetic gate expectations; no real-model or production accuracy claims."""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.api.dependencies import Application
from factory.api.routes.workspace import WorkspaceRoutes
from factory.services.quality_gate_service import QualityGateService

CASES = (
    ("eligibility","none","GO"),
    ("eligibility","boundary","NO-GO"),
    ("claim_review","none","GO"),
    ("claim_review","boundary","NO-GO"),
    # The bounded search cannot prove away the default branch in this fixture.
    ("deductible","none","NO-GO"),
    ("deductible","deductible_off_by_one","NO-GO"),
)
def run():
    results=[]
    with tempfile.TemporaryDirectory(prefix="rule2test-quality-benchmark-") as directory:
        app=Application(Path(directory)/"benchmark.db")
        routes=WorkspaceRoutes(app)
        for profile,fault,expected in CASES:
            started=time.perf_counter()
            def action(w,name,**extra):
                return routes.post("/api/v1/workflows/"+w["workflow_id"]+"/"+name,
                                   dict(revision=w["revision"],actor="Synthetic benchmark QA",**extra))
            w=routes.post("/api/v1/demo",dict(profile=profile,actor="Synthetic benchmark BA"))
            w=action(w,"analyze");w=action(w,"start-review")
            tests=app.workflow.get(w["workflow_id"]).tests
            w=action(w,"review",tests=[dict(test_id=t.test_id,revision=t.revision) for t in tests],
                     decision="approved",reason="Scripted fixture approvals; not human acceptance measurements")
            w=action(w,"finalize",reason="Synthetic benchmark only")
            sut=dict(profile=profile,fault=fault,min_age=18,max_age=65,claim_threshold="150000000",
                     deductible="10000000",currency="VND")
            w=action(w,"execute",sut=sut)["workflow"]
            w=action(w,"evidence")["workflow"]
            report=QualityGateService(app.db).evaluate(w["workflow_id"])
            results.append(dict(profile=profile,fault=fault,expected=expected,actual=report["verdict"],
                                matched=expected==report["verdict"],elapsed_ms=round((time.perf_counter()-started)*1000),
                                report=report))
    return dict(benchmark="synthetic-gate-contract-v1",simulated=True,
                meaning="Gate contract checks; not seeded-gap recall or real-model quality",
                matched=sum(r["matched"] for r in results),total=len(results),cases=results)
def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args(argv)
    result=run()
    if args.output:
        with args.output.open("x",encoding="utf-8") as stream:
            json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(benchmark=result["benchmark"],simulated=True,matched=result["matched"],
                         total=result["total"],cases=[{k:v for k,v in r.items() if k!="report"} for r in result["cases"]])))
    return 0 if result["matched"]==result["total"] else 1
if __name__=="__main__":raise SystemExit(main())
