# Benchmarks

Every number below is copied from an artifact in this repository. The collector computes nothing.
Regenerate with `py -3 -B scripts/collect_benchmarks.py --force`.

| Measurement | Value | What it measures | What it does not prove | Source |
| --- | --- | --- | --- | --- |
| Quality-gate contract cases matched | **6/6** | Six synthetic workflows reach the GO/NO-GO verdict the contract requires, including the deliberate NO-GO fixtures. | Not seeded-gap recall, not real-model quality, and not production release authorization. | `data/generated/quality-gate-benchmark.json` |
| Designed boundary coverage, baseline to final | **16.67% → 100.0%** | Boundary obligations covered by the existing suite versus the suite after generated candidates, on the synthetic eligibility scenario. | Designed coverage on one synthetic scenario. Coverage is not a pass rate and not release approval. | `data/generated/phase3-analysis-report.json` |
| Mutation score on the same scenario | **100.0%** | Specification mutants killed by the designed suite. | A small fixed mutant set on one scenario; not a general fault-detection rate. | `data/generated/phase3-analysis-report.json` |
| Offline mock replay — extraction cases matched | **5/10** | Authored Japanese single-rule spot checks against separate ground truth (synthetic-replay-v1). Breakdown: ambiguity 2/2, numeric_variant 0/1, paraphrase 0/3, replay 3/3, untrusted_instruction 0/1. | Ten authored cases only. Not representative Japanese document accuracy and not an SME-reviewed benchmark. | `data/generated/phase10-mock-evaluation/report.json` |
| Offline mock replay — schema and citation valid | **10/10** | Outputs that survived strict JSON, schema and exact-line citation validation before truth comparison. | A valid citation proves the quote exists, not that the interpretation is semantically correct. | `data/generated/phase10-mock-evaluation/report.json` |
| Offline mock replay — median extraction latency | **0 ms** | Host-measured wall-clock time per case on the machine that produced this artifact. | Includes cold model loading and host validation. Not a throughput or cost measurement. | `data/generated/phase10-mock-evaluation/report.json` |
| Offline mock replay — retrieval top-1 | **5/9** | Hybrid lexical+vector ranking put the expected workflow first. MRR@3 0.611. | Only three approved test records are indexed, so this measures ranking on a tiny corpus, not embedding quality. | `data/generated/phase10-mock-evaluation/report.json` |
| Offline mock replay — age-66 ALLOW witness found | **True** | One fixed witness: the retrieved age-66 input is recomputed as ALLOW against the new 18..70 policy. | A single witness plus grounding checks. The host oracle computes the expected outcome, so this is not model reasoning accuracy. | `data/generated/phase10-mock-evaluation/report.json` |
| Offline mock replay — evaluated proposals auto-approved | **False** | The evaluator never approves, promotes or attaches anything it generated. | Nothing. This is a guardrail check, not a performance measurement. | `data/generated/phase10-mock-evaluation/report.json` |
| Live cloud model, prompt v1 — extraction cases matched | **2/10** | Authored Japanese single-rule spot checks against separate ground truth (gpt-oss:120b-cloud). Breakdown: ambiguity 2/2, numeric_variant 0/1, paraphrase 0/3, replay 0/3, untrusted_instruction 0/1. | Ten authored cases only. Not representative Japanese document accuracy and not an SME-reviewed benchmark. | `data/generated/phase10-cloud-evaluation/report.json` |
| Live cloud model, prompt v1 — schema and citation valid | **2/10** | Outputs that survived strict JSON, schema and exact-line citation validation before truth comparison. | A valid citation proves the quote exists, not that the interpretation is semantically correct. | `data/generated/phase10-cloud-evaluation/report.json` |
| Live cloud model, prompt v1 — median extraction latency | **4991 ms** | Host-measured wall-clock time per case on the machine that produced this artifact. | Includes cold model loading and host validation. Not a throughput or cost measurement. | `data/generated/phase10-cloud-evaluation/report.json` |
| Live cloud model, prompt v1 — retrieval top-1 | **9/9** | Hybrid lexical+vector ranking put the expected workflow first. MRR@3 1.000. | Only three approved test records are indexed, so this measures ranking on a tiny corpus, not embedding quality. | `data/generated/phase10-cloud-evaluation/report.json` |
| Live cloud model, prompt v1 — age-66 ALLOW witness found | **True** | One fixed witness: the retrieved age-66 input is recomputed as ALLOW against the new 18..70 policy. | A single witness plus grounding checks. The host oracle computes the expected outcome, so this is not model reasoning accuracy. | `data/generated/phase10-cloud-evaluation/report.json` |
| Live cloud model, prompt v1 — evaluated proposals auto-approved | **False** | The evaluator never approves, promotes or attaches anything it generated. | Nothing. This is a guardrail check, not a performance measurement. | `data/generated/phase10-cloud-evaluation/report.json` |
| Live cloud model, prompt v2 — extraction cases matched | **4/10** | Authored Japanese single-rule spot checks against separate ground truth (gpt-oss:120b-cloud). Breakdown: ambiguity 1/2, numeric_variant 0/1, paraphrase 1/3, replay 1/3, untrusted_instruction 1/1. | Ten authored cases only. Not representative Japanese document accuracy and not an SME-reviewed benchmark. | `data/generated/phase10-cloud-prompt-v2/report.json` |
| Live cloud model, prompt v2 — schema and citation valid | **5/10** | Outputs that survived strict JSON, schema and exact-line citation validation before truth comparison. | A valid citation proves the quote exists, not that the interpretation is semantically correct. | `data/generated/phase10-cloud-prompt-v2/report.json` |
| Live cloud model, prompt v2 — median extraction latency | **4678 ms** | Host-measured wall-clock time per case on the machine that produced this artifact. | Includes cold model loading and host validation. Not a throughput or cost measurement. | `data/generated/phase10-cloud-prompt-v2/report.json` |
| Live cloud model, prompt v2 — retrieval top-1 | **9/9** | Hybrid lexical+vector ranking put the expected workflow first. MRR@3 1.000. | Only three approved test records are indexed, so this measures ranking on a tiny corpus, not embedding quality. | `data/generated/phase10-cloud-prompt-v2/report.json` |
| Live cloud model, prompt v2 — age-66 ALLOW witness found | **True** | One fixed witness: the retrieved age-66 input is recomputed as ALLOW against the new 18..70 policy. | A single witness plus grounding checks. The host oracle computes the expected outcome, so this is not model reasoning accuracy. | `data/generated/phase10-cloud-prompt-v2/report.json` |
| Live cloud model, prompt v2 — evaluated proposals auto-approved | **False** | The evaluator never approves, promotes or attaches anything it generated. | Nothing. This is a guardrail check, not a performance measurement. | `data/generated/phase10-cloud-prompt-v2/report.json` |
| Automated test suite | **275 passing** | Unit, integration and evaluation tests on the machine producing this summary (ran 275 tests in 43.383s). | Test count is not a quality metric; it does not measure insurance-domain correctness. | `tests/` |

## How to read these numbers

- The mock replay and the live model numbers are not comparable: mock extraction matches only exact fixtures.
- Prompt v2 was written after inspecting prompt v1 failures, so it is not independent held-out validation.
- Latency figures describe one machine and one run, including cold model loading.

## Explicitly unmeasured

- real reviewer acceptance
- manual effort savings
- production accuracy
- token usage and monetary cost
- independent SME-reviewed labels

Synthetic results are not production measurements. A GO verdict is a local regression assessment,
not release authorization. See [quality gate](QUALITY_GATE.md) and [live AI](LIVE_AI.md).
