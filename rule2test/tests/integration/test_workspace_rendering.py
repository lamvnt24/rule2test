"""Real browser regression: standalone testcase intake through reviewed evidence."""
import tempfile,threading,unittest
from pathlib import Path
from factory.api.dependencies import Application
from factory.server import WorkspaceServer
try:
    from playwright.sync_api import sync_playwright,expect
    from scripts.suite_browser_flow import prepare_comparison
    BROWSER=True
except ImportError:BROWSER=False

@unittest.skipUnless(BROWSER,'Playwright is not installed')
class WorkspaceRenderingTests(unittest.TestCase):
    def test_suite_to_evidence_and_reload(self):
        with tempfile.TemporaryDirectory() as temp:
            app=Application(Path(temp)/'test.db');server=WorkspaceServer(('127.0.0.1',0),app)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as playwright:
                    browser=playwright.chromium.launch()
                    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{server.server_port}')
                    expect(page.locator('#notice')).to_contain_text('Workspace ready')
                    page.locator('#actor').fill('Browser QA')
                    prepare_comparison(page)
                    expect(page.locator('#not-linked')).to_contain_text('TC005')
                    expect(page.locator('#test-rows')).to_contain_text('E3')
                    expect(page.locator('#sut-max')).to_have_value('65')
                    self.assertEqual(page.locator('[name="test-selection"]:checked').count(),0)
                    page.locator('#select-all').check();page.locator('#review-reason').fill('Checked every proposed input and expected result')
                    page.get_by_role('button',name='Approve selected',exact=True).click()
                    expect(page.locator('#notice')).to_contain_text('review decisions saved')
                    page.get_by_role('button',name='Finalize review',exact=True).click()
                    expect(page.locator('#notice')).to_contain_text('Review finalized')
                    page.locator('nav [data-page="evidence"]').click()
                    page.get_by_role('button',name='Execute approved tests',exact=True).click()
                    expect(page.locator('#notice')).to_contain_text('Execution completed')
                    expect(page.locator('#run-detail')).to_contain_text('pass')
                    page.get_by_role('button',name='Create evidence pack',exact=True).click()
                    expect(page.locator('#notice')).to_contain_text('Evidence archived')
                    page.get_by_role('button',name='Evaluate current revision',exact=True).click()
                    expect(page.locator('#gate-detail strong')).to_have_text('GO')
                    with page.expect_download() as download:
                        page.get_by_role('link',name='Download verified evidence JSON').click()
                    self.assertIsNone(download.value.failure())
                    workflow=page.locator('#workflow-select').input_value()
                    page.reload();expect(page.locator('#notice')).to_contain_text('Workspace ready')
                    page.locator('#workflow-select').select_option(workflow)
                    expect(page.locator('#context-state')).to_contain_text('evidenced')
                    page.set_viewport_size({'width':390,'height':844})
                    page.locator('nav [data-page="tests"]').click()
                    expect(page.locator('#test-rows')).to_contain_text('DENY → ALLOW')
                    self.assertEqual(errors,[])
                    custom=browser.new_page()
                    custom.goto(f'http://127.0.0.1:{server.server_port}')
                    expect(custom.locator('#notice')).to_contain_text('Workspace ready')
                    custom.locator('#actor').fill('Custom rule reviewer')
                    prepare_comparison(custom,baseline=False,max_age=72)
                    expect(custom.locator('#change-overview')).to_contain_text('previous rule unknown')
                    expect(custom.locator('#rule-detail')).to_contain_text('Age ≤ 72')
                    expect(custom.locator('#sut-max')).to_have_value('72')
                    browser.close()
            finally:server.shutdown();server.server_close();thread.join(timeout=5)
