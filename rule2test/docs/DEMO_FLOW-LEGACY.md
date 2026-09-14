# Tài liệu lưu trữ — giao diện trước luồng testcase độc lập

# Demo flow

1. Run `py -3 -B scripts/run_demo.py --seed` from the project root (preflight plus workspace). `py -3 -B -m factory.server` still works and skips the preflight.
2. Open http://127.0.0.1:8000 and enter a reviewer identity.
3. Under Document intake, create the synthetic eligibility workflow.
4. Analyze & generate; inspect rule versions, delta, impact, gaps and designed coverage.
5. Open test review. Inspect candidate inputs and expected results, explicitly select tests, enter a reason and approve the selection.
6. Finalize review. Under Run & evidence, execute the independent eligibility mock with no fault.
7. Create evidence, inspect executed coverage and download the evidence/source files.
8. Reopen review with a reason and repeat explicit approval/finalization before running the boundary fault. Inspect the FAIL result.

The default UI is web/workspace.html. The original threshold demo remains at /legacy. streamlit_app remains a scaffold. See [WORKSPACE.md](WORKSPACE.md) for the complete screen guide and database options.

For a timed competition run with speaker notes and recovery paths, use [COMPETITION_DEMO.md](COMPETITION_DEMO.md).

## Phase 3 CLI
Run python -B scripts/run_analysis_demo.py from the project directory for rule delta, related/changed tests, gap candidates, coverage, mutation and independent execution evidence. This CLI uses scripted synthetic approvals and does not alter the web workflow.

## Phase 4 persistence demo
Run python -B scripts/run_workflow_demo.py. The demo persists 14 test results and evidence, then reopens the database to verify the saved workflow. Use workflow_cli.py for explicit human review decisions; see [WORKFLOWS.md](WORKFLOWS.md).

## Phase 6 extraction demo

Run python -B scripts/run_extraction_demo.py with RULE2TEST_EXTRACTION_PROVIDER=mock. Inspect the pending proposal, simulation flag, source hashes and citations using extraction_cli.py show --full. Only after a human rule review should it be promoted to the typed workflow. The demo does not automatically approve rules or tests.

Run python -B scripts/evaluate_extraction.py for four labeled synthetic replay checks. They do not measure real-model Japanese extraction accuracy. See [AI_EXTRACTION.md](AI_EXTRACTION.md).

## Phase 7 retrieval demo

Run python -B scripts/run_retrieval_demo.py --backend faiss after installing requirements-retrieval.txt. It seeds six knowledge records with explicitly synthetic reviews, retrieves an age-66 test and recomputes DENY -> ALLOW for the new age-70 policy. Six duplicate boundary inputs are removed. The resulting batch remains unattached and unapproved.

The three-query retrieval check is labeled synthetic, not semantic model accuracy. See [RETRIEVAL.md](RETRIEVAL.md).
