# Rule2Test — Insurance Rule2Test Evidence Factory

A runnable Python 3.11+ hackathon project. The core and JSON import use the standard library; XLSX import has optional dependencies. The demo uses synthetic insurance data and runs on localhost.

## Run the web demo

Open PowerShell and change to the project directory first:

```powershell
Set-Location -LiteralPath "E:\AI hackathon\rule2test"
python -B -m factory.server
```

Open http://127.0.0.1:8000.

## Run the engine demo and tests

From the same project directory:

```powershell
python -B scripts/run_engine_demo.py
python -B -m unittest discover -s tests -v
```

The engine demo produces three PASS results with correct mock implementations and three intentional FAIL results with injected bugs. The automated tests verify that those bugs are detected.

Files under factory/models are package modules, not standalone entry points. Do not run test_case.py or decision_table.py directly.

## Four-minute web demo

1. Load the fixture: maximum age changes from 60 to 65; the manual-review threshold changes from 100M to 150M VND.
2. Analyze: two rule changes and five related tests; only two tests actually change their expected outcome. Dependency impact and behavioral change are different.
3. Review the 14 gaps, select all candidates and enter the QA reviewer name. Run the correct mock: GO with 100% boundary coverage.
4. Run again with the comparator bug, >= instead of >: two threshold tests FAIL and the gate becomes NO-GO.
5. Inspect mutation witnesses and download the JSON evidence. Show the source quote, rule hash, reviewer, input hash and timestamp.

These metrics come from the synthetic fixture and execution results, not production measurements.

## Optional live AI extraction

Install and run Ollama with a locally available model, then set this environment variable before starting the server:

```powershell
$env:OLLAMA_MODEL="your-installed-model"
```

Expand local LLM extraction in the UI, paste a requirement and extract it into V2. The adapter calls the local API and validates the schema and exact source quote. Missing model configuration produces an explicit error; the structured JSON demo is not presented as AI inference.

A valid source quote does not prove that the threshold was interpreted correctly. QA must review the result before analysis. English, Vietnamese and Japanese extraction have not been benchmarked. Use synthetic documents for this demo.

## Architecture and implementation status

Browser -> HTTP API -> validated rules -> delta / impact -> boundary obligations -> QA selection -> independent mock SUT -> mutation testing -> SQLite evidence.

- Phase 1: immutable domain models, version-bound approval/evidence contracts, lossless JSON serialization, configuration and exceptions.
- Phase 2: typed oracle, independent insurance mock, approved test executor, validators and HTTP SUT adapter. Eligibility, claim thresholds and deductible calculations run through the Python API and CLI.
- The web UI still uses the original threshold workflow. Typed execution has not yet been connected to the UI.
- Phase 3: six deterministic analysis services, bounded gap search, candidate generation, coverage and specification mutation are implemented. Phase 4 adds SQLite repositories, versioned workflow/review services and persistent evidence. Phase 5 adds structured JSON/XLSX import, source-byte archives and synthetic templates. Phase 6 adds a mock/Ollama extraction provider boundary, exact-line validation and hash-bound rule review. Cloud providers, retrieval and Streamlit remain scaffolds.

See [project structure](docs/STRUCTURE.md), [domain contracts](docs/DOMAIN_MODELS.md) and [engine guide](docs/ENGINES.md).

## Original web-demo DSL

Rules contain id, field, threshold and source. Fields are age or claim_amount, with integer values. Values at or below the threshold produce ALLOW; higher values produce REVIEW; invalid types or out-of-domain values produce INVALID.

The age domain is 0..120; the money domain is 0..1 billion VND. This legacy workflow models maximum thresholds, not complete product eligibility, minimum-age rules or deductible payouts.

It supports threshold changes with stable IDs and fields. Added/deleted rules and field migrations are rejected explicitly. The separate phase-2 engine supports richer conditions and deductible calculations; see [ENGINES.md](docs/ENGINES.md).

## Evidence and controls

- The oracle computes expected results; the independent mock computes actual results.
- Two legacy mutants per rule simulate a comparator error and a reduced threshold. Mutation score measures detected mutants, not proof that every possible bug is covered.
- The server retrieves the saved plan and validates approved candidate IDs. The client does not submit execution rules or expected results.
- SQLite stores plans and evidence with the approval selection. Reviewer names are self-declared; authentication and RBAC are not implemented.
- SHA-256 checks content integrity. It is not a digital signature, immutable ledger or protection against an administrator rewriting data and hashes.
- The server binds to loopback, limits request size and rejects cross-origin browser POST requests.

## KPI definitions

- Rule coverage: rules with at least one test / total rules. This is not branch coverage.
- Boundary coverage: obligations with a matching test input / total obligations. Each legacy rule has seven: t-1, t, t+1, null, negative, overflow and wrong type. This measures exercised inputs; a failing test still counts as exercised.
- Reviewer acceptance: approved candidates / generated candidates; N/A when there are no candidates.
- Traceability: every result includes its source and rule hash.
- Seeded-gap recall: a unit benchmark uses 14 independently specified ground-truth obligations. Coverage is not labeled as recall.
- GO gate: boundary coverage >=90%, no FAIL results, and acceptance >=70% or N/A. This is a demo gate, not authorization to release an insurance product.

## API

See [API.md](docs/API.md). Import JSON follows [data/demo.json](data/demo.json).

## Next development stages

1. Extend typed text extraction to general document layouts and evaluate real-model performance.
2. Broader decision-table support and SMT/Z3 analysis for overlaps, unsatisfiable rules and witnesses.
3. Semantic retrieval with labeled evaluation, beyond rule-ID mapping.
4. Integration with a real SUT API and additional property/metamorphic tests.
5. Authenticated RBAC, signed evidence and stronger append-only storage.
6. A broader synthetic benchmark corpus with independent seeded gaps, latency/cost/acceptance metrics and a manual baseline.
7. FastAPI, PostgreSQL and a task queue when needed.

See [architecture](docs/ARCHITECTURE.md), [demo flow](docs/DEMO_FLOW.md) and [pitch](docs/PITCH.md).

## Phase 3: analysis services
Implemented deterministic delta, impact, gap, generation, coverage and specification-mutation services. Run python -B scripts/run_analysis_demo.py from the project directory. Use --output data/generated/analysis-demo.json to save a full report to a new file. See [analysis service guide](docs/ANALYSIS_SERVICES.md) for metric definitions and unresolved obligations. Approval decisions in the CLI are synthetic; services never approve candidates.

## Phase 4: persistent review workflows
Run python -B scripts/run_workflow_demo.py for a persistent synthetic demo. Use python -B scripts/workflow_cli.py --help for explicit review/edit/execute commands. Workflow snapshots, review decisions, execution journals and evidence survive process restarts. See [workflow guide](docs/WORKFLOWS.md). The new CLI does not change the legacy web workflow.

## Phase 5: JSON and Excel import

Import two rule versions and existing tests, retain cell/JSON Pointer citations, archive original source bytes and create a persistent DRAFT workflow.

```powershell
python -m pip install --user -r requirements-excel.txt
python -B scripts/seed_demo.py
python -B scripts/import_documents.py validate data/demo/eligibility.xlsx
python -B scripts/run_import_demo.py
```

The demo ends at IN_REVIEW without automatic approvals. Complete templates: [eligibility](data/demo/eligibility.xlsx), [claim review](data/demo/claim_review.xlsx), [deductible](data/demo/deductible.xlsx). JSON equivalents are in the same directory.

See [import format and commands](docs/IMPORT_FORMAT.md). This phase supports structured templates and explicit Japanese header mapping; phase 6 adds a separate UTF-8 text extraction path with mock/Ollama providers and rule review. Import currently uses the CLI, not the legacy web UI.

## Phase 6: AI extraction and rule review

```powershell
$env:RULE2TEST_EXTRACTION_PROVIDER="mock"
python -B scripts/run_extraction_demo.py
python -B scripts/evaluate_extraction.py
```

The default provider replays three exact Japanese synthetic source pairs and labels results simulated=true. Unknown sources require clarification. The demo stops before rule approval. An optional Ollama adapter is available; live model quality has not been evaluated.

Validated proposals are persisted with source lines, prompt metadata and hashes. Explicit rule review can promote a proposal into a DRAFT workflow; QA test review remains a separate gate. See [AI extraction guide](docs/AI_EXTRACTION.md) for inspection, approval, promotion and local-provider configuration. The current input is UTF-8 text, not free-layout Excel/PDF.
