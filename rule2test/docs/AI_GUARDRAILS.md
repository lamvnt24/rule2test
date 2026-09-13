# AI guardrails

## Typed extraction pipeline (phase 6)

- Providers return untrusted JSON; host validators check exact fields, bounds, source version, line and quote, followed by domain validation.
- Every rule and policy row requires a citation. Missing facts should produce needs_clarification with no executable rule rows.
- Literal source grounding does not prove interpretation accuracy. A human must inspect operators, thresholds, outcomes and omitted conditions.
- Proposals, reviewer decisions and promotion records are immutable and hash-bound. Explicit rule approval precedes workflow creation; test approval still precedes execution.
- Source bytes, raw response, prompt hash/version, provider/model, simulation flag and review are retained for audit.
- Mock replay is labeled simulated and is not used as evidence of language understanding.
- Ground truth is excluded from extraction. Existing test answers are excluded from the Ollama prompt.
- Document text is data, not instructions. No provider output is executed as code or used to authorize actions.
- Provider failures do not fall back to mock. Limits, socket timeout and disabled redirects bound the local transport.
- Provider exception bodies are not persisted because they may contain transport or credential details.
- The oracle and independent SUT determine expected/actual results; the LLM never assigns PASS/FAIL.

## Existing web demo

The original Ollama adapter validates supported threshold fields and literal source quotes. Its review/UI workflow is separate from the new typed extraction pipeline.

## Remaining work

Authenticated reviewer identity, role enforcement, cloud providers, broader semantic/adversarial evaluation, signed evidence and stronger audit storage are not implemented. Hashes do not prevent an administrator rewriting content and hashes.

Use synthetic data for the hackathon demo. Never commit secrets. See [AI_EXTRACTION.md](AI_EXTRACTION.md) for executable commands, supported input and limitations.

## Phase 7 retrieval

- Corpus scope is explicit; rule/test reviews are independently checked and revalidated at search/proposal/attachment.
- Old expected results are never authoritative for a new policy. The current oracle supplies candidate expected values.
- Only IDs in the actual retrieved context can be cited; schema validation rejects provider-supplied expected values and approvals.
- Canonical input deduplication removes repeated cases. Missing-gap claims require matching deterministic obligations.
- Candidate attachment archives the batch/corpus atomically and creates no approvals.
- Mock lexical embeddings and scripted suggestions are labeled simulated; three-query fixture metrics are not semantic accuracy.
- Embedding model revision is operator-declared. Change it and rebuild after changing weights/preprocessing.
- Reviewer authentication, cross-tenant authorization and signed evidence remain unimplemented.
