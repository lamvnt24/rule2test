# Phase 5: structured document import

Phase 5 converts reviewed JSON tables or an XLSX workbook into the typed phase-4 workflow. It preserves the original document bytes, SHA-256, source quotes and cell/JSON Pointer locations. Import creates DRAFT; analysis proposes tests, and QA reviews them before execution.

This parser handles an explicit table format. It does not infer rules from an arbitrary Japanese BD spreadsheet. Japanese quotes and manually mapped Japanese column headers are supported. General document interpretation belongs to the AI provider phase.

## Setup and first run

Run all commands from the project root:

```powershell
Set-Location -LiteralPath "E:\AI hackathon\rule2test"
python -m pip install --user -r requirements-excel.txt
python -B scripts/seed_demo.py
python -B scripts/import_documents.py validate data/demo/eligibility.xlsx
python -B scripts/run_import_demo.py
```

The import demo stops at IN_REVIEW and prints the workflow ID, revision, pending tests and an archived source reference. It persists to data/import-demo.db. It does not manufacture reviewer decisions.

JSON import, engines and the legacy web demo require no third-party dependencies. XLSX import and fixture generation require openpyxl and defusedxml. Tests explicitly skip XLSX cases when these optional packages are unavailable.

## Files and responsibilities

| Component | Responsibility |
| --- | --- |
| factory/parsers/json_parser.py | Strict UTF-8 JSON, duplicate-key rejection, exact row schema and JSON Pointers |
| factory/parsers/excel_parser.py | XLSX limits, sheets, headers, mapping and cell diagnostics |
| factory/parsers/_builder.py | Shared conversion into typed values, rules, tables and existing tests |
| factory/parsers/schema.py | Canonical columns and import schema version |
| factory/parsers/templates.py | Three independent synthetic scenarios and literal-only workbook output |
| factory/models/import_document.py | Document name, media type, byte length and SHA-256 |
| factory/repositories/document_repository.py | Exact source-byte archive and integrity verification |
| factory/services/import_service.py | Parse before transaction, create workflow and retrieve archived source |
| scripts/import_documents.py | Validate, create and recover a source file |
| scripts/seed_demo.py / reset_demo.py | Create or restore only the six known fixture files |

## Workbook contract

Required sheets: Manifest, Policies, RulesV1, RulesV2, Tests. Optional sheet: Guide, containing explanatory text only.

All columns listed below are required, including columns whose values may be blank. Column order may change. Headers are trimmed and matched case-insensitively, except Manifest's exact key/value headers. Unknown columns and sheets are rejected. Every populated row is validated, including hidden rows. Fully empty rows are ignored; partial rows are errors.

### Manifest

Two columns: key, value. Exactly three entries:

| Key | Example | Meaning |
| --- | --- | --- |
| schema_version | 1 | Supported import format |
| created_at | 2020-01-01T00:00:00+00:00 | Declared source snapshot timestamp, including timezone |
| created_by | Synthetic Rule2Test fixture | Source author label |

Keep created_at as text. The workflow separately records the importing actor and actual import time. Declared source metadata does not authenticate its author.

### Policies

Columns: label, table_id, version, hit_policy, default_outcome, default_amount, default_deductible, currency, as_of.

Exactly two rows with label v1 and v2. Supported hit policies are unique and first. The default outcome is used when no row matches. A payout default requires exactly one of default_amount or default_deductible, plus currency.

Supply as_of when any rule has effective_from. It is a date, independent of the document's created_at. A changed table retaining its ID must increase version.

### RulesV1 and RulesV2

Columns: rule_id, version, title, field, operator, value_type, value, currency, outcome, payout_amount, deductible, effective_from, effective_to, quote.

Rows with the same rule_id form an AND conjunction. Repeat version, title, action and effective dates identically; there is no implicit fill-down. Each condition retains its own quote cell. Rule order follows first appearance, which matters for first hit policy.

Supported business fields are age and claim_amount. Rule age thresholds are integers in 0..120. Money thresholds are in 0..1,000,000,000 with at most 12 fractional decimal places. Ordered comparisons use eq, ne, lt, le, gt, ge. For is_null or is_missing, value_type must be null or missing and value must be blank.

Outcomes are allow, deny, review, invalid, payout. For payout, supply exactly one of payout_amount or deductible. Deductible means max(claim_amount - deductible, 0), implemented by the typed engine. Formula text is never executed.

Rule snapshot hashes include provenance. A V2 row has a different source location from V1 even if its conditions are unchanged; increase its version accordingly. The delta service separately identifies semantic changes. Re-importing identical bytes under the same filename produces identical source/rule snapshots but a new workflow ID.

### Tests

Columns: test_id, revision, title, inputs_json, expected_outcome, expected_amount, currency, rule_ids, kind, rationale.

inputs_json is a JSON array stored as text in XLSX. Each entry contains exactly field, kind, value and currency:

```json
[{"field":"age","kind":"integer","value":61,"currency":null}]
```

For money, use kind money, a plain decimal string and a currency such as VND. Null and missing use value null. Typed invalid business inputs (negative age, text instead of age) may be imported for exception tests. Unknown business fields are rejected.

rule_ids is a comma-separated list of V1 rule IDs. Tests have origin existing. Expected values describe V1 and are not automatically approved or silently changed by import. Analysis creates new revision proposals against V2. kind is positive, negative, boundary or exception. A payout expected result must be a concrete expected_amount, not a deductible formula.

## JSON format

Use the same rows as the workbook in a single object with exactly these top-level fields:

```text
schema_version, created_at, created_by,
policies[], rules_v1[], rules_v2[], tests[]
```

Each array row has exactly the canonical columns for its corresponding sheet. Use null for blank values. inputs_json can be a native array or a JSON string. See the complete examples in data/demo/eligibility.json, claim_review.json and deductible.json.

This import format is separate from the legacy web DSL and the tagged Model.to_json() serialization used for persistence. Unknown fields, duplicate keys and NaN/Infinity are rejected.

## Money, dates and workbook behavior

- Prefer plain decimal text for all money: 100000000.25. Fractional numeric Excel cells are rejected to avoid binary floating-point ambiguity. Integer numeric cells are accepted; boolean, fraction and date cells are not accepted as integer thresholds.
- No thousands separators or exponent notation in money text. JSON fractional numbers are read as Decimal.
- Dates accept ISO YYYY-MM-DD strings or native Excel date cells. Datetime date cells must have no time component.
- Mixed currencies within a decision table are unsupported; no currency conversion is inferred.
- Formula cells, Excel error cells and merged data cells are rejected with their sheet and cell/range.
- Macros and external workbook links are rejected. Import does not evaluate formulas or fetch links.
- Limits: 10 MiB input, 2,000 ZIP parts, 50 MiB expanded archive, 5,000 data rows and 64 columns per data sheet. Up to 100 diagnostics are returned; no partial workflow is committed.

The loader uses data_only=False so formulas remain visible for rejection, and keep_links=False. These options are documented by [openpyxl's reader API](https://openpyxl.readthedocs.io/en/stable/api/openpyxl.reader.excel.html). The optional dependency includes defusedxml following [openpyxl's XML security guidance](https://openpyxl.readthedocs.io/en/stable/).

## Japanese column mapping

Keep canonical sheet names. Store this mapping as a UTF-8 JSON file and rename the relevant workbook headers:

```json
{
  "RulesV1": {"value": "閾値", "quote": "原文"},
  "RulesV2": {"value": "閾値", "quote": "原文"}
}
```

```powershell
python -B scripts/import_documents.py validate your-workbook.xlsx --mapping header-mapping.json
```

Mapping is explicit, not inferred. Duplicate mapped labels are rejected. Japanese quote text is preserved verbatim.

## Persistent workflow commands

```powershell
$created = python -B scripts/import_documents.py --db data/workflow.db create data/demo/eligibility.xlsx --actor BA | ConvertFrom-Json
$analyzed = python -B scripts/workflow_cli.py --db data/workflow.db analyze --workflow $created.workflow_id --revision $created.revision --actor BA | ConvertFrom-Json
$review = python -B scripts/workflow_cli.py --db data/workflow.db start-review --workflow $analyzed.workflow_id --revision $analyzed.revision --actor QA | ConvertFrom-Json
$review | ConvertTo-Json -Depth 20
```

Review, edit, finalize, execute and export evidence using the phase-4 commands in [WORKFLOWS.md](WORKFLOWS.md). Always use the latest revision. Import does not approve tests or invoke a SUT.

Recover the original imported bytes even after the working file was edited or removed:

```powershell
python -B scripts/import_documents.py --db data/workflow.db source --workflow $created.workflow_id --hash $created.documents[0].document_hash --output data/generated/recovered.xlsx
```

The output must not already exist. The repository checks the archived byte length and SHA-256 before returning it.

## Traceability and atomicity

SourceReference records document_id, document_hash, quote and either sheet/cell or json_pointer. Existing tests also retain their input source. Workflow.documents records archived document metadata.

Migration 2 adds wf_source_documents. Document bytes, workflow head, immutable snapshots and initial event are saved in one transaction. A failure rolls everything back. Parser failures happen before persistence; the CLI does not even create a database for invalid input.

New optional source fields are omitted when empty, preserving the serialization and hashes of pre-phase-5 snapshots. SHA-256 detects accidental changes; it is not a digital signature or protection against an administrator rewriting all data and hashes.

## Synthetic fixtures and reset

| Fixture | V1 -> V2 |
| --- | --- |
| eligibility | Maximum age 60 -> 65 |
| claim_review | Manual-review threshold 100M -> 150M VND |
| deductible | Deductible 5M -> 10M VND |

seed_demo.py creates missing files and preserves existing ones. reset_demo.py overwrites only these three JSON and three XLSX files, after checking target paths; it does not delete a directory or touch databases/evidence/custom files. Workbook packaging timestamps may change on regeneration, so raw document hashes may change. Previous imported bytes remain archived.

## Validation

```powershell
python -B -m unittest tests.unit.test_import_parsers tests.integration.test_import_workflow -v
python -B -m unittest discover -s tests -v
```

Coverage includes strict schemas, Japanese mapping, source locations, formula/merged-cell rejection, lossless money, effective dates, archived-source recovery, migration compatibility, rollback and workflow review state. General Japanese BD extraction accuracy is not measured by these tests.

The typed import currently runs through Python services and CLI. The legacy browser UI and Streamlit scaffold do not yet expose this workflow.
