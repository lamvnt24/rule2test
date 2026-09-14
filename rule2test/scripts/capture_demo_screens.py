"""Capture the demo story as numbered screenshots plus a self-contained offline replay page.

No video file is produced. This is the rehearsed fallback when the live demo cannot run: the captions are the
same sentences as docs/COMPETITION_DEMO.md. It uses a temporary database and never touches data/workspace.db.
"""
import argparse,base64,json,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.api.dependencies import Application
from factory.observability import logger
from factory.server import WorkspaceServer

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"data"/"generated"/"demo-capture"
REVIEWER="Demo reviewer"
REASON="Inspected synthetic boundaries, source revisions and expected results"

PAGE="""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Rule2Test demo replay</title><style>
:root{color-scheme:light dark;--bg:#0f1115;--fg:#e8eaed;--muted:#9aa3af;--line:#2a2f3a;--accent:#7aa2f7}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:14px 20px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
h1{font-size:16px;margin:0}header small{color:var(--muted)}
main{padding:16px 20px;max-width:1500px;margin:0 auto}
figure{margin:0}img{width:100%;border:1px solid var(--line);border-radius:8px;display:block;background:#fff}
figcaption{margin-top:12px;font-size:17px;line-height:1.45}
.step{color:var(--accent);font-weight:600;margin-right:8px}
nav{display:flex;gap:8px;align-items:center;margin:14px 0;flex-wrap:wrap}
button{font:inherit;padding:8px 14px;border-radius:6px;border:1px solid var(--line);background:#1a1e27;color:var(--fg);cursor:pointer}
button:hover{border-color:var(--accent)}
.bar{height:4px;background:var(--line);border-radius:2px;overflow:hidden;margin-bottom:12px}
.bar i{display:block;height:100%;background:var(--accent)}
.note{color:var(--muted);font-size:13px;margin-top:18px;border-top:1px solid var(--line);padding-top:12px}
</style></head><body>
<header><h1>Rule2Test &mdash; demo replay</h1><small>Arrow keys or the buttons. Synthetic data. No video file is included.</small></header>
<main><div class="bar"><i id="bar"></i></div>
<nav><button id="prev">&larr; Previous</button><button id="next">Next &rarr;</button><span id="counter"></span></nav>
<figure><img id="shot" alt=""><figcaption><span class="step" id="step"></span><span id="caption"></span></figcaption></figure>
<p class="note" id="note"></p></main>
<script>
const FRAMES=__FRAMES__;
let index=0;
function render(){
  const frame=FRAMES[index];
  document.getElementById("shot").src=frame.image;
  document.getElementById("shot").alt=frame.caption;
  document.getElementById("caption").textContent=frame.caption;
  document.getElementById("step").textContent=frame.title;
  document.getElementById("counter").textContent=(index+1)+" / "+FRAMES.length;
  document.getElementById("bar").style.width=((index+1)/FRAMES.length*100)+"%";
  document.getElementById("note").textContent=frame.note||"";
}
document.getElementById("prev").onclick=()=>{index=(index-1+FRAMES.length)%FRAMES.length;render();};
document.getElementById("next").onclick=()=>{index=(index+1)%FRAMES.length;render();};
addEventListener("keydown",event=>{
  if(event.key==="ArrowRight"||event.key===" ")document.getElementById("next").click();
  if(event.key==="ArrowLeft")document.getElementById("prev").click();
});
render();
</script></body></html>
"""

def build_replay(frames,directory):
    payload=[]
    for frame in frames:
        data=base64.b64encode((directory/frame["file"]).read_bytes()).decode("ascii")
        payload.append(dict(title=frame["title"],caption=frame["caption"],note=frame.get("note",""),
                            image="data:image/png;base64,"+data))
    document=PAGE.replace("__FRAMES__",json.dumps(payload,ensure_ascii=False))
    (directory/"replay.html").write_text(document,encoding="utf-8")
    return directory/"replay.html"

def capture(directory,*,width,height):
    from playwright.sync_api import sync_playwright,expect
    # Diagnostics are on during the capture so the screenshots show a realistic run, and the
    # captured log becomes an artifact judges can inspect line by line.
    logger.configure(dict(RULE2TEST_LOG_LEVEL="info",RULE2TEST_LOG_FILE=str(directory/"demo-run.log")))
    frames=[]
    with tempfile.TemporaryDirectory(prefix="rule2test-capture-") as temporary:
        app=Application(Path(temporary)/"workspace.db")
        server=WorkspaceServer(("127.0.0.1",0),app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as engine:
                browser=engine.chromium.launch()
                page=browser.new_page(viewport={"width":width,"height":height},device_scale_factor=1)
                def shot(title,caption,note=""):
                    name=f"{len(frames)+1:02d}-{title.lower().replace(' ','-')}.png"
                    page.screenshot(path=str(directory/name),full_page=True)
                    frames.append(dict(file=name,title=title,caption=caption,note=note))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                expect(page.locator("#notice")).to_contain_text("Workspace ready")
                page.locator("#actor").fill(REVIEWER)
                shot("Overview","An insurer changes one rule. Today nobody can prove which regression tests that invalidated. We turn a rule change into reviewed tests and an audit trail.")

                from scripts.suite_browser_flow import prepare_comparison
                prepare_comparison(page,shot)

                page.locator("#select-all").check()
                page.locator("#review-reason").fill(REASON)
                page.get_by_role("button",name="Approve selected",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("explicit review decisions saved")
                shot("Human review","Nothing is approved automatically. Each decision is bound to a test revision and a person. Change a test afterwards and its approval is void.")

                page.get_by_role("button",name="Finalize review",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Review finalized")
                page.locator('nav [data-page="evidence"]').click()
                page.get_by_role("button",name="Execute approved tests",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Execution completed")
                shot("Clean run","Expected comes from our typed oracle. Actual comes from an independently configured system under test. They never share code, and the SUT never sees the expected value.")

                page.get_by_role("button",name="Create evidence pack",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Evidence archived")
                shot("Evidence","The evidence pack binds rules, approvals, inputs, expected, actual and the reviewer, under one SHA-256 fingerprint.",
                     "SHA-256 detects corruption. It is not a signature and does not stop an administrator who rewrites both payload and hash.")

                page.get_by_role("button",name="Evaluate current revision",exact=True).click()
                expect(page.locator("#gate-detail strong")).to_have_text("GO")
                shot("Gate GO","The regression gate reads GO for this revision: execution succeeded, obligations resolved, and every source and evidence link verified.")

                page.locator("#control-reason").fill("Reopen to demonstrate the injected boundary fault")
                page.get_by_role("button",name="Reopen review",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Workflow transition recorded")
                page.locator('nav [data-page="tests"]').click()
                page.locator("#select-all").check()
                page.locator("#review-reason").fill(REASON)
                page.get_by_role("button",name="Approve selected",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("explicit review decisions saved")
                page.get_by_role("button",name="Finalize review",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Review finalized")
                page.locator('nav [data-page="evidence"]').click()
                page.locator("#sut-fault").select_option("boundary")
                page.get_by_role("button",name="Execute approved tests",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Execution completed")
                shot("Injected bug","Now the off-by-one at the exact threshold. The suite catches it and the counterexample is a concrete age, not a stack trace.")

                page.get_by_role("button",name="Create evidence pack",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Evidence archived")
                page.get_by_role("button",name="Evaluate current revision",exact=True).click()
                expect(page.locator("#gate-detail strong")).to_have_text("NO-GO")
                shot("Gate NO-GO","A passing suite alone was never the point. The gate flips to NO-GO and names the failing check.")

                page.locator('nav [data-page="overview"]').click()
                page.get_by_role("button",name="Inspect this run",exact=True).click()
                expect(page.locator("#diagnostics-detail")).to_contain_text("Counters")
                shot("Diagnostics","Every request carries a trace id, provider failures are classified with a remediation hint, and we never retry or silently fall back to mock.",
                     "Counters are process-local and reset on restart. They never contain document text, prompts, reviewer names or session tokens.")
                browser.close()
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)
    return frames

def main(argv=None):
    parser=argparse.ArgumentParser(description="Capture the demo story as screenshots and an offline replay page.")
    parser.add_argument("--output",type=Path,default=OUTPUT)
    parser.add_argument("--width",type=int,default=1440)
    parser.add_argument("--height",type=int,default=1050)
    args=parser.parse_args(argv)
    args.output=args.output.resolve()
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("Playwright is not installed. Run:\n  py -3 -m pip install --user -r requirements-browser.txt\n"
              "  py -3 -m playwright install chromium",file=sys.stderr)
        return 2
    try:
        args.output.mkdir(parents=True,exist_ok=True)
        frames=capture(args.output,width=args.width,height=args.height)
        replay=build_replay(frames,args.output)
        print(json.dumps(dict(frames=len(frames),directory=str(args.output.relative_to(ROOT)),
            replay=str(replay.relative_to(ROOT)),log=str((args.output/"demo-run.log").relative_to(ROOT)),
            database="temporary; data/workspace.db untouched",
            video="not produced; screen-record the replay page if a video file is required"),ensure_ascii=False,indent=2))
        return 0
    except Exception as exc:
        print("Capture failed: "+type(exc).__name__+": "+str(exc)[:400],file=sys.stderr)
        return 1
if __name__=="__main__":raise SystemExit(main())
