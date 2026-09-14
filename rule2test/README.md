# Rule2Test — Insurance Rule2Test Evidence Factory

A runnable Python 3.11+ hackathon project that turns insurance rule changes into reviewed regression tests and traceable execution evidence. The core, JSON import and web workspace use the standard library. Excel import and FAISS are optional.

## Portable executable

```powershell
py -3 -m PyInstaller packaging/rule2test.spec --noconfirm --clean
.\dist\rule2test.exe
```

One self-contained Windows file, about 12 MB: bundled CPython, the whole `factory` package, the browser
workspace and the demo fixtures. Copy it to another Windows machine and run it — no Python, no install, no
download at startup. Databases are written beside the executable, never into the temporary extraction
directory, so workflows and evidence survive restarts and travel with the file.

`rule2test.exe check` runs the preflight alone; `rule2test.exe doctor` inspects the local model inventory.
Windows x64 only, unsigned. See [packaging guide](docs/PACKAGING.md).

## Demo and test kit

```powershell
py -3 -B scripts/build_demo_kit.py --force
```

Builds `demo-kit/`: the portable executable, the timed demo script, benchmarks, diagrams, the pitch deck,
import fixtures, the Japanese rule-document pairs with their separate truth files, AI profile templates, the
offline screenshot replay, a SHA-256 manifest, and an `EXPECTED-RESULTS.md` whose every number is produced by
executing the real services while the kit is assembled. Copy the folder to another Windows machine and run
`app/rule2test.exe`. `make kit` rebuilds it; the folder is not tracked in git.

## Run the workspace

Open PowerShell in the project directory:

```powershell
Set-Location -LiteralPath "<path to this repository>"
py -3 -B scripts/run_demo.py --seed
```

`run_demo.py` runs an explicit preflight (Python version, free port, writable database directory, optional dependencies, fixtures) and then starts the workspace. Use `--check` for the preflight alone, `--reset-database` to discard the selected database, and `--profile` to start with a digest-pinned live AI profile. `py -3 -B -m factory.server` still works and skips the preflight.

Open http://127.0.0.1:8000. Enter your reviewer identity, then use **Document intake → Create synthetic workflow**. The default database is **data/workspace.db**; workflow reviews and evidence survive restarts.

To inspect an existing typed CLI database:

```powershell
py -3 -B scripts/run_demo.py --db data/retrieval-demo.db --port 8001
```

The original threshold demo remains at **/legacy**, with its separate data/factory.db. The new workspace uses the typed services from phases 1–7. Streamlit and FastAPI are not required.

See [workspace guide](docs/WORKSPACE.md) and [demo flow](docs/DEMO_FLOW.md).

## What is implemented

| Phase | Capability |
| --- | --- |
| 1 | Immutable domain contracts, strict typed values, versioned rules and content hashes |
| 2 | Typed oracle, independent insurance mock, approved executor and HTTP SUT adapter |
| 3 | Rule delta, dependency/behavior impact, bounded gap search, generation, coverage and mutation |
| 4 | SQLite snapshots, revision checks, explicit review, execution journals and evidence |
| 5 | Structured JSON/XLSX import, source citations and original-byte archives |
| 6 | Mock/Ollama text extraction, exact-line validation, immutable proposals and explicit rule review |
| 7 | Reviewed knowledge corpus, mock/Ollama embeddings, Python/FAISS retrieval and grounded suggestions |
| 8 | Unified browser workspace, versioned REST API, atomic selected-test review, downloads and audit inspection |
| 9 | Versioned regression quality gate, revision-bound reports and synthetic gate benchmark |
| 10 | Digest-pinned local AI profiles, readiness probes and three-role evaluation tooling; Cloud Free connection verified on synthetic data |
| 11 | Structured logging, request tracing, bounded metrics, classified provider failures and a preflighted demo launcher |
| 12 | Aggregated benchmark artifacts, architecture diagrams, a timed demo script, a generated pitch deck and an offline screenshot replay |

The AI providers propose rules or test inputs. The typed oracle computes expected results; an independent SUT computes actual results. AI never decides PASS/FAIL or approves its own output.

## Five-minute demo

1. Create the synthetic eligibility workflow: maximum eligible age changes from 60 to 65.
2. Analyze and inspect rule delta, affected tests, gaps and designed coverage.
3. Open test review. Inspect inputs and expected outcomes, explicitly select tests and record your decisions with a reason.
4. Finalize review. Under **Run & evidence**, execute the eligibility mock with no fault.
5. Create and download the evidence pack. Original source bytes are also downloadable.
6. Reopen review with a reason, review and finalize again, then run with the boundary fault. Inspect the failing age-boundary test.

Designed coverage and executed coverage are shown separately. Failing tests still exercise inputs; coverage is not a pass rate or release approval. Synthetic results are not production measurements.

## Optional Excel and AI

```powershell
python -m pip install --user -r requirements-excel.txt
python -B scripts/seed_demo.py
```

Import the versioned templates in data/demo. See [import format](docs/IMPORT_FORMAT.md).

The default AI providers are offline mock replays, explicitly labeled simulated. To use an already installed local Ollama model, set process environment variables before starting the server:

```powershell
$env:RULE2TEST_EXTRACTION_PROVIDER="ollama"
$env:RULE2TEST_EXTRACTION_MODEL="your-installed-model"
```

Set embedding and suggestion providers separately as described in [retrieval guide](docs/RETRIEVAL.md). The workspace reads RULE2TEST_VECTOR_BACKEND=python or faiss. Install requirements-retrieval.txt before selecting faiss. Changing embedding identity requires a matching index.

The .env.example file is a template; it is not loaded automatically. Live-model quality has not been benchmarked. Exact source citations do not establish semantic correctness; human rule review remains required.

## Tests and CLI entry points

```powershell
python -B -m unittest discover -s tests -v
python -B scripts/run_engine_demo.py
python -B scripts/run_analysis_demo.py
python -B scripts/run_workflow_demo.py
python -B scripts/run_import_demo.py
python -B scripts/run_extraction_demo.py
python -B scripts/run_retrieval_demo.py
```

Some CLI demos deliberately seed approvals labeled as synthetic fixtures. The browser does not automatically approve rules or tests.

Optional real-browser verification:

```powershell
python -m pip install --user -r requirements-browser.txt
python -m playwright install chromium
python -B scripts/check_workspace_browser.py
```

This check uses a temporary database and writes desktop/mobile screenshots under data/generated. It does not modify existing workflow databases.

Files under factory/models are importable package modules, not standalone entry points. Run commands from the project directory.

## Controls and scope

- Every mutation uses persisted workflow revisions; stale actions fail instead of silently overwriting work.
- Selected-test review validates the entire selection before committing any decision.
- Execution receives SUT configuration; clients cannot supply execution expectations or rules.
- Source and evidence downloads verify stored content integrity.
- The server binds to loopback and checks Host/Origin, JSON limits and a session token on versioned POST routes.
- Reviewer names are self-declared. Authentication, RBAC, a background queue and deployment hardening are future work.
- SHA-256 is an integrity check, not a digital signature or protection from an administrator rewriting both data and hashes.
- The workspace exposes the independent mock SUT. The HTTP SUT adapter remains available through Python.

Tiếng Việt: [tổng quan và lộ trình](docs/vi/TONG-QUAN-VA-ROADMAP.md), [hướng dẫn sử dụng](docs/vi/HUONG-DAN-SU-DUNG.md).

See [packaging](docs/PACKAGING.md), [benchmarks](docs/BENCHMARKS.md), [diagrams](docs/DIAGRAMS.md), [observability](docs/OBSERVABILITY.md), [competition demo](docs/COMPETITION_DEMO.md), [API](docs/API.md), [architecture](docs/ARCHITECTURE.md), [project structure](docs/STRUCTURE.md), [domain models](docs/DOMAIN_MODELS.md), [engines](docs/ENGINES.md), [analysis](docs/ANALYSIS_SERVICES.md), [workflows](docs/WORKFLOWS.md), [AI extraction](docs/AI_EXTRACTION.md) and [pitch](docs/PITCH.md).

## Next development

Evaluate real extraction/embedding models against a broader labeled corpus; add richer decision-table analysis and metamorphic tests; integrate a real SUT; introduce authenticated roles, signed evidence and operational monitoring. FastAPI, PostgreSQL and background jobs can replace transport/storage boundaries when needed.


## Phase 9: regression quality gate

After creating evidence, use **Run & evidence → Evaluate current revision**. Inspect GO/NO-GO checks and download the report. The gate requires execution success, coverage, candidate acceptance, resolved obligations and verified source/evidence links. Reopening review invalidates the current GO context.

Run `python -B scripts/evaluate_quality_gate.py` for six synthetic expectations. The correct deductible fixture remains NO-GO because its default-branch obligation is unresolved. See [quality gate guide](docs/QUALITY_GATE.md) for exact thresholds, CLI exit codes and metric limits.


## Phase 10: live AI setup and evaluation

```powershell
python -B scripts/ai_doctor.py
python -B scripts/evaluate_ai.py --profile data/ai_profiles/mock.json
```

The evaluator separates exact replay, paraphrase, numeric-change, instruction and ambiguity cases. It measures extraction, hybrid retrieval and grounded suggestions without automatically approving evaluated proposals. Each run preserves its profile, dataset, report and database.

The initial environment had no Ollama service. A subsequent Cloud Free run verifies chat and CPU embeddings; current extraction matches 4/10 authored cases, so model quality remains limited. See [live AI guide](docs/LIVE_AI.md) to create an installed-model profile, probe it and run the real evaluation.


## Connected Cloud Free profile

    python -B scripts/run_ai_workspace.py --profile data/ai_profiles/ollama-cloud.local.json

Plain factory.server does not load this profile. See [LIVE_AI.md](docs/LIVE_AI.md) for the real synthetic evaluation and remaining extraction failures.


## Phase 11: diagnostics and demo packaging

```powershell
py -3 -B scripts/run_demo.py --check
$env:RULE2TEST_LOG_LEVEL="debug"; py -3 -B scripts/run_demo.py --seed
```

Every response carries `X-Trace-Id`, and every error body repeats it as `trace_id`. Logs are single-line JSON
restricted to an allowlist of fields, so document text, prompts, reviewer names and session tokens cannot reach a
log line. Provider failures are classified into eleven kinds with a remediation hint and are surfaced as HTTP 502
with `retried: false` and `fallback_used: false` — there is still no automatic retry, no fallback to mock and no
automatic approval.

Inspect a run at **Overview → Run diagnostics** or `GET /api/v1/diagnostics`. Metrics are process-local and reset
on restart. See [observability guide](docs/OBSERVABILITY.md).


## Phase 12: competition materials

```powershell
py -3 -B scripts/collect_benchmarks.py --force
py -3 -B scripts/capture_demo_screens.py
py -3 -B scripts/build_slides.py
```

`collect_benchmarks.py` copies every measured value out of the artifacts under data/generated into
[docs/BENCHMARKS.md](docs/BENCHMARKS.md); it computes nothing and invents nothing. `build_slides.py` reads that
summary, so [docs/slides/index.html](docs/slides/index.html) cannot quote a number the repository has not measured.

`capture_demo_screens.py` needs requirements-browser.txt and writes numbered screenshots, a captured JSON log and
a self-contained `replay.html` under data/generated/demo-capture, using a temporary database. **No video file is
produced** — screen-record the replay page if a video is required.

Run the presentation from [docs/COMPETITION_DEMO.md](docs/COMPETITION_DEMO.md), which gives 5 and 10 minute
scripts, a recovery path for every step that can fail, and the questions to expect.
