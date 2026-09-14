# Cập nhật: testcase và luật là hai đầu vào độc lập

Luồng giao diện hiện hành: **Test cases → Rules → Compare & review → Run & evidence**. File testcase XLSX/CSV không chứa luật hoặc rule_ids. Nhập luật bằng văn bản; chọn Pattern hoặc AI provider; xác nhận trước khi so sánh.

[Xem hướng dẫn và API đầy đủ](vi/LUONG-TESTCASE-DOC-LAP.md). Template workbook V1/V2 và các ví dụ phase cũ bên dưới dành cho **Overview → Advanced** hoặc CLI; không phải yêu cầu của import testcase thuần.

# Phase 8 — Unified API and browser workspace

## Start and storage

Run from the project root:

```powershell
python -B -m factory.server
# Open an existing phase 4–7 database on another port:
python -B -m factory.server --db data/retrieval-demo.db --port 8001
```

The default URL is http://127.0.0.1:8000 and the default database is data/workspace.db. Use an explicit --db to view CLI-generated records. The server does not merge databases or load demo records automatically. Relative database paths resolve against your working directory.

The root page is web/workspace.html, with external workspace.js and workspace.css. The previous UI remains at /legacy and uses data/factory.db. Versioned /api/v1 routes operate on the typed database configured at startup.

## Screens

| Screen | Purpose |
| --- | --- |
| Overview | Latest 100 workflows, review/evidence counts and actual configured provider names |
| Document intake | Synthetic draft or JSON/XLSX upload with optional Excel mapping |
| AI rule review | Two source versions, extraction proposal, citations, explicit approve/reject and separate promotion |
| Test workspace | Versioned rule snapshots, delta/impact/gap analysis, coverage, candidate inputs, reviews and edits |
| Knowledge & reuse | Explicit source selection, immutable corpus, hybrid search, grounded batches and pending attachment |
| Run & evidence | Independent mock configuration, execution results, executed coverage, mutation report, source/evidence downloads and audit history |

Enter a reviewer identity before changing data. It is recorded in history but is not authenticated. Select a workflow using the header or a workflow row. On a revision conflict, refresh and inspect the latest state before retrying; mutations are never automatically retried.

## Review sequence

Draft → Analyze & generate → Open test review → Inspect each candidate → Select intended tests → Record a decision and reason → Finalize review → Execute approved tests → Create evidence pack.

Selection is empty by default. Approve selected, Reject selected and Request changes apply atomically to 1–200 selected current test revisions. If any selection is stale or invalid, none of the decisions are committed. Finalization requires a current decision for every test, no unresolved changes, and at least one approved test.

Inspect / edit opens the typed test JSON and provenance. Edits create a new revision and invalidate its previous approval. Money values retain the typed decimal envelope. Invalid or unsupported data is rejected by the existing service validators.

The advanced rule editor accepts the full typed table and rules. Preserve the table ID, increase the version, and keep row content and rule references consistent. RuleReference.rule_hash must equal factory.models.content_hash(rule). Source citations must remain valid against archived bytes. A saved rule revision resets analysis and test approvals; it is not a shortcut around review.

## Extraction and retrieval

Load one of the Japanese synthetic pairs to exercise the offline mock. Unknown source text may require clarification. The UI exposes raw source versions, exact citations, validation issues, provider/model and simulation labels. An approved rule proposal still requires a separate promotion action to create a draft workflow.

A corpus may contain current approved tests; rule records require the phase-6 reviewed promotion proof. Reviewed tests alone do not imply reviewed rules. Select source workflows and build an index explicitly. Search revalidates source approval freshness.

Propose tests for the active target workflow, inspect the stored batch and attach it explicitly. Attachment targets the batch's recorded workflow and revision, even if the active selector has changed. The resulting candidates remain unapproved. Zero candidates can be a valid outcome after deduplication; they are not presented as additional coverage.

For a prepared retrieval scenario, use scripts/run_retrieval_demo.py and open its database with --db data/retrieval-demo.db. Its corpus approvals are labeled synthetic; they are not real SME decisions.

## Execution and evidence

The web SUT is an independent insurance mock. Set its profile, numeric configuration and injected fault explicitly. Defaults model eligibility 18–65, claim threshold 150,000,000 VND and deductible 10,000,000 VND. These are deployment settings, not values inferred from imported rules. Custom rules can correctly reveal mismatches against these defaults.

Only finalized approved workflows execute. The API rejects client-supplied expected results and rule snapshots on execution requests.

Designed coverage considers current candidate inputs. Run coverage is calculated from the archived approved workflow revision and the run journal; PASS and FAIL exercise inputs, ERROR and SKIPPED do not. A later workflow edit does not change the old run's coverage.

Evidence JSON contains the rule/table, approved test and decision snapshots, expected/actual results and provenance. Coverage is a separate derived API report, not a field added to the evidence hash contract. Downloaded bytes are the original canonical Evidence serialization; the server validates stored integrity.

To verify a downloaded pack:

```python
from pathlib import Path
from factory.models import Evidence
evidence = Evidence.from_json(Path("downloaded-evidence.json").read_text(encoding="utf-8"))
print(evidence.fingerprint)
```

Compare the fingerprint with the value shown when the pack was created. Source downloads also verify hashes. Audit history records revision, actor, action, reason and timestamp.

Reopen review before another completed run; approvals must be recorded again. Recover interrupted run is an explicit reconciliation action for an active/unreconciled journal; inspect history first.

## Local operating limits

No production login, RBAC, signing, background job queue or live-model performance claims are included. Requests execute synchronously in server threads. Provider selection is server-owned process configuration. The session token prevents cross-site browser writes but is not an authenticated user identity.

Versioned JSON requests are capped at 16 MiB, source imports at 10 MiB, and extraction text at 64 KiB/1,000 lines per version. Other domain/provider bounds from prior phases still apply. Keep this loopback workspace for local development.

The old /api routes remain for /legacy compatibility. Their contracts are separate from /api/v1 and do not provide typed workflow guarantees.

## Verification

```powershell
python -B -m unittest discover -s tests -v
python -m pip install --user -r requirements-browser.txt
python -m playwright install chromium
python -B scripts/check_workspace_browser.py
```

HTTP integration tests use ephemeral loopback servers and temporary SQLite files. The browser check verifies explicit review, execution, evidence download, reload persistence, responsive layout and escaped audit content. Screenshots are written to data/generated/phase8-desktop.png and phase8-mobile.png.
