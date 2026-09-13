# Phase 11 — Logging, tracing, metrics, provider errors and demo packaging

Local-demo diagnostics built on the standard library. This is not production telemetry: nothing is exported,
sampled or persisted, and every counter resets when the process stops.

## Turning diagnostics on

Logging is **off** until an entry point calls `factory.observability.logger.configure()`. Importing the library
never writes to a stream, so the CLI demos and the test suite stay quiet unless they opt in.

| Variable | Values | Default |
| --- | --- | --- |
| `RULE2TEST_LOG_LEVEL` | off, debug, info, warn, error | info |
| `RULE2TEST_LOG_FILE` | append-mode path; empty means stderr | empty |

```powershell
$env:RULE2TEST_LOG_LEVEL="debug"
py -3 -B scripts/run_demo.py --seed
```

`factory.server.main` and `scripts/run_demo.py` call `configure()` and print the resolved level and destination.
An unknown level raises `ConfigurationError` instead of falling back to a default.

## What a log line contains

One JSON object per line, sorted keys, UTF-8, never wrapped. Fields come from an explicit **allowlist**
(`factory/observability/logger.py`), not a denylist:

```json
{"component":"transport","duration_ms":12.4,"event":"http_request","http_status":200,"level":"info",
 "method":"POST","outcome":"ok","route":"/api/v1/workflows/:id/analyze","timestamp":"...","trace_id":"4f62a979"}
```

Any key outside the allowlist is dropped and only its count is recorded as `dropped_fields`. Strings are
truncated to 200 characters and non-finite numbers are dropped. Consequently the following **cannot** reach a log
line: source document text, prompts, model output, reviewer names, session tokens, file paths and provider
response bodies. `tests/unit/test_observability.py` asserts this.

Identifiers are allowed on purpose: `workflow_id`, `run_id`, `proposal_id`, `index_id`, `batch_id` and content
hashes are correlation keys, not content.

## Traces and spans

`factory/observability/tracing.py` creates one trace per HTTP request and per instrumented CLI run, using
`contextvars` so each `ThreadingHTTPServer` thread stays isolated. Nested spans record their own duration,
`outcome` (`ok`/`error`), the exception class and, for a classified provider failure, its `kind` — never the
exception message.

Instrumented spans today:

| Span | Component | Where |
| --- | --- | --- |
| `http_request` | transport | every GET/POST, including rejected requests |
| `workflow_<action>` | service | analyze, start-review, review, finalize, execute, evidence, … |
| `coverage_measure`, `quality_gate_evaluate`, `mutation_analyze` | service | the expensive read paths |
| `extraction_propose`, `suggestion_propose` | service | around the provider call only |
| `ollama_chat`, `ollama_embed`, `http_sut_execute` | provider / sut | transport time alone |

Span depth is capped at 16. Every response carries the trace in an `X-Trace-Id` header, and every JSON error body
repeats it as `trace_id`, so a message in the browser can be tied to the server-side records.

## Metrics

`factory/observability/metrics.py` keeps process-local counters and duration histograms behind one lock.

- Labels are restricted to a fixed allowlist (`component`, `operation`, `route`, `method`, `status`, `outcome`,
  `kind`, `provider`, `backend`). A caller cannot turn a workflow id or a reviewer name into a dimension.
- Label values must be short and match a safe character set, otherwise they become `invalid`.
- Request paths are reduced to a route template before use: `/api/v1/workflows/<uuid>/runs/<uuid>` becomes
  `/api/v1/workflows/:id/runs/:id`.
- The registry is capped at 256 series; anything beyond that is refused and reported as `dropped_series`.
- Histograms use fixed millisecond buckets, so reported quantiles are **bucket upper bounds**, not exact values.

Recorded today: `http_responses_total`, `http_request_duration_ms`, `span_duration_ms`, `span_errors_total`,
`db_transactions_total`, `db_transaction_duration_ms`, `db_reads_total`, `db_read_duration_ms`,
`provider_calls_total`, `provider_failures_total`, `extraction_failures_total`.

Durations are host wall-clock times that include cold model loading and disk latency. They describe this run on
this machine and are not a quality or performance claim.

## Classified provider failures

`ProviderError` now carries a `kind` and a static `remediation` hint. `factory/providers/failure.py` maps a
transport exception to exactly one kind and never copies the provider payload, URL or credentials into the message.

| Kind | Typical cause |
| --- | --- |
| `unreachable` | service not running, connection refused, DNS/socket error |
| `timeout` | socket timeout on chat, embedding or SUT call |
| `http_status` | provider answered with a non-2xx status (the code is kept, the body is not) |
| `oversized_response` | bounded read limit exceeded (256 KiB chat, 4 MiB embedding batch, 64 KiB SUT) |
| `malformed_json` | body was not a single valid JSON document |
| `schema_rejected` | JSON parsed but violated the required contract (`done`, row counts, vector shape) |
| `model_mismatch` | the response model differs from the configured tag |
| `capability_unsupported` | tool calls or an operation the selected model does not support |
| `redirect_blocked` | a redirect was attempted; redirects are disabled by design |
| `invalid_request` | the host refused to send the request |
| `unclassified` | anything not matched above |

The HTTP layer answers `502` with `{"error", "kind", "remediation", "retried": false, "fallback_used": false,
"trace_id"}`. The browser renders the kind and the remediation under the error message.

**The guarantee is unchanged and tested:** no automatic retry, no automatic fallback to mock, no output repair
and no automatic approval. `CountingFailureProvider` in `tests/integration/test_diagnostics.py` asserts that a
failing provider is called exactly once.

`POST /api/v1/extract` deliberately still answers `200` with `status="provider_error"`: the proposal is a durable
artifact that records the attempt. Its `issues[0]` now names the kind and the remediation, so the failure is no
longer anonymous.

## Inspecting a run

`GET /api/v1/diagnostics` (loopback, same Host/Origin checks as every other route) returns configured providers,
the effective configuration with secrets reported only as `set`/`unset`, optional-dependency availability, the
database path/migrations/writability, the logging configuration and the metrics snapshot.

In the browser: **Overview → Run diagnostics → Inspect this run**.

## Demo packaging

```powershell
py -3 -B scripts/run_demo.py --check            # preflight only
py -3 -B scripts/run_demo.py --seed             # preflight, create missing fixtures, start the workspace
py -3 -B scripts/run_demo.py --reset-database   # discard the selected database first
py -3 -B scripts/run_demo.py --profile data/ai_profiles/ollama.local.json
```

The preflight reports Python version, database directory writability, port availability, database state, optional
dependencies and demo fixtures. A `FAIL` row exits with code 2 and installs, downloads and deletes nothing.
`--reset-database` refuses any path outside the project `data/` directory and is never implied by another flag.

`WorkspaceServer` now sets `allow_reuse_address=False`, so a second demo process on the same port fails with a
clear message instead of silently sharing the socket.

## Limits

- Metrics live in one process. Restarting the workspace loses them; nothing is written to disk.
- Quantiles are bucket upper bounds, and the maximum bucket is 30 s — slower calls only report `> 30000`.
- There is no OpenTelemetry export, no log rotation, no sampling and no alerting.
- Logs are diagnostics, not an audit trail. The audit record remains `wf_events` plus the evidence pack.
- The legacy `/legacy` surface keeps its original behaviour and is not instrumented beyond the request span.
- SHA-256 values in logs are integrity fingerprints, not signatures.
