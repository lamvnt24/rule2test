# Phase 4 — Persistent workflow, review and evidence

## Quick demo

```powershell
Set-Location -LiteralPath "E:\AI hackathon\rule2test"
python -B scripts/run_workflow_demo.py
```

This creates a new workflow in data/workflow-demo.db, analyzes a rule change, reopens the database, edits a test as a new revision, applies explicitly scripted synthetic review decisions, runs 14 tests and persists evidence.

Every invocation creates a separate workflow. The demo never clears existing data. Its synthetic approvals are not real user decisions.

Run all checks:

```powershell
python -B -m unittest discover -s tests -v
```

## Explicit human review CLI

workflow_cli.py stores its workflows in data/workflow.db by default. Pass --db PATH before the subcommand to use another database.

```powershell
Set-Location -LiteralPath "E:\AI hackathon\rule2test"
$rule2testState = python -B scripts/workflow_cli.py create-demo --actor BA | ConvertFrom-Json
$rule2testState = python -B scripts/workflow_cli.py analyze --workflow $rule2testState.workflow_id --revision $rule2testState.revision --actor BA | ConvertFrom-Json
$rule2testState = python -B scripts/workflow_cli.py start-review --workflow $rule2testState.workflow_id --revision $rule2testState.revision --actor QA | ConvertFrom-Json
$rule2testState.tests | Format-List
```

Inspect a test before reviewing it. For example, to approve the first reviewed test:

```powershell
$rule2testTest = $rule2testState.tests[0]
$rule2testState = python -B scripts/workflow_cli.py review --workflow $rule2testState.workflow_id --revision $rule2testState.revision --test-id $rule2testTest.test_id --test-revision $rule2testTest.revision --decision approved --actor QA --reason "Checked input and expected result" | ConvertFrom-Json
```

Repeat review for the remaining tests, using the latest workflow revision returned by each command. Decisions are approved, rejected or changes_requested.

Once every current test is approved or rejected, and at least one is approved:

```powershell
$rule2testState = python -B scripts/workflow_cli.py finalize --workflow $rule2testState.workflow_id --revision $rule2testState.revision --actor QA --reason "Review complete" | ConvertFrom-Json
$rule2testState = python -B scripts/workflow_cli.py execute --workflow $rule2testState.workflow_id --revision $rule2testState.revision --actor QA --profile eligibility | ConvertFrom-Json
python -B scripts/workflow_cli.py evidence --workflow $rule2testState.workflow_id --revision $rule2testState.revision --actor QA --output data/generated/reviewed-evidence.json
```

The evidence output file must not already exist. Database evidence remains available if a file export fails. Reload the current workflow revision before retrying.

## Commands

| Command | Purpose |
| --- | --- |
| create-demo | Create a DRAFT workflow from synthetic old/new rules and existing tests |
| show | Display current revision, status, tests and review decisions; --full includes snapshots and analysis |
| history | Read the ordered audit events |
| analyze | Persist phase-3 analysis and candidate/revision proposals |
| start-review | Move ANALYZED to IN_REVIEW |
| review | Approve, reject or request changes for a stored test revision |
| edit-test | Create a new test revision from a JSON patch; invalidate that test's approval |
| finalize | Verify all review decisions and reserve the reviewed suite as APPROVED |
| revise-rules | Store a higher table version, clear approvals and return to DRAFT |
| reopen-review | Explicitly reopen a completed/approved workflow; clear current approvals before rerun |
| execute | Run only approved stored tests against the configured mock |
| run-show | Read a persisted execution journal, including partial results |
| recover | Explicit operator recovery of an interrupted run; never replays tests |
| evidence | Build/retrieve durable evidence and optionally export JSON |

Run python -B scripts/workflow_cli.py COMMAND --help for parameters.
The Python WorkflowService.execute method also accepts a phase-2 HTTP SUT adapter. CLI execution currently exposes the mock profiles.

## Test edits

edit-test accepts --file with a JSON object containing inputs and expected, with an optional title. Other keys are rejected.

Example patch:

```json
{
  "inputs": [
    {"field": "age", "value": {"kind": "integer", "data": 65, "currency": null}}
  ],
  "expected": {"outcome": "allow", "amount": null, "formula": null},
  "title": "Exact maximum-age boundary"
}
```

Supply workflow ID/revision, test ID/revision, actor and reason. The backend retrieves the stored test and creates revision+1; client-provided rule references, hashes and approvals are not accepted.

Expected values inconsistent with the oracle cannot be approved. Editing an approved or completed test returns the workflow to IN_REVIEW. Other unchanged tests keep their current decisions; the edited test must be reviewed again. Historical tests, approvals and evidence remain available.

## Rule revisions

revise-rules accepts a JSON object with table, rules and optional ISO as_of date. Table/rule objects use their phase-1 to_dict schemas.

The table ID must remain stable and its version must increase. Changed rule snapshots must increase their rule versions. All current approvals are cleared, and the workflow returns to DRAFT for analysis and review.

Added/removed rule references that cannot be rebased still require explicit remapping; automatic semantic remapping is not implemented.

## State machine

DRAFT -> ANALYZED -> IN_REVIEW -> APPROVED -> EXECUTING -> EXECUTED -> EVIDENCED

- Pending decisions and changes_requested block finalization.
- Rejected tests are excluded from execution.
- At least one approved test is required.
- Every approved test is revalidated before the first outbound SUT call.
- EVIDENCED means evidence has been stored, not that all tests passed or a product release is authorized.
- Editing tests reopens review. Revising rules starts a new analysis cycle.
- Unexpected execution failures can leave INTERRUPTED; an abrupt process stop may leave EXECUTING.

Each change increments the workflow revision. All mutation commands require the caller's expected revision. A stale browser/CLI command raises ConflictError rather than replacing newer data.

## Persistence and transactions

Database creates schema migration 1 and uses wf_ tables, leaving the legacy records table unchanged.

- wf_objects: immutable application-level snapshots for rules, tables, test revisions, approvals, workflows and evidence.
- wf_heads: current workflow revision.
- wf_runs: durable execution journals updated as each test completes.
- wf_events: ordered audit events with actor, reason and workflow revision.
- wf_schema_migrations: applied migration versions.

Snapshots are scoped by workflow, so unrelated workflows cannot reuse each other's approvals. Repositories validate content hashes when loading snapshots. Writing different content to the same scoped ID/revision raises ConflictError.

Mutations use BEGIN IMMEDIATE transactions and compare-and-swap workflow heads. Snapshot writes, current-state changes and audit events commit together or roll back together.

The application does not hold a SQLite write transaction while calling a SUT. It persists an execution reservation first, then records results after each call. Analysis is synchronous and runs inside a transaction; a task queue and higher-scale database are future work.

## Interruptions and duplicate execution

An active run blocks editing, review and another execute request. The execution journal is committed after each completed test.

If the process dies after calling a SUT but before saving a result, the external effect may already have occurred. There is no automatic replay or exactly-once guarantee across a remote SUT.

Before using recover, the operator must stop the old worker and reconcile external effects. Recover records the operator's reason, marks the journal interrupted and clears current approvals. Review is required again before another run.

Recovery cannot cancel an in-flight external call. The worker checks its reservation before subsequent calls and before recording a result, but a call already in progress may finish. Interrupted journals remain inspectable with run-show and cannot be presented as completed evidence.

## Evidence

EvidenceService loads the approved workflow revision referenced by the completed run, selects exactly the approved tests, verifies journal completeness and persists the typed Evidence snapshot.

Creating evidence again for the current EVIDENCED revision returns the stored record. Prior evidence remains readable after later test/rule edits.

The CLI can export a new JSON file. SQLite stores the canonical snapshot and content hash.

## Validation and limitations

Tests cover reopen/restart persistence, migration idempotency, legacy-table preservation, rollback, stale revisions, explicit CLI review, rejected/pending tests, edits, rule changes, duplicate execution, partial crash journals, operator recovery and historical evidence.

Reviewer/actor names are self-declared. Authentication, RBAC, separate rule-owner approval and signed append-only audit storage are not implemented. Hashes detect inconsistent content but do not prevent a database administrator from rewriting data and hashes.

The workflow layer is available through Python, CLI and the phase-8 browser workspace. The root UI and /api/v1 use the same services; /legacy retains the original demo. See [WORKSPACE.md](WORKSPACE.md).

