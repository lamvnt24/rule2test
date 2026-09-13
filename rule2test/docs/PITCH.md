# Pitch

"Every rule change becomes test coverage and auditable evidence."

## Problem

Insurance rule changes can leave boundary cases untested and break the link between requirements, tests and execution results.

## Solution

Normalize rules with source citations, analyze changes, identify related tests, detect specific coverage gaps, propose candidates for QA review and produce traceable execution evidence.

## Demo highlight

A passing suite alone is not enough. Inject a comparator bug at the exact threshold: the test produces a concrete counterexample and the release gate becomes NO-GO.

The phase-2 CLI also demonstrates independent expected/actual execution for eligibility, claim review and deductible calculations.

## AI's role

AI helps interpret documents; deterministic engines verify behavior. When running the offline structured demo, state explicitly that the input is already normalized rule JSON.

## Evidence-based claims

Present synthetic seeded-gap benchmark results and the current DSL limitations. Do not claim time savings or production accuracy without measurements.

Every quotable number lives in [BENCHMARKS.md](BENCHMARKS.md) with its source artifact and an explicit statement of what it does not prove. The deck at [slides/index.html](slides/index.html) is generated from that file, so it cannot drift. Use the timed script in [COMPETITION_DEMO.md](COMPETITION_DEMO.md) and the diagrams in [DIAGRAMS.md](DIAGRAMS.md).
