# Phase 1: domain contracts

Implemented with frozen, keyword-only standard-library dataclasses. No new dependencies. The running demo still uses factory/core.py; these contracts will be integrated during phase 2.

## Modules
- common: strict Model serialization, typed Value, SourceReference, RuleReference, Metadata, WorkflowStatus.
- rule: AND conditions, explicit operators, actions, versioned Rule with source citations and optional inclusive effective interval.
- decision_table: rows, mandatory default action, UNIQUE / FIRST / COLLECT policy. FIRST uses tuple order. Evaluation, overlap detection and COLLECT action conflict handling belong to the engine phase.
- rule_delta: added/removed/modified snapshots; modified fields must match actual snapshot differences.
- test_case: immutable inputs, expected action, origin, test type, rationale, obligations and versioned rule references.
- approval: approve/reject/request changes for exact subject revision and hash.
- execution: PASS/FAIL require actual and consistent equality; ERROR/SKIPPED require a reason and no actual.
- evidence: self-contained snapshot checks rule/test hashes, approval revision, approval timing and execution linkage.
- config: Settings.from_env; exceptions: transport-independent typed application errors.

## JSON contract
Call model.to_dict()/to_json() and ModelClass.from_dict()/from_json().
Unknown fields, missing required fields and incorrect scalar types are rejected. Python constructors require enum instances and tuples; JSON accepts enum string values and arrays.
Decimal uses {"$decimal":"150000000.00"}, date uses {"$date":"2026-09-11"}, datetime uses {"$datetime":"2026-09-11T00:00:00+00:00"}.
Money is Decimal with a three-letter currency identifier; floats are rejected. This validates code shape, not a currency registry or currency-specific rounding.
Missing and null are different ValueKind variants. Test inputs can contain negative numbers or wrong-type values intentionally; age rule thresholds must be integers 0..120.
Metadata timestamps require timezone information. Immutable tuples prevent accidental nested list mutation.
content_hash hashes sorted compact UTF-8 JSON. Hashes represent exact serialized snapshots, not semantic equivalence (Decimal scale and timezone representation are retained).

## Configuration
Settings is an explicit API for future dependency injection; the legacy server does not consume it yet. from_env does not load .env files.
RULE2TEST_HOST, RULE2TEST_PORT, RULE2TEST_DATABASE_PATH, RULE2TEST_LLM_PROVIDER, RULE2TEST_REQUEST_TIMEOUT_SECONDS, OPENAI_API_KEY, OPENAI_MODEL, OLLAMA_MODEL.
Default provider is mock. Selecting a real provider requires explicit configuration. Config validation does not call an API or instantiate a provider. API keys are excluded from Settings repr.

## Boundaries
This phase defines and validates data only. It does not execute compound conditions, calculate deductible formulas, enforce repository transitions, authenticate reviewers or validate citations against document bytes. Evidence hash validation detects inconsistent snapshots but is not a digital signature. Source document hash/quote authenticity requires parser validation.
Current payout action models a fixed amount; dynamic deductible expressions require a later DSL extension.

## Phase 2 extensions
Action now supports an explicit PayoutFormula for deductible calculation. Execution records table hash and evaluation date; Evidence includes decision-table snapshots. See [ENGINES.md](ENGINES.md), including serialization/hash compatibility notes. Earlier fixed-payout-only limitations above describe phase 1.
