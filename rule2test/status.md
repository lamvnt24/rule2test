# Trạng thái công việc — tách import testcase và nhập luật (2026-09-14)

Ghi lại để tiếp tục nếu phiên làm việc bị gián đoạn. Mọi thứ dưới đây đang ở **working tree, chưa commit**.

## Mục tiêu (theo yêu cầu)

Hai đầu vào độc lập: **file testcase thuần** (Excel/CSV, không chứa luật, không `rule_ids`) và **luật do người dùng gõ** (luật hiện tại + luật mới, hoặc chỉ luật mới). Hệ thống tự tìm test bị ảnh hưởng, đề xuất **Giữ nguyên / Đổi expected (trước → sau) / Bổ sung / Cần kiểm tra** kèm lý do, trích dẫn luật và ô Excel; người dùng duyệt rồi chạy test và xuất evidence. Ba scenario demo chỉ còn ở mục "Load demo example". Giao diện tiếng Anh (như hiện tại), tài liệu tiếng Việt.

## Đã làm xong (backend) — đã chạy thử tay, pipeline chạy đúng ví dụ TC001/TC002/65/66

| Phần | File | Ghi chú |
|---|---|---|
| Migration 3 | `factory/repositories/connection.py` | bảng `wf_documents(scope, document_hash, metadata, data)` — archive file testcase trước khi có workflow |
| Archive theo scope | `factory/repositories/document_repository.py` | thêm `ArchiveRepository` (cùng contract, bảng khác) |
| Media type CSV | `factory/models/import_document.py` | thêm `text/csv` |
| Model suite | `factory/models/test_suite.py` | `SuiteColumn`, `SuiteCell`, `SuiteRow` (status ready/needs_confirmation/skipped, notes, questions), `TestSuite`, `ExcludedRow`, `SuiteLink` |
| Repo suite | `factory/repositories/suite_repository.py` | scope `suites`, kind `test_suite` / `suite_link` |
| Tiện ích text | `factory/services/text_patterns.py` | fold không dấu (giữ độ dài), đọc tiền VN/EN/JA (`100.000.000 VND`, `150 triệu`, `1,5 tỷ`), format câu (fmt_rule…) |
| Đọc testcase | `factory/services/testcase_interpreter.py` | "Tuổi: 61" → Age=61; "Bị từ chối" → DENY; "Chi trả 15.000.000 VND" → PAYOUT; null/missing/text; dòng mơ hồ → questions |
| Đọc câu luật | `factory/services/rule_interpreter.py` | 3 dạng: khoảng tuổi / ngưỡng xem xét / khấu trừ; VI, EN, JA (đọc đúng cả 3 fixture Nhật); trả về câu hỏi khi không rõ |
| Provider pattern | `factory/providers/llm/patterns.py` | `PatternRuleProvider` (name `pattern`) xuất đúng JSON contract + citation; thêm vào `factory.py` (`RULE2TEST_EXTRACTION_PROVIDER=pattern`) |
| Chỉ luật mới | `factory/models/extraction.py`, `validators/extraction_validator.py`, `providers/llm/prompt.py` (v3), `providers/llm/mock.py` | `ExtractionRequest` chấp nhận chỉ `v2`; `baseline_known` property; compile tự nhân bản v2 thành v1 (version 1) → không có delta |
| Parser file testcase | `factory/parsers/testcase_parser.py` | xlsx/csv, tìm header row, gợi ý mapping (header VI/EN), preview, `extract_rows` giữ ô gốc; `open_workbook` tách ra từ `excel_parser.py` |
| Mẫu demo | `factory/parsers/testcase_samples.py` | 3 bộ testcase VI (dòng 5 cố ý mơ hồ), 3 cặp câu luật VI, `rule_examples()` gộp cả cặp JA |
| Suite service | `factory/services/suite_service.py` | inspect / preview / create (áp `resolutions` của người dùng: skip hoặc sửa input+expected) / list / get / source |
| Link service | `factory/services/link_service.py` | suite + proposal đã approve → workflow (existing tests = dòng ready & liên quan), archive đủ nguồn, ghi promotion + `SuiteLink`, rồi analyze + start_review |
| Đề xuất sửa | `factory/services/change_proposal_service.py` | `build()` → rows keep/change/add/check theo nhóm (affected/boundary/coverage/robustness/unchanged), lý do bằng câu, trích dẫn luật + ô Excel; `suggest_sut()` tự cấu hình mock SUT từ luật mới |
| Routes | `factory/api/routes/suites.py`, `workspace.py`, `server.py` | GET `/suites`, `/suites/{id}`, `/suites/{id}/source`, `/suites/samples/{profile}`, `/rules/examples`; POST `/suites/inspect`, `/suites/preview`, `/suites`, `/suites/{id}/link`; `/extract` thêm `engine: pattern|provider`, `existing_tests_json` optional; GET workflow thêm `proposal`, `sut_suggestion`, `link`, `suite`; GET proposal thêm `compiled` |
| Test cũ | `tests/integration/test_diagnostics.py`, `test_import_workflow.py`, `test_workflow_persistence.py` | sửa số migration 2 → 3 |

Bộ test hiện tại: **294 pass** sau khi sửa 3 assertion migration (chạy `py -3 -B -m unittest discover -s tests`).

## Còn phải làm (theo thứ tự)

1. **Test mới**: `tests/unit/test_testcase_interpreter.py`, `test_rule_interpreter.py`, `test_testcase_parser.py`; `tests/integration/test_suite_workflow.py` (suite → link → proposal → review → execute → evidence, cả chế độ chỉ-luật-mới); thêm case API vào `test_workspace_api.py`.
2. **UI** `web/workspace.html` + `web/workspace.js` (+ css): nav 01 Overview → 02 Test cases → 03 Rules → 04 Compare & review → 05 Run & evidence → 06 Knowledge; trang Test cases (chọn file / Load demo example → chọn sheet & mapping → bảng diễn giải, Edit/Skip dòng chưa rõ → Save); trang Rules (2 ô text, Load demo example, chọn Pattern/AI provider, hiển thị rule dạng câu + "what changed", Confirm/Reject); trang Compare & review (chọn suite + rules → Compare → bảng đề xuất theo nhóm, tick duyệt, Finalize; bảng "Not linked"); Run page tự điền SUT từ `sut_suggestion`; bỏ "Create synthetic workflow", template JSON/XLSX cũ đưa vào Advanced ở Overview; flow strip 5 bước theo trạng thái mới.
3. **Playwright**: viết lại `tests/integration/test_workspace_rendering.py` theo luồng mới; cập nhật `scripts/check_workspace_browser.py`, `scripts/capture_demo_screens.py`.
4. **Docs**: README, `docs/WORKSPACE.md`, `docs/API.md`, `docs/IMPORT_FORMAT.md` (mục file testcase), `docs/DEMO_FLOW.md`, `docs/COMPETITION_DEMO.md`, `docs/vi/HUONG-DAN-SU-DUNG.md`; `scripts/build_demo_kit.py` (đoạn README "Document intake → Create synthetic workflow").
5. Chạy lại toàn bộ test, rồi commit.

## Cách kiểm tra nhanh backend (không cần UI)

```powershell
$env:PYTHONIOENCODING="utf-8"; $env:PYTHONPATH="D:\project\rule2test\rule2test"
py -3 - <<'EOF'
# xem scratch script đã dùng: inspect sample → preview → create (skip dòng 6) → pattern proposal → approve → link → build()
EOF
```
Kết quả mong đợi với mẫu eligibility: TC001 keep, TC002 change DENY→ALLOW ("Age ≤ 60 became Age ≤ 65"), thêm test tại 64/65/66 ("new limit"), robustness (empty/missing/text/negative/overflow), TC005 excluded (skipped).
