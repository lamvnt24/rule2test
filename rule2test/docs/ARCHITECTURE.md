# Architecture decision record

The project uses standard-library HTTP and SQLite to minimize hackathon setup dependencies. The domain core is separated from transport so HTTP can later move to FastAPI and SUT implementations can be replaced through adapters.

## Trust boundaries

Untrusted document -> LLM proposal -> schema and literal citation validation -> human JSON review -> saved plan -> reviewer-approved candidate IDs -> deterministic execution.

The LLM does not determine PASS/FAIL. The current extraction adapter uses a fixed loopback Ollama endpoint, without a cloud API key. The UI escapes values before rendering HTML. SQL uses parameter binding. Rule execution does not use eval or execute AI-generated code.

## Legacy evidence envelope

- input_hash binds old/new rules and test inputs.
- rule_hash identifies the rule content used during execution.
- Each result includes its source quote.
- plan_id links analysis to execution.
- reviewer and approved_ids record the approval selection.
- timestamp and engine identify execution context.
- evidence_hash covers the complete payload before the hash itself is added.

To verify downloaded evidence, parse the JSON, remove evidence_hash and compare it with factory.core.digest(payload). The evidence GET endpoint returns the original envelope without adding evidence_id.

Hashes do not prevent someone with database access from changing the payload and recomputing its hash. Stronger audit storage requires signing and append-only storage.

## Phase-2 execution

The typed oracle evaluates decision tables while the independently configured insurance mock supplies actual results. The executor checks test approval and expected-result consistency before calling a SUT adapter.

Typed execution records the decision-table hash and evaluation date. Typed evidence includes decision-table snapshots. The CLI demonstrates these contracts; the legacy web server still uses its original dictionary-based workflow.

See [ENGINES.md](ENGINES.md) for supported conditions, financial calculations, HTTP contracts and timeout behavior.

## Limitations

The server uses synchronous request threads, without a background queue, LLM cancellation or authentication. It is intended for a local demo.

Independent expected/actual implementations can still share a specification misunderstanding; explicit fixtures and SME review remain necessary.

The stale mutant reduces the threshold by a fixed amount; it does not always represent the actual previous version of custom rules.

Unsupported DSL semantics are rejected. The demo is not a general insurance-reasoning engine.

## Phase-6 typed extraction

UTF-8 V1/V2 sources -> provider -> strict schema and exact-line citations -> typed rule validation -> immutable proposal -> explicit hash-bound rule review -> atomic workflow promotion.

The proposal, review and promotion use the existing scoped object store. Promotion archives source text, derived import, proposal and review in the same transaction as the workflow. Rule sources are rebound to original document hashes and line numbers; default-policy citations are retained. Existing test inputs/expectations are supplied by the host, not by the model.

The provider records simulated/mock or real/Ollama explicitly. Mock recognizes only exact fixtures, and the Ollama transport has not been evaluated against a live model. See [AI_EXTRACTION.md](AI_EXTRACTION.md).
