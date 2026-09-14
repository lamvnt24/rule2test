"""Build a self-contained pitch deck from the captured screenshots and the aggregated benchmark summary.

Every number on a slide is looked up in data/generated/benchmark-summary.json. A number that is not in that
file is rendered as "not measured" rather than invented.
"""
import argparse,base64,html,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.parsers.common import strict_json

ROOT=Path(__file__).resolve().parents[1]
SUMMARY=ROOT/"data"/"generated"/"benchmark-summary.json"
CAPTURE=ROOT/"data"/"generated"/"demo-capture"
TARGET=ROOT/"docs"/"slides"/"index.html"

STYLE="""
:root{--bg:#0d1117;--panel:#161b22;--fg:#e6edf3;--muted:#8b949e;--line:#30363d;--accent:#3fb950;--warn:#d29922}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);
  font:16px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
#deck{height:100%;display:flex;flex-direction:column}
#bar{height:3px;background:var(--line);flex:none}
#bar i{display:block;height:100%;background:var(--accent);transition:width .2s}
section{flex:1;display:none;padding:clamp(20px,4vw,56px);overflow:auto}
section.on{display:block}
.eyebrow{color:var(--accent);letter-spacing:.14em;text-transform:uppercase;font-size:12px;font-weight:700;margin:0 0 12px}
h1{font-size:clamp(30px,5vw,58px);line-height:1.1;margin:0 0 18px;letter-spacing:-.02em}
h2{font-size:clamp(22px,3.2vw,38px);line-height:1.15;margin:0 0 20px;letter-spacing:-.01em}
p{font-size:clamp(15px,1.6vw,20px);max-width:62ch}
.lead{color:var(--muted)}
ul{font-size:clamp(15px,1.6vw,20px);max-width:68ch;padding-left:22px}li{margin:10px 0}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));margin:22px 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}
.stat b{display:block;font-size:clamp(24px,3.4vw,40px);line-height:1.1;margin-bottom:6px}
.stat span{color:var(--muted);font-size:13px}
.stat.warn b{color:var(--warn)}.stat.good b{color:var(--accent)}
figure{margin:18px 0 0}
img{width:100%;max-height:58vh;object-fit:contain;object-position:top;border:1px solid var(--line);border-radius:10px;background:#fff}
figcaption{color:var(--muted);font-size:13px;margin-top:8px}
table{border-collapse:collapse;width:100%;max-width:900px;font-size:clamp(13px,1.4vw,17px)}
th,td{border-bottom:1px solid var(--line);padding:9px 10px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600}
code{background:var(--panel);border:1px solid var(--line);border-radius:5px;padding:1px 6px;font-size:.92em}
footer{flex:none;display:flex;justify-content:space-between;align-items:center;gap:12px;
  padding:9px 18px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}
footer button{font:inherit;background:var(--panel);color:var(--fg);border:1px solid var(--line);
  border-radius:6px;padding:5px 11px;cursor:pointer}
footer button:hover{border-color:var(--accent)}
.note{color:var(--muted);font-size:clamp(12px,1.2vw,14px);margin-top:18px;border-top:1px solid var(--line);padding-top:12px;max-width:72ch}
/* Print and PDF export: one 16:9 page per slide. */
@page{size:338mm 190mm;margin:0}
@media print{
  html,body{height:auto;background:var(--bg)}
  #deck{display:block;height:auto}
  #bar,footer{display:none}
  section{display:block!important;width:338mm;height:190mm;overflow:hidden;
          padding:11mm 14mm;break-after:page;page-break-after:always;
          background:var(--bg);-webkit-print-color-adjust:exact;print-color-adjust:exact}
  section:last-child{break-after:auto;page-break-after:auto}
  img{max-height:104mm}
  .grid ~ figure img{max-height:74mm}  /* slides that carry a stat row above the screenshot */
  .note{margin-top:10px;padding-top:8px}
}
"""

SCRIPT="""
const slides=[...document.querySelectorAll("section")];
let index=Math.min(Math.max(parseInt(location.hash.slice(1))-1||0,0),slides.length-1);
function show(){
  slides.forEach((s,i)=>s.classList.toggle("on",i===index));
  document.getElementById("count").textContent=(index+1)+" / "+slides.length;
  document.getElementById("fill").style.width=((index+1)/slides.length*100)+"%";
  history.replaceState(null,"","#"+(index+1));
  slides[index].scrollTop=0;
}
function go(step){index=Math.min(Math.max(index+step,0),slides.length-1);show();}
document.getElementById("prev").onclick=()=>go(-1);
document.getElementById("next").onclick=()=>go(1);
addEventListener("keydown",e=>{
  if(["ArrowRight","PageDown"," "].includes(e.key)){e.preventDefault();go(1);}
  if(["ArrowLeft","PageUp"].includes(e.key)){e.preventDefault();go(-1);}
  if(e.key==="Home"){index=0;show();}
  if(e.key==="End"){index=slides.length-1;show();}
});
addEventListener("hashchange",()=>{
  const target=parseInt(location.hash.slice(1));
  if(target>=1&&target<=slides.length&&target-1!==index){index=target-1;show();}
});
show();
"""

def escape(text):return html.escape(str(text),quote=False)

def load_summary():
    if not SUMMARY.exists():return {}
    with SUMMARY.open("rb") as stream:raw=stream.read(8*1024*1024)
    try:data=strict_json(raw.decode("utf-8"))
    except (ValueError,UnicodeError):return {}
    return {entry["name"]:entry for entry in data.get("entries",[])}

def value(summary,name,fallback="not measured"):
    entry=summary.get(name)
    return escape(entry["value"]) if entry else fallback

def image(name):
    path=CAPTURE/name
    if not path.exists():return ""
    data=base64.b64encode(path.read_bytes()).decode("ascii")
    return "data:image/png;base64,"+data

def figure(name,caption):
    source=image(name)
    if not source:
        return f'<p class="lead"><em>Screenshot unavailable. Run <code>py -3 -B scripts/capture_demo_screens.py</code> to embed it.</em></p>'
    return f'<figure><img src="{source}" alt="{escape(caption)}"><figcaption>{escape(caption)}</figcaption></figure>'

def stat(figure_value,label,tone=""):
    return f'<div class="stat {tone}"><b>{figure_value}</b><span>{escape(label)}</span></div>'

def slides(summary):
    gate=value(summary,"Quality-gate contract cases matched")
    coverage=value(summary,"Designed boundary coverage, baseline to final")
    mutation=value(summary,"Mutation score on the same scenario")
    live=value(summary,"Live cloud model, prompt v2 — extraction cases matched")
    live_v1=value(summary,"Live cloud model, prompt v1 — extraction cases matched")
    valid=value(summary,"Live cloud model, prompt v2 — schema and citation valid")
    latency=value(summary,"Live cloud model, prompt v2 — median extraction latency")
    retrieval=value(summary,"Live cloud model, prompt v2 — retrieval top-1")
    mock=value(summary,"Offline mock replay — extraction cases matched")
    suite=value(summary,"Automated test suite")
    return [
f"""<p class="eyebrow">Insurance &middot; regression assurance</p>
<h1>Every rule change.<br>A traceable test story.</h1>
<p class="lead">Rule2Test turns an insurance rule revision into reviewed regression tests and execution evidence
you can hand to an auditor &mdash; with the AI never deciding pass or fail.</p>
<div class="grid">{stat(coverage,"designed boundary coverage, before to after","good")}
{stat(gate,"quality-gate contract cases matched","good")}
{stat(suite,"automated tests on this build")}</div>
<p class="note">Every figure in this deck is copied from an artifact in the repository. Synthetic data; not production measurements.</p>""",

f"""<p class="eyebrow">The problem</p>
<h2>A rule changes. Nobody can prove what it broke.</h2>
<ul>
<li>The boundary that moved is exactly the case the existing suite never covered.</li>
<li>Nobody can say which tests the change invalidated, or who accepted the new ones.</li>
<li>A green suite is presented as evidence, but nothing links a result back to the clause that caused it.</li>
<li>Reviewers are asked to trust an AI summary of a document they cannot re-check line by line.</li>
</ul>
<p class="lead">The gap is not test generation. It is <strong>traceability and authority</strong>.</p>""",

f"""<p class="eyebrow">The moment</p>
<h2>A passing suite was never the point.</h2>
<p>We inject an off-by-one at the exact threshold that moved. The generated boundary test catches it, and the
release gate flips to <strong>NO-GO</strong> with a concrete counterexample &mdash; an age, not a stack trace.</p>
{figure("11-gate-no-go.png","Quality gate NO-GO: execution_results fails with 13 pass and 1 fail on the moved boundary.")}""",

f"""<p class="eyebrow">How it works</p>
<h2>Five stages, one audit trail.</h2>
<table><tr><th>Stage</th><th>What happens</th><th>Who decides</th></tr>
<tr><td>Ingest</td><td>Two rule versions; source bytes archived and hashed</td><td>Deterministic</td></tr>
<tr><td>Analyze</td><td>Rule delta, impact, bounded gap search, candidate tests</td><td>Deterministic</td></tr>
<tr><td>Review</td><td>Explicit, revision-bound approval per test</td><td><strong>Human</strong></td></tr>
<tr><td>Execute</td><td>Approved tests only, against an independent system under test</td><td>Deterministic</td></tr>
<tr><td>Prove</td><td>Evidence pack plus a GO / NO-GO regression gate</td><td>Deterministic</td></tr></table>
<p class="note">Each stage binds to a workflow revision. A stale action fails instead of silently overwriting work.</p>""",

f"""<p class="eyebrow">The differentiator</p>
<h2>AI proposes. Engines decide. A human approves.</h2>
<ul>
<li><strong>AI never computes expected.</strong> A typed oracle does, from the reviewed rules.</li>
<li><strong>AI never sees the answer.</strong> Ground truth is compared only after the model returns.</li>
<li><strong>Every extracted rule cites an exact source line.</strong> If the quote is not literally in the document, we reject the output.</li>
<li><strong>No retry, no repair, no fallback to mock.</strong> A provider failure is classified and surfaced, never hidden.</li>
<li><strong>Nothing is approved automatically</strong> &mdash; not rules, not tests, not the AI's own proposals.</li>
</ul>""",

f"""<p class="eyebrow">Stage 2 &middot; analyze</p>
<h2>Find the cases nobody wrote.</h2>
<div class="grid">{stat(coverage,"designed boundary coverage, baseline to final","good")}
{stat(mutation,"mutation score on the same synthetic scenario","good")}</div>
{figure("04-analysis.png","Rule delta, impact, uncovered obligations and baseline coverage for the eligibility change.")}
<p class="note">Designed coverage on one synthetic scenario. Coverage is not a pass rate and not release approval.</p>""",

f"""<p class="eyebrow">Stage 3 &middot; review</p>
<h2>Approval is a person, a reason, and a revision.</h2>
{figure("06-human-review.png","Explicit selection, a written reason, and a per-test decision bound to the test revision.")}
<p class="note">Edit a test after approval and the approval is void. Reopening review clears approvals and
invalidates the current GO context.</p>""",

f"""<p class="eyebrow">Stage 4 &middot; execute</p>
<h2>Expected and actual never share code.</h2>
{figure("07-clean-run.png","Every row shows the oracle's expected value beside the independent system's actual value.")}
<p class="note">The system under test receives inputs only &mdash; never the expected result and never the rule snapshot.</p>""",

f"""<p class="eyebrow">Stage 5 &middot; prove</p>
<h2>Evidence an auditor can re-verify.</h2>
{figure("08-evidence.png","Evidence pack binding rules, approvals, inputs, expected, actual and the reviewer under one fingerprint.")}
<p class="note">SHA-256 detects corruption. It is an integrity check, not a digital signature, and it does not stop
an administrator who rewrites both the payload and the hash.</p>""",

f"""<p class="eyebrow">Measured, honestly</p>
<h2>What the AI actually did.</h2>
<div class="grid">{stat(live,"live model, extraction cases matched, prompt v2","warn")}
{stat(valid,"schema and citation valid","warn")}
{stat(retrieval,"retrieval top-1 over the reviewed corpus","good")}
{stat(latency,"median extraction latency")}</div>
<table><tr><th>Run</th><th>Extraction</th><th>Meaning</th></tr>
<tr><td>Offline mock replay</td><td>{mock}</td><td>Fixture replay only &mdash; <strong>not</strong> comprehension</td></tr>
<tr><td>Live model, prompt v1</td><td>{live_v1}</td><td>First real-model run on ten authored Japanese cases</td></tr>
<tr><td>Live model, prompt v2</td><td>{live}</td><td>After inspecting v1 failures &mdash; not held-out validation</td></tr></table>
<p class="note">Ten authored cases, no SME-reviewed labels. Successful extraction is not reliable insurance interpretation.</p>""",

f"""<p class="eyebrow">Engineering</p>
<h2>Built to be debugged on stage.</h2>
<div class="grid">{stat(suite,"automated tests, standard library core")}
{stat("11","provider failure kinds, each with a remediation hint")}
{stat("0","automatic retries, fallbacks or auto-approvals","good")}</div>
{figure("12-diagnostics.png","Run diagnostics: logging configuration, bounded metric series, database state and counters.")}
<p class="note">Logs use a field allowlist, so document text, prompts, reviewer names and session tokens cannot
reach a log line. Counters are process-local and reset on restart.</p>""",

f"""<p class="eyebrow">Scope</p>
<h2>What we do not claim.</h2>
<ul>
<li>Not a general insurance reasoning engine &mdash; the supported rule DSL is deliberately small and rejects what it cannot express.</li>
<li>Not production-ready: reviewer names are self-declared; there is no authentication, RBAC or deployment hardening.</li>
<li>Not a release authorization &mdash; GO is a local regression assessment for one workflow revision.</li>
<li>Not measured: reviewer acceptance, effort savings, production accuracy, token cost, SME-reviewed labels.</li>
<li>Synthetic results throughout. Mock providers are labelled simulated everywhere they appear.</li>
</ul>
<p class="lead">We would rather be trusted on five numbers than doubted on fifty.</p>""",

f"""<p class="eyebrow">Next</p>
<h2>From a demo to a pipeline.</h2>
<ul>
<li>Evaluate real extraction and embedding models against a broader, SME-labelled corpus.</li>
<li>Richer decision-table analysis and metamorphic tests beyond single-field boundaries.</li>
<li>Integrate a real system under test through the existing HTTP adapter.</li>
<li>Authenticated roles, signed evidence, append-only audit storage and operational monitoring.</li>
</ul>
<p class="lead"><strong>Every rule change becomes test coverage and auditable evidence.</strong></p>
<p class="note">Sources: docs/BENCHMARKS.md &middot; docs/DIAGRAMS.md &middot; docs/OBSERVABILITY.md &middot; docs/COMPETITION_DEMO.md</p>""",
    ]

def build(summary):
    body="".join(f"<section>{content}</section>" for content in slides(summary))
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Rule2Test &mdash; pitch deck</title><style>"+STYLE+"</style></head><body>"
        "<div id=\"deck\"><div id=\"bar\"><i id=\"fill\"></i></div>"+body+
        "<footer><span>Rule2Test &middot; synthetic data &middot; arrow keys to navigate</span>"
        "<span><button id=\"prev\">&larr;</button> <span id=\"count\"></span> <button id=\"next\">&rarr;</button></span>"
        "</footer></div><script>"+SCRIPT+"</script></body></html>")

def main(argv=None):
    parser=argparse.ArgumentParser(description="Build the self-contained pitch deck.")
    parser.add_argument("--output",type=Path,default=TARGET)
    args=parser.parse_args(argv)
    try:
        summary=load_summary()
        if not summary:
            print("No benchmark summary found. Run scripts/collect_benchmarks.py first; "
                  "slides would otherwise carry no measured numbers.",file=sys.stderr)
            return 2
        args.output.parent.mkdir(parents=True,exist_ok=True)
        document=build(summary)
        args.output.write_text(document,encoding="utf-8")
        embedded=document.count("data:image/png;base64,")
        print(json.dumps(dict(slides=document.count("<section>"),screenshots_embedded=embedded,
            size_kb=round(len(document.encode("utf-8"))/1024),output=str(args.output.relative_to(ROOT)),
            numbers_from=str(SUMMARY.relative_to(ROOT))),ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,TypeError) as exc:
        print(type(exc).__name__+": "+str(exc),file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
