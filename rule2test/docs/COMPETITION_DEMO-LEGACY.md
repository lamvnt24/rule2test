# Tài liệu lưu trữ — giao diện trước luồng testcase độc lập

# Competition demo script

Two timed variants of the same story, with the exact command, the exact click, what to say, and a recovery path
for every step that can fail. Rehearse the 5-minute version; keep the 10-minute version for a longer slot or Q&A.

**The one sentence to land:** *a rule changed, and we can prove which tests that invalidated, who approved the new
ones, what the system actually did, and whether it is safe to ship — with the AI never deciding pass or fail.*

## Before you start — 3 minutes, off the clock

```powershell
py -3 -B scripts/run_demo.py --check
py -3 -B scripts/collect_benchmarks.py --force --skip-tests
py -3 -B scripts/run_demo.py --seed --reset-database
```

1. Every preflight row must read `PASS` or `SKIP`. A `FAIL` row exits with code 2 and names the cause.
2. Open http://127.0.0.1:8000, type a reviewer name in the header, and leave the browser on **Overview**.
3. Open a second tab on http://127.0.0.1:8000/api/v1/diagnostics — you will show it at the end.
4. Keep `docs/BENCHMARKS.md` open in a third tab for questions.
5. Set the terminal font large enough to read from the back of the room.

> Only run `--reset-database` when you intend to discard the workspace database. It refuses any path outside
> `data/` and is never implied by another flag.

## 5-minute version

| Time | Do | Say |
| --- | --- | --- |
| 0:00–0:30 | Stay on **Overview**. Point at the four pipeline cards. | "An insurer changes one rule. Today nobody can prove which regression tests that invalidated. We turn a rule change into reviewed tests and an audit trail." |
| 0:30–1:10 | **Document intake → Scenario: Eligibility · age 60 → 65 → Create synthetic workflow**. | "Two versions of one rule go in. The source bytes are archived and hashed, so every later claim points back to a document you can download." |
| 1:10–2:10 | On **Test workspace** press **Analyze & generate**. Expand *Rule delta, impact, gaps & baseline coverage*. Point at boundary coverage. | "The engine computes the delta, finds the tests the change touches, and lists the boundary obligations nobody covers. Baseline boundary coverage on this scenario was 16.67%." |
| 2:10–3:00 | **Open test review**, tick the age-65 and age-66 rows, type a reason, **Approve selected**, then **Finalize review**. | "Nothing is approved automatically. Each decision is bound to a test revision and a person. Change a test afterwards and its approval is void." |
| 3:00–3:50 | **Run & evidence** → leave fault **None** → **Execute approved tests** → **Create evidence pack**. Download the evidence JSON. | "Expected comes from our typed oracle. Actual comes from an independently configured system under test. They never share code, and the SUT never sees the expected value." |
| 3:50–4:30 | **Evaluate current revision** under the quality gate — it reads GO. Then **Reopen review** with a reason, re-approve, re-finalize, set fault to **Boundary**, execute again, evaluate again — it reads **NO-GO** with the failing age test. | "This is the moment that matters. We inject an off-by-one at the exact threshold. The suite catches it, the gate flips to NO-GO, and the counterexample is a concrete age, not a stack trace." |
| 4:30–5:00 | Switch to the diagnostics tab. | "Every request carries a trace id, provider failures are classified with a remediation hint, and we never retry or silently fall back to mock. Numbers are in BENCHMARKS.md with the artifact each one came from." |

## 10-minute version

Run the 5-minute script through 3:50, then insert the following before the closing diagnostics beat.

| Time | Do | Say |
| --- | --- | --- |
| +0:00–1:30 | **AI rule review** → load the Japanese sample pair → **Extract rule proposal**. Expand the citations. | "The model reads two Japanese policy versions and returns structured rules. Every row must carry an exact source line — if the quote is not literally in the document, we reject the output. No prose repair, no retry." |
| +1:30–2:30 | Press **Approve proposal**, then **Promote approved proposal**. | "A person approved that proposal against its content hash. Only then does it become a workflow. The AI never promotes its own output." |
| +2:30–3:30 | **Knowledge & reuse** → build an index → query `age eligibility 加入年齢` → **Propose tests for active workflow** → inspect the batch → **Attach batch for review**. | "Retrieval reuses tests a human already approved elsewhere. The model proposes inputs only; our oracle recomputes every expected value against the current rules, and the batch arrives as pending review." |
| +3:30–4:00 | **Overview → Inspect AI configuration**. | "Providers are explicit. Mock is offline replay and is labelled simulated. Live models are digest-pinned. There is no automatic fallback between them." |

## Recovery paths

| If this fails | Do this on stage | What to say |
| --- | --- | --- |
| Preflight reports the port is busy | `py -3 -B scripts/run_demo.py --seed --port 8010` | "The launcher refuses to share a port instead of half-starting." |
| The workspace will not start | `py -3 -B scripts/run_demo.py --check --json` and read the failing row | "The preflight names the cause; nothing was installed or deleted." |
| A button is disabled | Check the status badge next to the workflow title | "Actions are gated by state. This one needs the previous step first." |
| A `409` conflict appears | Press **Refresh list**, reopen the workflow, repeat the action | "Two edits raced. We refuse the stale one instead of overwriting work." |
| Live AI is unreachable | Continue with the mock provider; skip the 10-minute AI block | "Offline replay, explicitly labelled simulated. The pipeline does not change." |
| A provider error banner appears | Read the classification and remediation on screen | "The failure is classified — unreachable, timeout, model mismatch — with a fix. We do not retry and we do not fall back to mock." |
| The browser is unusable | Fall back to the CLI: `py -3 -B scripts/run_analysis_demo.py` | "Same services, no UI." |
| Everything is unusable | Open `docs/slides/index.html` and the screenshot replay | See [backup capture](#backup-capture) below. |

## Backup capture

Video is not recorded by this repository and no video file is included. The rehearsed fallback is a deterministic
screenshot sequence plus an offline replay page:

```powershell
py -3 -m pip install --user -r requirements-browser.txt
py -3 -m playwright install chromium
py -3 -B scripts/capture_demo_screens.py
```

This writes numbered PNGs and a self-contained `replay.html` under `data/generated/demo-capture/`, using a
temporary database. It does not touch `data/workspace.db`. Open `replay.html` from disk and step through it with
the arrow keys; each frame carries the caption you would have spoken.

If you also want a video file, screen-record yourself stepping through `replay.html` with the captions visible —
that keeps the narration and the timings identical to the live run.

## Questions you should expect

| Question | Answer |
| --- | --- |
| "Does the AI decide whether a test passes?" | No. The typed oracle computes expected, an independent SUT computes actual, and a person approves the tests. See [DIAGRAMS.md](DIAGRAMS.md) diagram 1. |
| "How good is the extraction really?" | On ten authored Japanese cases, the live cloud model matched 4/10 with prompt v2 and 2/10 with v1. That is an honest limitation, not a headline. See [BENCHMARKS.md](BENCHMARKS.md). |
| "Is coverage a pass rate?" | No. Designed and executed coverage are shown separately, and failing tests still exercise inputs. |
| "Is GO a release approval?" | No. It is a local regression assessment for one workflow revision. Reopening review invalidates it. |
| "What happens when the model is down?" | The call fails with a classified error and a remediation hint. Nothing is retried, repaired or replaced by mock output. |
| "Can someone tamper with the evidence?" | SHA-256 detects accidental corruption. It is not a signature and does not stop an administrator who rewrites both the payload and the hash. |
| "What is not measured?" | Reviewer acceptance, effort savings, production accuracy, token cost and SME-reviewed labels. All listed in BENCHMARKS.md. |

## Do not say

- Any accuracy or time-saving number that is not in [BENCHMARKS.md](BENCHMARKS.md).
- "Production ready", "certified", or "signed evidence".
- That mock results demonstrate AI capability — mock extraction only replays exact fixtures.
