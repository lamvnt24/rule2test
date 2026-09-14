"""The workspace must show a reviewer sentences, not the typed JSON contracts behind them.

Skipped when Playwright is absent; the rendering is browser behaviour and cannot be asserted
meaningfully without one.
"""
import tempfile,threading,unittest
from pathlib import Path
from factory.api.dependencies import Application
from factory.server import WorkspaceServer

try:
    from playwright.sync_api import sync_playwright,expect
    BROWSER=True
except ImportError:
    BROWSER=False

REASON="Inspected the boundaries and the expected outcomes"

@unittest.skipUnless(BROWSER,"Playwright is not installed")
class WorkspaceRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="rule2test-render-")
        cls.app=Application(Path(cls.temp.name)/"render.db")
        cls.server=WorkspaceServer(("127.0.0.1",0),cls.app)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.playwright=sync_playwright().start()
        cls.browser=cls.playwright.chromium.launch()
        cls.page=cls.browser.new_page(viewport={"width":1440,"height":1000})
        cls.errors=[]
        cls.page.on("pageerror",lambda exc:cls.errors.append(str(exc)))
        cls.page.on("console",lambda message:cls.errors.append(message.text) if message.type=="error" else None)
        cls.page.goto(f"http://127.0.0.1:{cls.server.server_port}")
        expect(cls.page.locator("#notice")).to_contain_text("Workspace ready")
        cls.page.locator("#actor").fill("Rendering QA")
        cls.page.locator('nav [data-page="intake"]').click()
        cls.page.get_by_role("button",name="Create synthetic workflow",exact=True).click()
        expect(cls.page.locator("#notice")).to_contain_text("Draft created")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.playwright.stop()
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=5)
        cls.temp.cleanup()

    def advance(self,label,expected):
        self.page.get_by_role("button",name=label,exact=True).click()
        expect(self.page.locator("#notice")).to_contain_text(expected)

    def test_01_one_button_analyses_and_opens_review(self):
        # The two mechanical transitions used to be two separate clicks.
        expect(self.page.locator("#flow .step.now")).to_have_text("1 Rule versions")
        self.advance("Analyze & open review","review opened")
        expect(self.page.locator("#flow .step.now")).to_have_text("3 Your review")

    def test_02_candidate_inputs_and_outcomes_read_as_sentences(self):
        row=self.page.locator("#test-rows tr").first
        self.assertRegex(row.inner_text(),r"Age = \d+","inputs must read as a sentence")
        self.assertIn("ALLOW",self.page.locator("#test-rows").inner_text())
        body=self.page.locator("#test-rows").inner_text()
        for fragment in ('"kind"','"integer"','"outcome"','"currency"'):
            self.assertNotIn(fragment,body,"the candidate table must not print raw JSON")

    def test_03_rules_read_as_a_sentence_with_their_source_quote(self):
        rules=self.page.locator("#rule-detail").inner_text()
        self.assertIn("If Age ≥ 18",rules)
        self.assertIn("→ ALLOW",rules)
        self.assertIn("Age from 18 through 65",rules,"the source quote grounds the rule")

    def test_04_analysis_explains_the_change_in_words(self):
        # The headings are uppercased by CSS, so compare case-insensitively.
        analysis=self.page.locator("#rule-detail").inner_text().lower()
        for heading in ("what changed in the rules","existing tests this affects","cases nobody covers yet"):
            self.assertIn(heading,analysis)
        self.assertIn("changed\teligibility",analysis,"the delta row names the change and the rule")
        self.assertIn("age = 66",analysis,"an uncovered boundary is shown as the input that would cover it")
        self.assertNotIn('"kind"',analysis,"the analysis panel must not print raw JSON above the disclosure")

    def test_05_raw_json_stays_available_for_audit(self):
        # Readability must not remove the artefact an auditor needs.
        self.assertGreaterEqual(self.page.locator('#rule-detail details >> text="Raw JSON"').count(),1)

    def test_06_review_and_execution_read_as_sentences(self):
        self.page.locator("#select-all").check()
        self.page.locator("#review-reason").fill(REASON)
        self.advance("Approve selected","review decisions saved")
        self.advance("Finalize review","Review finalized")
        expect(self.page.locator("#flow .step.now")).to_have_text("4 Execution")
        self.advance("Run the approved tests","Execution completed")
        self.page.locator('nav [data-page="evidence"]').click()
        # The results table must read plainly; the full journal stays raw underneath for audit.
        results=self.page.locator("#run-detail table").inner_text()
        self.assertIn("ALLOW",results)
        self.assertNotIn('"outcome"',results,"the results table must not print raw JSON")
        # The disclosure is collapsed, so assert on the DOM rather than the rendered text.
        self.assertIn('"outcome"',self.page.locator("#run-detail details").inner_html(),
                      "the raw execution journal must remain available for audit")

    def test_07_one_button_creates_evidence_and_evaluates_the_gate(self):
        self.advance("Create evidence & evaluate","GO")
        checks=self.page.locator("#gate-detail table").inner_text()
        self.assertIn("Execution results",checks,"check names are humanised")
        self.assertIn("pass: 14",checks,"observed values read as a sentence")
        self.assertNotIn('"status":',checks,"observed values must not print raw JSON")
        expect(self.page.locator("#flow .step.now")).to_have_text("5 Evidence & gate")

    def test_08_no_console_or_page_errors_occurred(self):
        self.assertEqual(self.errors,[])

if __name__=="__main__":unittest.main()
