# Phase 9 — Regression quality gate

## Purpose

A read-only, versioned assessment of the current persisted workflow. It answers whether the available regression evidence meets the local demo policy, with explicit GO/NO-GO checks. It does not approve tests, change workflow state, or authorize a production release.

The report binds to workflow revision/hash, approved revision/hash, run hash and evidence hash. Reads use one SQLite transaction. A reopened or edited workflow cannot reuse the old GO verdict. Downloaded reports remain historical snapshots; evaluate again for the current state.

## Use in the workspace

1. Complete test review and finalization.
2. Execute the independent SUT and create evidence.
3. Open **Run & evidence → Regression quality gate → Evaluate current revision**.
4. Inspect each observed value and requirement.
5. Download this gate report to preserve the displayed snapshot.

The UI reports absent coverage categories as N/A, not 0%. The gate report is separate from canonical evidence; phase-4 evidence hashes and serialization remain unchanged.

## Policy local-regression-v1

| Check | Required result |
| --- | --- |
| Current evidence | Current workflow is EVIDENCED |
| Complete run | Completed journal with exactly one execution per approved test |
| Execution results | Every approved execution PASS; no FAIL, ERROR or SKIPPED |
| Rule coverage | At least 90%, with a nonzero rule denominator |
| Branch, boundary, exception coverage | At least 90% of executed obligations; N/A if a category has no obligations |
| Resolved obligations | No unresolved bounded-search obligations |
| Candidate acceptance | At least 70% of current non-existing-origin candidates approved; N/A if none exist |
| Archived rule traceability | 100% of executions link through verified rule snapshots to archived original source bytes |
| Evidence consistency | Evidence matches the approved tests/rules/table and completed journal |

Coverage thresholds compare integer counts, not rounded percentages. FAIL results still exercise inputs for coverage but block the execution-results check. A passing subset is not sufficient when coverage or acceptance is below threshold.

Candidate acceptance uses all current tests whose origin is not existing, including deterministic, LLM and human additions. It is a local suite metric, not an estimate of live-model quality or real reviewer acceptance. Rejected candidates remain in its denominator. Synthetic scripted approvals must not be reported as observed SME acceptance.

Source-free CLI workflows may have valid rule/test hashes but cannot claim archived-source traceability. Corrupt stored hashes or source bytes produce a validation error rather than a GO report. A draft or reopened review returns NO-GO with no invented execution metrics.

Thresholds are versioned constants in the service, not client-controlled overrides. A future policy change must use a new policy version.

## API and CLI

- GET /api/v1/workflows/{id}/quality-gate: current assessment.
- GET /api/v1/workflows/{id}/quality-gate-report: canonical JSON download of the assessment at request time.

The browser's download button exports the exact displayed report, avoiding an implicit reassessment between display and download.

```powershell
python -B scripts/quality_gate.py --db data/workspace.db --workflow YOUR_WORKFLOW_ID
python -B scripts/quality_gate.py --db data/workspace.db --workflow YOUR_WORKFLOW_ID --output data/generated/gate-report.json
```

Exit codes: 0 GO, 2 NO-GO, 1 invalid input/storage/output failure. The database must already exist. Output files use exclusive creation and are not overwritten. The parent output directory must exist.

Verify report_hash by removing that field and hashing UTF-8 JSON encoded with ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False. factory.services.quality_gate_service.canonical_report implements this serialization. Hashes detect content changes; they are not digital signatures.

## Synthetic benchmark

```powershell
python -B scripts/evaluate_quality_gate.py
python -B scripts/evaluate_quality_gate.py --output data/generated/quality-gate-benchmark.json
```

Six fixed expectations are defined independently of the returned verdict:

| Profile | Fault | Expected verdict |
| --- | --- | --- |
| Eligibility | None | GO |
| Eligibility | Boundary | NO-GO |
| Claim review | None | GO |
| Claim review | Boundary | NO-GO |
| Deductible | None | NO-GO: unresolved default branch |
| Deductible | Off by one | NO-GO: failed execution and unresolved branch |

The deductible fixture has an unreachable default under valid input semantics, but the bounded gap search does not prove that branch away. The gate deliberately retains that unresolved obligation. A future reachability proof may justify revising the obligation set; this phase does not lower the threshold or silently exclude it.

The benchmark uses temporary databases, synthetic documents and explicitly scripted approvals. It reports matching gate expectations and elapsed scenario time. These are contract checks, not real-model accuracy, seeded-gap recall, cost savings or production latency.

## Unmeasured metrics

Seeded-gap recall requires separate labeled truth; model extraction/retrieval accuracy requires a real-model evaluation; manual effort savings require a measured human baseline. The report lists these as unmeasured rather than inventing KPI values.

## Files and verification

- factory/services/quality_gate_service.py: consistent snapshot reads and versioned policy.
- scripts/quality_gate.py: CLI assessment/export.
- scripts/evaluate_quality_gate.py: six-case synthetic benchmark.
- tests/integration/test_quality_gate.py: coverage/failure distinction, stale state, integrity and read-only checks.
- tests/integration/test_workspace_api.py: API/report consistency.
- scripts/check_workspace_browser.py: displayed GO and report download.

Run python -B -m unittest discover -s tests -v. Optional Chromium verification uses python -B scripts/check_workspace_browser.py.
