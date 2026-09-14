# Cập nhật: testcase và luật là hai đầu vào độc lập

Luồng giao diện hiện hành: **Test cases → Rules → Compare & review → Run & evidence**. File testcase XLSX/CSV không chứa luật hoặc rule_ids. Nhập luật bằng văn bản; chọn Pattern hoặc AI provider; xác nhận trước khi so sánh.

[Xem hướng dẫn và API đầy đủ](vi/LUONG-TESTCASE-DOC-LAP.md). Template workbook V1/V2 và các ví dụ phase cũ bên dưới dành cho **Overview → Advanced** hoặc CLI; không phải yêu cầu của import testcase thuần.

# REST API

Transport: factory/server.py, Python standard-library HTTP. Routing: factory/api/routes/workspace.py. Application dependencies: factory/api/dependencies.py. Services retain business validation and SQLite transactions. FastAPI is not required.

## Versioned local API

Fetch GET /api/v1/session first. It returns csrf_token, configured providers and api_version. Every versioned POST requires Content-Type: application/json and X-CSRF-Token with that token. Browser requests must use the same loopback origin. No CORS or authenticated roles are provided.

Unknown body fields are rejected. Domain objects use their Model.to_dict representation: decimals are {"$decimal":"..."}, dates are {"$date":"..."}, and datetimes are {"$datetime":"..."}. Top-level revise-rules.as_of uses an ISO date string or null. Supply the current integer revision on every workflow action.

### Collections and inspection

| Method | Path after /api/v1 | Response |
| --- | --- | --- |
| GET | /session | Token and provider transparency |
| GET | /workflows | Latest 100 summaries |
| GET | /workflows/{id} | workflow snapshot, summary and designed coverage |
| GET | /workflows/{id}/history | Ordered audit events |
| GET | /workflows/{id}/mutation | Read-only specification mutation report and score |
| GET | /workflows/{id}/runs/{run} | ExecutionRun fields plus derived executed coverage from its archived revision |
| GET | /workflows/{id}/evidence/{evidence} | Verified canonical evidence JSON download |
| GET | /workflows/{id}/sources/{sha256} | Verified original source-byte download |
| GET | /proposals | Latest 100 proposal summaries |
| GET | /proposals/{id} | Summary/hash, raw proposal, parsed reviewable output and stored review |
| GET | /indexes | Latest 100 corpus summaries |
| GET | /batches | Latest 100 batch summaries |
| GET | /batches/{id} | Stored batch and batch_hash |
| GET | /samples/{profile} | Synthetic Japanese v1/v2 and existing test array |

Profiles: eligibility, claim_review, deductible. Collections are bounded summaries, not a full pagination API.

### Intake, extraction and knowledge

| POST path after /api/v1 | Required JSON fields | Optional fields |
| --- | --- | --- |
| /demo | profile, actor | — |
| /import | filename, content_base64, actor | mapping |
| /extract | sources, existing_tests_json, actor | timeout |
| /proposals/{id}/review | proposal_hash, decision, reason, actor | — |
| /proposals/{id}/promote | proposal_hash, actor | — |
| /indexes | workflow_ids, actor | — |
| /search | index_id, query | fields, rule_ids, kind, workflow_ids, top_k |
| /suggestions | workflow_id, revision, index_id, query, actor | timeout |
| /batches/{id}/attach | batch_hash, actor | — |

Import content is base64 of source bytes, up to 10 MiB. Mapping follows [IMPORT_FORMAT.md](IMPORT_FORMAT.md). Each extraction source has document_id, label (v1/v2) and text. existing_tests_json is a string containing the structured import-format test array. Review decision is approved or rejected. Promotion and batch attachment are separate explicit mutations.

### Workflow commands

All paths below begin /api/v1/workflows/{id}/ and require revision and actor in addition to listed fields.

| POST action | Additional required fields | Result |
| --- | --- | --- |
| analyze | — | Workflow summary |
| start-review | — | Workflow summary |
| review | tests, decision, reason | Atomic decisions and workflow summary |
| finalize | reason | Approved workflow summary |
| edit-test | test_id, test_revision, inputs, expected, title, reason | New test revision and workflow summary |
| revise-rules | table, rules, as_of, reason | New draft summary |
| execute | sut | workflow summary and run |
| evidence | — | workflow summary, evidence_id, evidence_hash |
| reopen-review | reason | Workflow summary |
| recover | reason | Reconciled workflow summary |

Review tests is an array of exact {"test_id":"...","revision":1} pairs, 1–200 unique IDs. Decision is approved, rejected or changes_requested. All selections are validated before one commit. Finalization never invents missing decisions.

SUT configuration has exactly these fields:

```json
{
  "profile": "eligibility",
  "fault": "none",
  "min_age": 18,
  "max_age": 65,
  "claim_threshold": "150000000",
  "deductible": "10000000",
  "currency": "VND"
}
```

Faults: none, boundary, stale, deductible_off_by_one. Monetary settings use plain decimal strings. Expected outcomes and rules are not accepted on execute. Configuration is checked by the independent mock adapter.

### PowerShell example

```powershell
$rule2testBase = "http://127.0.0.1:8000/api/v1"
$rule2testSession = Invoke-RestMethod "$rule2testBase/session"
$rule2testHeaders = @{"X-CSRF-Token"=$rule2testSession.csrf_token}
$rule2testBody = @{profile="eligibility"; actor="QA"} | ConvertTo-Json
$rule2testWorkflow = Invoke-RestMethod "$rule2testBase/demo" -Method Post -Headers $rule2testHeaders -ContentType "application/json" -Body $rule2testBody
Invoke-RestMethod "$rule2testBase/workflows/$($rule2testWorkflow.workflow_id)"
```

### Errors and guarantees

Errors return {"error":"..."}, with issues for located import diagnostics. Statuses: 400 invalid input, 403 origin/host/token denied, 404 missing resource, 409 stale revision/state, 413 body size, 415 media type, 502 provider failure, 503 unavailable/invalid configuration, 500 unexpected server failure.

The browser shows failures without automatically retrying mutations. Reload after a 409 and inspect the current revision. A lost response does not imply rollback; inspect persisted history before retrying creation or other mutations.

SHA-256 verifies stored content integrity. It is not a digital signature. The session token and loopback controls are local browser protections, not authentication.

## Legacy API

The old UI is available at /legacy; these routes use the original dictionary workflow and data/factory.db.

| Method | Path | Input |
| --- | --- | --- |
| GET | /api/health | none |
| GET | /api/demo | none |
| POST | /api/extract | text; optional legacy OLLAMA_MODEL environment |
| POST | /api/analyze | old, new, existing |
| POST | /api/run | plan_id, approved_ids, reviewer, fault |
| GET | /api/evidence/{id} | evidence ID |

Legacy input: data/demo.json. Do not mix legacy plans/evidence with typed /api/v1 workflow objects.


## Phase 9 quality gate

GET /api/v1/workflows/{id}/quality-gate returns a versioned GO/NO-GO report with individual checks, metrics, explicit unmeasured KPIs and snapshot hashes. GET /api/v1/workflows/{id}/quality-gate-report downloads canonical JSON. Both are read-only and evaluate the current workflow revision.

A valid NO-GO is HTTP 200, since the assessment succeeded. Integrity validation errors remain HTTP 400 and do not return a misleading gate verdict. See [QUALITY_GATE.md](QUALITY_GATE.md).


## Phase 10 AI diagnostics

GET /api/v1/ai-status returns configured role/provider names, model tags and local Ollama inventory/readiness. It uses bounded metadata requests and does not trigger inference, downloads or provider switching. A missing service is returned as a diagnostic result, not a successful live-readiness claim.

The optional profile launcher propagates RULE2TEST_AI_TIMEOUT_SECONDS (1–120). Extraction/suggestion requests may provide their existing explicit timeout override; otherwise this configured default is used. See [LIVE_AI.md](LIVE_AI.md).
