# What you should see

Every number here was produced by running this repository's own services while the kit was built.
Nothing is estimated. Synthetic data throughout; these are not production measurements.

## Analyze — designed coverage before you review anything

| Scenario | Candidate tests | Rule | Branch | Boundary | Exception |
| --- | --- | --- | --- | --- | --- |
| eligibility | 14 | 100% | 100% | 100% | 100% |
| claim_review | 11 | 100% | 100% | 100% | 100% |
| deductible | 13 | 100% | 50% | 100% | 100% |

## Execute and evaluate the gate

| Scenario | Injected fault | Pass | Fail | Error | Gate | Blocked by |
| --- | --- | --- | --- | --- | --- | --- |
| eligibility | none | 14 | 0 | 0 | **GO** | — |
| eligibility | boundary | 13 | 1 | 0 | **NO-GO** | execution_results |
| claim_review | none | 11 | 0 | 0 | **GO** | — |
| claim_review | boundary | 10 | 1 | 0 | **NO-GO** | execution_results |
| deductible | none | 13 | 0 | 0 | **NO-GO** | branch_coverage, resolved_obligations |
| deductible | deductible_off_by_one | 12 | 1 | 0 | **NO-GO** | execution_results, branch_coverage, resolved_obligations |

The deductible scenario is NO-GO even with no injected fault: the bounded search cannot prove away its
default branch, so an obligation stays unresolved. That is the intended contract, not a bug — say so if
a judge asks.

## AI rule review — offline mock provider

| Source pair | Extraction status | Authored truth |
| --- | --- | --- |
| ambiguous | needs_clarification | needs_clarification |
| claim_review | pending_review | pending_review |
| deductible | pending_review | pending_review |
| eligibility | pending_review | pending_review |

The mock replays the three exact shipped fixtures and refuses anything else, which is why `ambiguous`
asks for clarification. That is the correct answer for it, not a failure. A live model is configured
separately; see LIVE_AI.md.

## Things that are deliberately not proven here

- Coverage is not a pass rate and a GO verdict is not release authorization.
- Mock extraction is fixture replay, not language understanding.
- Reviewer acceptance, effort savings, production accuracy and token cost are unmeasured.
