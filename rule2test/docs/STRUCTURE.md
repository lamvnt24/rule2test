# Project structure and implementation status

## Implemented

| Directory or module | Responsibility |
| --- | --- |
| factory/models | Immutable rule, table, test, approval, execution, evidence and analysis contracts |
| factory/engines | Oracle and evaluation traces, independent insurance mock, approved test execution |
| factory/validators | Supported DSL, test/approval provenance and UTF-8 source validation |
| factory/providers/sut | Mock and HTTP adapters |
| factory/services/rule_delta_service.py | Semantic rule changes |
| factory/services/impact_service.py | Dependency and behavioral impact |
| factory/services/gap_service.py | Bounded witness search and uncovered obligations |
| factory/services/generation_service.py | Candidate tests and revision proposals |
| factory/services/coverage_service.py | Designed-input and executed-input coverage |
| factory/services/mutation_service.py | Specification mutants and test witnesses |
| factory/config.py and exceptions.py | Configuration and shared error types |
| factory/core.py and server.py | Compatible legacy web workflow and SQLite persistence |
| web/index.html | English-language legacy dashboard |
| tests/unit | Domain, engine and service tests |
| tests/integration | HTTP adapter and full analysis-to-evidence tests |
| tests/evaluation | Independent synthetic seeded-gap truth sets |
| tests/fixtures | Shared synthetic business examples |

The live Ollama extraction adapter remains in factory/server.py. Phase 6 implements a typed mock/Ollama LLM provider package. Cloud LLM, embedding and vector integrations remain scaffolds.

## Entry points

- python -B -m factory.server: legacy web demo.
- python -B scripts/run_engine_demo.py: phase-2 business scenarios.
- python -B scripts/run_analysis_demo.py: phase-3 analysis through typed evidence.
- python -B -m unittest discover -s tests -v: all tests.

Run from the project directory. Model files are importable modules, not executable applications.

## Remaining scaffolds

Workflow, approval and evidence services plus SQLite repositories are implemented in phase 4. Phase 5 implements JSON/XLSX parsers and source archives. Phase 6 implements extraction orchestration and rule review. Observability infrastructure, API routes/schemas and Streamlit remain reserved for subsequent phases.
seed_demo.py creates missing synthetic imports; reset_demo.py restores only the six known fixture files.

## Data

- data/demo.json: active legacy web fixture.
- data/demo: versioned eligibility, claim-review and deductible JSON/XLSX imports.
- data/generated: optional CLI output.
- data/vector_index: reserved for a future index.

## Dependency direction

API/UI -> services -> models and provider/repository contracts.
Engines do not import the UI or HTTP routes. The SUT never receives expected results or rule snapshots from the executor.

See [domain models](DOMAIN_MODELS.md), [engines](ENGINES.md) and [analysis services](ANALYSIS_SERVICES.md).

## Phase 4 entry points
- scripts/run_workflow_demo.py: persistent synthetic review demo.
- scripts/workflow_cli.py: explicit review, edit, finalize, execute, recovery and evidence commands.
- factory/models/workflow.py: immutable workflow snapshots and execution journal contracts.
- factory/repositories/: SQLite transactions, migrations, scoped snapshot storage and audit history.
See [WORKFLOWS.md](WORKFLOWS.md).

## Phase 5 entry points

- scripts/import_documents.py: validate, create and recover archived source documents.
- scripts/run_import_demo.py: import through pending human review.
- factory/parsers/: structured JSON/XLSX schema, shared builder and templates.
- factory/services/import_service.py: validated import and atomic source archive.
See [IMPORT_FORMAT.md](IMPORT_FORMAT.md).

## Phase 6 entry points

- scripts/run_extraction_demo.py: synthetic proposal awaiting rule review.
- scripts/extraction_cli.py: extract, inspect, explicitly review and promote.
- scripts/evaluate_extraction.py: separate synthetic truth checks with simulation labels.
- factory/services/extraction_service.py: durable proposal, review and atomic promotion.
- factory/providers/llm/: provider protocol, mock replay, optional Ollama and versioned prompt.
- data/ai_samples/: Japanese source pairs, existing tests and separate truth.

See [AI_EXTRACTION.md](AI_EXTRACTION.md).
