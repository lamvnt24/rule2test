# Phase 3 — Rule analysis and regression test services

## Run the complete demo

```powershell
Set-Location -LiteralPath "E:\AI hackathon\rule2test"
python -B scripts/run_analysis_demo.py
python -B -m unittest discover -s tests -v
```

To save the full analysis, candidate tests and both evidence snapshots:

```powershell
python -B scripts/run_analysis_demo.py --output data/generated/analysis-demo.json
```

The output directory must exist. The script refuses to overwrite an existing file; choose a new filename for another export.

The demo changes the maximum eligible age from 60 to 65, analyzes three existing tests, proposes new revisions and missing candidates, applies explicitly synthetic approvals, executes a correct and a faulty mock, and builds evidence snapshots. The services themselves never approve tests.

## Implemented modules

| Module | Responsibility |
| --- | --- |
| rule_delta_service.py | Added/removed/modified semantic rule changes, with presentation-only revisions listed separately |
| impact_service.py | Rule-ID dependencies, old/new outcomes and stale expected results |
| gap_service.py | Bounded boundary, exception and branch obligations with unresolved reporting |
| generation_service.py | Deduplicated candidate generation and explicit revision proposals |
| coverage_service.py | Separate designed-input and executed-input coverage |
| mutation_service.py | Specification mutations with test witnesses, surviving mutants and invalid mutants |
| models/analysis.py | Immutable, JSON-serializable analysis reports |
| services/_support.py | Canonical input identity, references and bounded witness search |
| engines/oracle_engine.py | Evaluation traces identifying the selected row or default branch |

Example imports:

```python
from factory.services import (
    RuleDeltaService, ImpactService, GapService,
    GenerationService, CoverageService, MutationService,
)
```

All services use the phase-1 models and phase-2 engine. The original web demo and factory.core remain compatible; the new services are currently exposed through Python and the CLI.

## Delta semantics

Rule IDs map versions. Duplicate IDs, decreasing versions and changed snapshots with an unchanged version are rejected.

Condition order in an AND clause, titles, source formatting and metadata do not create a semantic rule delta. Changed snapshots with equivalent semantics are still listed in presentation_only_rule_ids. Money values with different Decimal scales compare canonically.

Conditions, actions, deductible formulas, currencies and effective intervals are semantic. RuleDelta retains exact before/after snapshots and exact changed fields for provenance.

Added and removed rules are supported by the delta service, including an empty version. The current DecisionTable model requires at least one row; a completely empty executable policy needs a future explicit model.

## Impact semantics

Each test receives related, status, old_expected, new_expected, expected_is_stale and a reason.

- changed: evaluated outcomes differ.
- unchanged: related to a change, but its outcome is unchanged.
- unaffected: in scope, with no related semantic/table change and no outcome change.
- unrelated: no rule-ID dependency in either table.
- unknown: added/removed dependencies, unsupported input or a decision-table conflict prevents a reliable comparison.

Default actions, hit policy, row order and evaluation date changes also trigger impact checks. This is deterministic rule-ID mapping and execution comparison, not embedding-based semantic retrieval.

Impact never changes a stored test. GenerationService.rebase creates revision+1 proposals with current rule references and new expected results; they require new approval. Unknown or removed references require explicit remapping.

## Gap obligations and bounded search

Each active row receives:
- A branch obligation to select the row.
- Below/at/above probes for each numeric condition.
- Null, missing, negative, overflow and wrong-type inputs for relevant fields.
- Wrong-currency input for money fields.
- Below/at/above deductible probes for payout formulas.

The table also has a default-branch obligation and probes for a default deductible formula if present.

The default step is 1 year for age and 1 currency unit for money. Configure money_step=Decimal("0.01") for cent-level boundaries. This is an explicit testing resolution, not automatic currency rounding.

Search uses condition and formula thresholds, domain endpoints, null and missing. It holds other row conditions true where possible and avoids selecting a shadowed row for a positive boundary witness. The default budget is 4,096 input combinations; exceeding it raises a clear error instead of silently truncating coverage.

An obligation with no witness remains unresolved and remains in the coverage denominator. This means "no witness found in this bounded search", not proof that the branch is unreachable. Tables without active rows are rejected for analysis; choose an applicable evaluation date.

An ALWAYS-applicable deductible row may leave its default branch unresolved. A default branch in that situation is not quietly counted as covered.

## Candidate generation and determinism

Candidates group missing obligations by canonical full input. One candidate can cover multiple obligations. IDs are derived from the table snapshot, evaluation date and inputs. Existing tests and proposals are immutable.

Expected results come from the oracle; candidates carry current rule hashes, rationale and obligation IDs. No approval is created by a service.

Repeated calls with the same table, inputs, search configuration and metadata produce identical candidate records. Changed metadata or snapshots produce different content hashes. Missing fields and explicit MISSING values share input identity; NULL remains distinct.

The gap report binds the table hash and evaluation date. Generation rejects a report from another table or evaluation date.

## Coverage definitions

All metrics contain covered and total counts. The percent property returns null when the denominator is zero.

- Rule coverage: active rules whose rows are actually selected by an eligible input. Merely listing a rule reference is insufficient.
- Branch coverage: selected active rows plus the table's default branch.
- Boundary coverage: explicit below/at/above witness inputs present in the suite.
- Exception coverage: explicit exceptional witness inputs present in the suite.

Boundary and exception obligations match the complete canonical witness input, not just one numeric field. This is a finite input-obligation metric, not MC/DC, exhaustive path coverage or proof of semantic completeness.

Designed-input mode can count inputs from tests mapped to older versions of the same rule ID. It measures the inventory of useful inputs, not whether those tests have current expected results or approval. Use ImpactService to identify stale expectations and rebase before execution.

Executed-input mode requires matching test hashes, current rule references, table hash and evaluation date. Only PASS and FAIL executions count as exercised. ERROR and SKIPPED do not count. FAIL may increase coverage, but it still indicates incorrect behavior.

Unresolved obligations stay uncovered. Coverage is not a release gate or reviewer acceptance score.

## Mutation analysis

This phase mutates the structured specification, not deployed application source code. It tests whether the suite distinguishes alternative rule behavior.

Mutations include strict/inclusive comparator flips, EQ/NE flips, threshold shifts, deductible shifts, optional restoration of previous conditions/actions, and a changed default outcome.

Each mutation reports:
- killed: at least one named test produces a different outcome.
- survived: the suite did not distinguish the mutation.
- invalid: the mutated table cannot be validated or conflicts on an evaluated input.

Score = killed / (killed + survived). Invalid mutations are shown separately and excluded. An empty suite has no score. Equivalent mutants are not proven equivalent or removed, so they can remain survived; the score is conservative in that respect.

Tests must reference current rules and have expected results consistent with the original oracle. Stale tests are rejected. The default mutation budget is 200; exceeding it raises an error.

The independent mock's injected faults remain separate from specification mutation. The full demo also runs the generated suite against that mock to show an actual expected/actual failure.

## Validation

The tests include explicit boundary truth sets, related-versus-changed impact, presentation-only edits, Decimal identity, compound conditions, shadowed rows, unresolved defaults, search/mutation budgets, revision proposals and execution provenance.

Seeded-gap evaluation defines held-out age and claim thresholds independently of the generator. It is a synthetic benchmark, not production accuracy.

## Next phase

Approval persistence, editable review workflows and state transitions belong to phase 4. Excel ingestion, live semantic retrieval and the new UI/API integration remain later stages.

## Phase 4 integration
Persistent workflow, approval and evidence services now orchestrate these analysis services. See [WORKFLOWS.md](WORKFLOWS.md). The earlier phase-4 roadmap above describes the original phase-3 handoff.
