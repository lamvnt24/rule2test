"""Assemble a self-contained folder for demonstrating and testing Rule2Test on another machine.

Every expected result in the kit is produced by executing the real pipeline here, not typed by hand,
so the kit cannot drift away from what the software actually does.
"""
import argparse,hashlib,json,shutil,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.api.dependencies import Application
from factory.api.routes.workspace import WorkspaceRoutes
from factory.models import content_hash
from factory.parsers.common import strict_json,read_input
from factory.providers.llm.mock import MockLLMProvider
from factory.repositories.connection import Database
from factory.services.extraction_service import ExtractionService
from factory.services.quality_gate_service import QualityGateService
from scripts.extraction_cli import request_from_files

ROOT=Path(__file__).resolve().parents[1]
KIT=ROOT/"demo-kit"
SUT=dict(min_age=18,max_age=65,claim_threshold="150000000",deductible="10000000",currency="VND")
SCENARIOS=(("eligibility","none"),("eligibility","boundary"),
           ("claim_review","none"),("claim_review","boundary"),
           ("deductible","none"),("deductible","deductible_off_by_one"))
HEADLINE="eligibility"

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run_scenarios():
    """Drive every profile and fault through the real services and record what actually happens."""
    rows=[];coverage={}
    with tempfile.TemporaryDirectory(prefix="rule2test-demo-kit-") as directory:
        app=Application(Path(directory)/"kit.db");routes=WorkspaceRoutes(app)
        for profile,fault in SCENARIOS:
            def action(w,name,**extra):
                return routes.post("/api/v1/workflows/"+w["workflow_id"]+"/"+name,
                                   dict(revision=w["revision"],actor="Demo kit QA",**extra))
            w=routes.post("/api/v1/demo",dict(profile=profile,actor="Demo kit BA"))
            w=action(w,"analyze")
            if profile not in coverage:
                detail=routes.get("/api/v1/workflows/"+w["workflow_id"],{})
                coverage[profile]=dict(tests=len(detail["workflow"]["tests"]),
                    designed={key:detail["coverage"][key]["percent"] for key in ("rule","branch","boundary","exception")})
            w=action(w,"start-review")
            tests=app.workflow.get(w["workflow_id"]).tests
            w=action(w,"review",tests=[dict(test_id=t.test_id,revision=t.revision) for t in tests],
                     decision="approved",reason="Scripted kit approvals; not a human acceptance measurement")
            w=action(w,"finalize",reason="Demo kit fixture")
            run=action(w,"execute",sut=dict(profile=profile,fault=fault,**SUT))
            executions=run["run"]["executions"];w=run["workflow"]
            w=action(w,"evidence")["workflow"]
            report=QualityGateService(app.db).evaluate(w["workflow_id"])
            blocking=[c["key"] for c in report["checks"] if c["status"]!="PASS"]
            rows.append(dict(profile=profile,fault=fault,tests=len(executions),
                passed=sum(e["status"]=="pass" for e in executions),
                failed=sum(e["status"]=="fail" for e in executions),
                errored=sum(e["status"]=="error" for e in executions),
                verdict=report["verdict"],blocking_checks=blocking,
                failing_inputs=[e["test_id"] for e in executions if e["status"]!="pass"]))
    return rows,coverage

def run_extractions():
    """Mock extraction over the shipped Japanese source pairs, compared with the separate truth files."""
    rows=[]
    with tempfile.TemporaryDirectory(prefix="rule2test-kit-extract-") as directory:
        service=ExtractionService(Database(Path(directory)/"extract.db"),MockLLMProvider())
        for folder in sorted(p for p in (ROOT/"data"/"ai_samples").iterdir() if p.is_dir()):
            request=request_from_files(folder/"rules_v1.txt",folder/"rules_v2.txt",folder/"existing_tests.json")
            proposal=service.propose(request,actor="Demo kit evaluator")
            truth=strict_json(read_input(folder/"ground_truth.json").decode("utf-8"))
            rows.append(dict(sample=folder.name,status=proposal.status,expected_status=truth["status"],
                issues=list(proposal.issues),simulated=proposal.simulated,provider=proposal.provider))
    return rows

def copy_tree(source,target,pattern="*"):
    target.mkdir(parents=True,exist_ok=True)
    copied=[]
    for item in sorted(Path(source).glob(pattern)):
        if item.is_file():
            shutil.copy2(item,target/item.name);copied.append(target/item.name)
    return copied

def expectations_markdown(rows,coverage,extractions):
    lines=["# What you should see","",
        "Every number here was produced by running this repository's own services while the kit was built.",
        "Nothing is estimated. Synthetic data throughout; these are not production measurements.","",
        "## Analyze — designed coverage before you review anything","",
        "| Scenario | Candidate tests | Rule | Branch | Boundary | Exception |","| --- | --- | --- | --- | --- | --- |"]
    for profile,data in coverage.items():
        percent=lambda key:"N/A" if data["designed"][key] is None else f"{data['designed'][key]:.0f}%"
        lines.append(f"| {profile} | {data['tests']} | {percent('rule')} | {percent('branch')} | {percent('boundary')} | {percent('exception')} |")
    lines+=["","## Execute and evaluate the gate","",
        "| Scenario | Injected fault | Pass | Fail | Error | Gate | Blocked by |","| --- | --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        lines.append(f"| {row['profile']} | {row['fault']} | {row['passed']} | {row['failed']} | {row['errored']} | "
                     f"**{row['verdict']}** | {', '.join(row['blocking_checks']) or '—'} |")
    lines+=["",
        "The deductible scenario is NO-GO even with no injected fault: the bounded search cannot prove away its",
        "default branch, so an obligation stays unresolved. That is the intended contract, not a bug — say so if",
        "a judge asks.","",
        "## AI rule review — offline mock provider","",
        "| Source pair | Extraction status | Authored truth |","| --- | --- | --- |"]
    for row in extractions:
        lines.append(f"| {row['sample']} | {row['status']} | {row['expected_status']} |")
    lines+=["",
        "The mock replays the three exact shipped fixtures and refuses anything else, which is why `ambiguous`",
        "asks for clarification. That is the correct answer for it, not a failure. A live model is configured",
        "separately; see LIVE_AI.md.","",
        "## Things that are deliberately not proven here","",
        "- Coverage is not a pass rate and a GO verdict is not release authorization.",
        "- Mock extraction is fixture replay, not language understanding.",
        "- Reviewer acceptance, effort savings, production accuracy and token cost are unmeasured.",""]
    return "\n".join(lines)

def readme(rows,coverage,has_executable):
    headline=next(r for r in rows if r["profile"]==HEADLINE and r["fault"]=="none")
    faulted=next(r for r in rows if r["profile"]==HEADLINE and r["fault"]=="boundary")
    start=("1. Run `app/rule2test.exe`. It checks its own preconditions, starts the workspace and opens a browser."
           if has_executable else
           "1. From a source checkout run `py -3 -B scripts/run_demo.py --seed`, or build the executable first\n"
           "   with `py -3 -m PyInstaller packaging/rule2test.spec --noconfirm --clean` and drop it into `app/`.")
    return f"""# Rule2Test — demo and test kit

Everything needed to run, demonstrate and check Rule2Test on a machine that has none of the source code.
Synthetic data throughout.

## Start here — five minutes

{start}
2. Type any reviewer name in the header. It is self-declared; there is no authentication.
   Vietnamese readers: `docs/vi/HUONG-DAN-SU-DUNG.md` walks through everything below in detail.
3. **Document intake → Eligibility · age 60 → 65 → Create synthetic workflow.**
4. **Analyze & generate.** You should get **{coverage[HEADLINE]['tests']} candidate tests**.
5. **Open test review**, select all, write a reason, **Approve selected**, then **Finalize review**.
6. **Run & evidence → Execute approved tests** with fault *None*: **{headline['passed']} pass, {headline['failed']} fail**.
7. **Create evidence pack**, then **Evaluate current revision**: **{headline['verdict']}**.
8. **Reopen review** with a reason, re-approve, re-finalize, set fault to **Boundary**, execute again and
   evaluate again: **{faulted['passed']} pass, {faulted['failed']} fail**, gate **{faulted['verdict']}**.

Step 8 is the point of the whole demo. Full minute-by-minute scripts, speaker notes and a recovery path for
every step that can fail are in `docs/COMPETITION_DEMO.md`.

## What is in this folder

| Path | What it is |
| --- | --- |
| `EXPECTED-RESULTS.md` | Every number you should see, produced by running the real pipeline |
| `expectations.json` | The same results as data, for automated checking |
| `MANIFEST.json` | Every file with its SHA-256, so you can verify nothing was altered in transit |
| `docs/` | Demo script, benchmarks, architecture diagrams, observability and packaging guides |
| `docs/vi/` | Vietnamese system overview, roadmap and step-by-step user guide |
| `docs/slides/final-round2.pdf` | Round 2 final-submission deck for Track 2, in Vietnamese — hand this to the organisers |
| `docs/slides/final-round2.html` | The same deck as a live page, for presenting |
| `docs/slides/index.html` | General pitch deck; open it from disk, arrow keys to navigate |
| `data/import/` | Versioned JSON and XLSX documents to import through **Document intake** |
| `data/ai-extraction/` | Japanese rule-document pairs for **AI rule review**, with separate truth files |
| `data/ai-profiles/` | Offline mock profile and a template for pinning a real local model |
| `backup/` | Screenshot replay of the whole demo, for when the live run cannot happen |
| `app/` | The portable executable, if it was built when this kit was assembled |

## Verify the kit arrived intact

`MANIFEST.json` lists every file with its SHA-256. On the target machine, with no Python needed:

```powershell
$m = Get-Content MANIFEST.json | ConvertFrom-Json
$m.files | ForEach-Object {{
  $actual = (Get-FileHash $_.path -Algorithm SHA256).Hash.ToLower()
  if ($actual -ne $_.sha256) {{ "CHANGED: " + $_.path }}
}}
```

Silence means every file matches. This detects corruption in transit; it is not a signature.

## Testing it rather than demonstrating it

- `app/rule2test.exe check` runs the preflight alone and exits 2 if something is wrong.
- Import each file in `data/import/` and compare against `EXPECTED-RESULTS.md`.
- Load each pair in `data/ai-extraction/` through **AI rule review**: paste `rules_v1.txt` and
  `rules_v2.txt` into the two source boxes, then compare the proposal status with the
  `ground_truth.json` beside them. The truth file is never shown to the provider. The optional
  *Existing tests JSON* box is inside a collapsed **Existing tests JSON** section — expand it first
  if you want to supply `existing_tests.json`; leaving it empty is fine.
- **Overview → Run diagnostics** shows request counts, durations and the logging configuration for the
  running process. Counters reset when you stop the application.

## If something fails

Every error message carries a trace id, and the same id appears in the console output. Provider failures are
classified with a remediation hint and are never retried or silently replaced by mock output. `docs/OBSERVABILITY.md`
explains the diagnostics surface; `docs/COMPETITION_DEMO.md` has the recovery table.

## Honest limits

- Windows x64 only, and the executable is unsigned, so SmartScreen warns on first run.
- Live AI needs a local Ollama service and installed models on the target machine. Without one the kit runs on
  offline mock providers, labelled simulated everywhere they appear.
- SHA-256 in `MANIFEST.json` detects corruption in transit. It is not a signature.
"""

def build(target,*,force):
    if target.exists():
        if not force:raise ValueError(f"{target} already exists; pass --force to rebuild it")
        try:shutil.rmtree(target)
        except PermissionError as exc:
            # Windows refuses to remove a directory that any process is sitting in.
            raise ValueError(f"Cannot replace {target}: a program is using it. Close any terminal, "
                             "editor or Explorer window open inside that folder and run this again") from exc
    rows,coverage=run_scenarios()
    extractions=run_extractions()

    docs=target/"docs";docs.mkdir(parents=True)
    for name in ("COMPETITION_DEMO.md","BENCHMARKS.md","DIAGRAMS.md","OBSERVABILITY.md","PACKAGING.md",
                 "QUALITY_GATE.md","LIVE_AI.md","WORKSPACE.md","IMPORT_FORMAT.md"):
        source=ROOT/"docs"/name
        if source.is_file():shutil.copy2(source,docs/name)
    vietnamese=ROOT/"docs"/"vi"
    if vietnamese.is_dir():copy_tree(vietnamese,docs/"vi","*.md")
    (docs/"slides").mkdir()
    for name in ("index.html","final-round2.html","index.pdf","final-round2.pdf"):
        source=ROOT/"docs"/"slides"/name
        if source.is_file():shutil.copy2(source,docs/"slides"/name)

    copy_tree(ROOT/"data"/"demo",target/"data"/"import","*.json")
    copy_tree(ROOT/"data"/"demo",target/"data"/"import","*.xlsx")
    for folder in sorted(p for p in (ROOT/"data"/"ai_samples").iterdir() if p.is_dir()):
        copy_tree(folder,target/"data"/"ai-extraction"/folder.name)
    profiles=target/"data"/"ai-profiles";profiles.mkdir(parents=True)
    shutil.copy2(ROOT/"data"/"ai_profiles"/"mock.json",profiles/"mock.json")
    (profiles/"ollama.template.json").write_text(json.dumps(dict(
        mode="ollama",extraction_model="REPLACE_WITH_AN_INSTALLED_CHAT_TAG",extraction_digest="0"*64,
        suggestion_model="REPLACE_WITH_AN_INSTALLED_CHAT_TAG",suggestion_digest="0"*64,
        embedding_model="REPLACE_WITH_AN_INSTALLED_EMBEDDING_TAG",embedding_digest="0"*64,
        embedding_dimensions=768,embedding_device="cpu",timeout_seconds=60,schema_version=1),
        ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (profiles/"README.md").write_text(
        "# AI profiles\n\n`mock.json` is the offline default and needs nothing installed.\n\n"
        "`ollama.template.json` is a placeholder, not a working profile: the digests are zeros and the model\n"
        "tags are not real. Generate a valid one on the target machine, where the real digests exist:\n\n"
        "```powershell\n.\\rule2test.exe doctor\n"
        "py -3 -B scripts/ai_doctor.py --chat-model \"YOUR_TAG\" --embedding-model \"YOUR_TAG\" \\\n"
        "  --dimensions 768 --write-profile data/ai_profiles/ollama.local.json\n```\n\n"
        "No model is ever downloaded automatically, and there is no fallback to mock if a live model fails.\n",
        encoding="utf-8")

    capture=ROOT/"data"/"generated"/"demo-capture"
    if capture.is_dir():
        backup=target/"backup";backup.mkdir(parents=True)
        for item in sorted(capture.iterdir()):
            if item.is_file():shutil.copy2(item,backup/item.name)

    executable=ROOT/"dist"/"rule2test.exe"
    has_executable=executable.is_file()
    if has_executable:
        (target/"app").mkdir();shutil.copy2(executable,target/"app"/"rule2test.exe")

    payload=dict(schema_version=1,synthetic=True,
        scope="Produced by executing the real services while assembling this kit; nothing is estimated.",
        analyze=coverage,scenarios=rows,extraction=extractions,
        unmeasured=["real reviewer acceptance","manual effort savings","production accuracy","token usage and monetary cost"])
    (target/"expectations.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (target/"EXPECTED-RESULTS.md").write_text(expectations_markdown(rows,coverage,extractions),encoding="utf-8")
    (target/"README.md").write_text(readme(rows,coverage,has_executable),encoding="utf-8")

    files=sorted(p for p in target.rglob("*") if p.is_file() and p.name!="MANIFEST.json")
    manifest=dict(schema_version=1,kit="rule2test-demo-kit",files=[
        dict(path=str(p.relative_to(target)).replace("\\","/"),bytes=p.stat().st_size,sha256=digest(p)) for p in files])
    manifest["total_bytes"]=sum(f["bytes"] for f in manifest["files"])
    manifest["note"]="SHA-256 detects corruption in transit. It is an integrity check, not a signature."
    (target/"MANIFEST.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest,has_executable

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=KIT)
    parser.add_argument("--force",action="store_true",help="Replace an existing kit folder")
    args=parser.parse_args(argv)
    try:
        manifest,has_executable=build(args.output,force=args.force)
        print(json.dumps(dict(kit=str(args.output),files=len(manifest["files"]),
            megabytes=round(manifest["total_bytes"]/1048576,1),executable_included=has_executable),
            ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,TypeError) as exc:
        print(type(exc).__name__+": "+str(exc),file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
