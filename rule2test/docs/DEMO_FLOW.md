# Demo flow

1. Run `python -m factory.server` from the project root.
2. Open http://127.0.0.1:8000 and load the synthetic demo.
3. Analyze the rule delta, impact and boundary gaps.
4. Select candidates, enter a reviewer and run the correct mock.
5. Run again with the boundary fault; inspect failures and NO-GO.
6. Download the evidence JSON.

The current UI is web/index.html. streamlit_app is a scaffold, not yet a runnable Streamlit interface.

## Phase 3 CLI
Run python -B scripts/run_analysis_demo.py from the project directory for rule delta, related/changed tests, gap candidates, coverage, mutation and independent execution evidence. This CLI uses scripted synthetic approvals and does not alter the web workflow.

## Phase 4 persistence demo
Run python -B scripts/run_workflow_demo.py. The demo persists 14 test results and evidence, then reopens the database to verify the saved workflow. Use workflow_cli.py for explicit human review decisions; see [WORKFLOWS.md](WORKFLOWS.md).

## Phase 6 extraction demo

Run python -B scripts/run_extraction_demo.py with RULE2TEST_EXTRACTION_PROVIDER=mock. Inspect the pending proposal, simulation flag, source hashes and citations using extraction_cli.py show --full. Only after a human rule review should it be promoted to the typed workflow. The demo does not automatically approve rules or tests.

Run python -B scripts/evaluate_extraction.py for four labeled synthetic replay checks. They do not measure real-model Japanese extraction accuracy. See [AI_EXTRACTION.md](AI_EXTRACTION.md).
