"""Optional real-browser smoke check. Uses an isolated temporary database."""
import json,tempfile,threading,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.api.dependencies import Application
from factory.server import WorkspaceServer
from playwright.sync_api import sync_playwright,expect

def main():
    root=Path(__file__).resolve().parents[1]
    output=root/"data"/"generated";output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rule2test-browser-") as temporary:
        app=Application(Path(temporary)/"workspace.db")
        server=WorkspaceServer(("127.0.0.1",0),app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        errors=[]
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch()
                page=browser.new_page(viewport={"width":1440,"height":1050},device_scale_factor=1)
                page.on("pageerror",lambda error:errors.append(str(error)))
                page.on("console",lambda message:errors.append(message.text) if message.type=="error" else None)
                page.goto(f"http://127.0.0.1:{server.server_port}")
                expect(page.locator("#notice")).to_contain_text("Workspace ready")
                page.get_by_role("button",name="Inspect AI configuration",exact=True).click()
                expect(page.locator("#dialog-title")).to_have_text("AI configuration & local model inventory")
                page.get_by_role("button",name="Close dialog",exact=True).click()
                page.locator("#actor").fill("Browser QA")
                page.get_by_role("button",name="Start a workflow").click()
                page.get_by_role("button",name="Create synthetic workflow",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Draft created")
                page.get_by_role("button",name="Analyze & generate",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Analysis complete")
                page.get_by_role("button",name="Open test review",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Test review opened")
                count=page.locator('[name="test-selection"]').count();assert count>0
                assert page.locator('[name="test-selection"]:checked').count()==0
                page.locator("#select-all").check()
                page.locator("#review-reason").fill("Inspected synthetic boundaries, source revisions and expected results")
                page.get_by_role("button",name="Approve selected",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("explicit review decisions saved")
                page.get_by_role("button",name="Finalize review",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Review finalized")
                page.locator('nav [data-page="evidence"]').click()
                page.get_by_role("button",name="Execute approved tests",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Execution completed")
                assert page.locator("#run-detail .badge.pass").count()==count
                page.get_by_role("button",name="Create evidence pack",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Evidence archived")
                with page.expect_download() as download:
                    page.get_by_role("link",name="Download verified evidence JSON").click()
                evidence=json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
                assert len(evidence["executions"])==count
                page.get_by_role("button",name="Evaluate current revision",exact=True).click()
                expect(page.locator("#gate-detail strong")).to_have_text("GO")
                with page.expect_download() as gate_download:
                    page.get_by_role("button",name="Download this gate report",exact=True).click()
                gate=json.loads(Path(gate_download.value.path()).read_text(encoding="utf-8"))
                assert gate["verdict"]=="GO" and gate["evidence_id"]==evidence["evidence_id"]
                workflow=page.locator("#workflow-select").input_value()
                page.reload();expect(page.locator("#notice")).to_contain_text("Workspace ready")
                page.locator("#workflow-select").select_option(workflow)
                expect(page.locator("#context-state")).to_contain_text("evidenced")
                page.locator('nav [data-page="overview"]').click()
                page.screenshot(path=str(output/"phase8-desktop.png"),full_page=True)
                page.set_viewport_size({"width":390,"height":844})
                page.screenshot(path=str(output/"phase8-mobile.png"),full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                # Untrusted reviewer text is displayed as literal content inside the audit dialog.
                page.set_viewport_size({"width":1440,"height":1050})
                page.locator("#actor").fill('<img src=x onerror="window.injected=true">')
                page.locator('nav [data-page="evidence"]').click()
                page.locator("#control-reason").fill("Reopen for browser XSS rendering check")
                page.get_by_role("button",name="Reopen review",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Workflow transition recorded")
                page.locator('#page-evidence [data-action="history"]').click()
                expect(page.locator("#detail-dialog")).to_be_visible()
                assert page.locator("#detail-dialog img").count()==0
                assert page.evaluate("window.injected === undefined")
                page.get_by_role("button",name="Close dialog",exact=True).click()
                page.locator("#workflow-select").select_option("")
                expect(page.locator("#context-state")).to_have_text("No workflow selected")
                assert page.locator("#test-rows tr").count()==0
                page.locator('nav [data-page="extraction"]').click()
                page.get_by_role("button",name="Load sample text",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Synthetic source pair loaded")
                page.get_by_role("button",name="Extract rule proposal",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Proposal stored: pending_review")
                page.locator("#proposal-reason").fill("Inspected synthetic source lines and typed extraction")
                page.get_by_role("button",name="Approve proposal",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Rule review decision recorded")
                page.get_by_role("button",name="Promote approved proposal",exact=True).click()
                expect(page.locator("#notice")).to_contain_text("Approved proposal promoted")
                expect(page.locator("#context-state")).to_contain_text("draft")
                assert not errors,errors
                browser.close()
                print(json.dumps(dict(status="passed",browser="Chromium",tests_executed=count,
                    checks=["manual approvals","expected/actual results","evidence download","reload persistence","desktop/mobile","escaped audit content","empty selection","extraction review and promotion","quality gate and report download"],
                    screenshots=["data/generated/phase8-desktop.png","data/generated/phase8-mobile.png"])))
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)
if __name__=="__main__":main()


