# Phase 2 — Engines, validators and SUT adapters

## Implemented modules

| Module | Responsibility |
| --- | --- |
| factory/engines/oracle_engine.py | Compute expected results from decision tables without calling the SUT |
| factory/engines/insurance_engine.py | Independent insurance mock with separate configuration |
| factory/engines/test_executor.py | Validate approval and expected results, invoke the adapter and create Execution |
| factory/providers/sut/base.py | Adapter contract that accepts only test inputs |
| factory/providers/sut/mock.py | Adapter for the insurance mock |
| factory/providers/sut/http.py | POST inputs and read a concrete Action over HTTP |
| factory/validators/rule_validator.py | Validate the DSL, source-rule hashes, currencies and effective dates |
| factory/validators/test_validator.py | Validate inputs and approval revision/hash |
| factory/validators/llm_output_validator.py | Validate Rule JSON, document bytes/hash and quotes in UTF-8 text |

## Run and test

Start in the project directory:

```powershell
Set-Location -LiteralPath "E:\AI hackathon\rule2test"
python -B -m unittest discover -s tests -v
python -B scripts/run_engine_demo.py
```

The CLI runs three business scenarios, each with a correct mock and an injected bug. Expect three PASS results and three intentional FAIL results. Script approvals are synthetic fixtures, not real user review decisions.

Each run creates in-memory Evidence containing decision-table, rule, test, approval and execution snapshots. The script prints results and hashes; it does not write to SQLite.

## Supported business scenarios

1. Eligibility: ages 18..65 inclusive produce ALLOW; other valid ages produce DENY.
2. Claim review: amounts above 150 million VND produce REVIEW; amounts at or below the threshold produce ALLOW.
3. Deductible: payout = max(claim_amount - 10 million VND, 0).

The mock has its own min_age, max_age, claim_threshold, deductible and currency configuration. The SUT receives neither rules nor expected results from the oracle. These values are demo assumptions, not universal insurance rules.

The oracle supports age (integer 0..120) and claim_amount (MONEY 0..1 billion, at most 12 decimal places), with one currency per table. Money calculations use Decimal and localcontext precision 64.

Conditions within a row use AND. Supported operators are EQ, NE, LT, LE, GT, GE, IS_NULL and IS_MISSING. No eval or AI-generated code is executed.

UNIQUE raises ConflictError when multiple rows match. FIRST uses row order. COLLECT is rejected because Execution currently represents one Action.

Rules with effective_from require an explicit as_of date. Effective intervals are inclusive. Inactive rows are ignored; the table's default action applies when no active row matches.

There is no pre-execution solver for overlaps or unsatisfiable conditions. UNIQUE collisions are detected for the input being evaluated.

## Invalid data and execution errors

- Invalid input types, domains or currencies, and missing required inputs, produce INVALID.
- IS_NULL and IS_MISSING can be handled explicitly in rule rows; the two are distinct.
- Unsupported fields raise ValidationError.
- Approval revision/hash mismatches or expected results that disagree with the oracle are rejected before the SUT is called. Approved expected results are never silently rewritten.
- Actual differing from expected produces FAIL.
- Timeouts, network failures, HTTP errors and invalid response schemas produce ERROR with actual=None.
- Programming errors outside the adapter error contract are not silently converted to PASS/FAIL.

The HTTP adapter enforces a socket timeout. The executor also checks elapsed time after an adapter returns. This is not a hard-cancellation mechanism for an arbitrary hanging Python adapter. New adapters must enforce their own I/O timeouts; process isolation is a future extension.

## HTTP contract

The endpoint is configured by the developer when constructing HttpSUTAdapter. The current UI does not accept SUT endpoint URLs.

Request:

```json
{"inputs":[{"field":"age","value":{"kind":"integer","data":65,"currency":null}}]}
```

Response: status 200, Content-Type application/json, with a concrete Action body:

```json
{"outcome":"allow","amount":null,"formula":null}
```

The adapter does not send expected results, rules, approvals or test rationale. It does not automatically retry POST requests or follow redirects. Responses are limited to 64 KiB by default.

Endpoints with a different schema require a mapping or custom adapter. Authentication integration and verification against an external insurance system have not been implemented; integration tests use a localhost server.

## Model extensions and provenance

Action now supports PayoutFormula(field="claim_amount", deductible=Value(MONEY)).
A PAYOUT must contain exactly one of a fixed amount or a formula. The oracle resolves formulas into concrete amounts before comparison.

Execution records decision_table_hash and evaluation_date. Evidence includes decision_tables so snapshots can be checked against execution hashes.

New fields have defaults for older constructor inputs. Canonical Action JSON now includes formula=null, so hashes of older typed models may change when reserialized. No migration is provided for externally stored typed snapshots. The legacy SQLite demo uses a separate dictionary schema and is unchanged.

## Compatibility and remaining work

factory.core retains analyze, execute and digest, and re-exports validate, oracle and mock_sut. Legacy threshold validation, oracle logic and mock logic have moved into dedicated modules.

The web UI and HTTP server still run the legacy workflow. The new typed executor is available through the Python API and CLI, but is not yet connected to the UI.

Delta, impact, gap, generation, coverage and mutation services belong to phase 3. Complete approval persistence and workflow state transitions belong to phase 4.

The LLM source validator currently accepts UTF-8 bytes, not binary XLSX/PDF files, and does not prove semantic interpretation of a quote.

## Phase 3 integration
OracleEngine.trace now returns the action, selected row IDs and default-branch flag. The six phase-3 services use these traces for coverage and witness selection. See [ANALYSIS_SERVICES.md](ANALYSIS_SERVICES.md).
