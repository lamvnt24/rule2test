# Trạng thái triển khai — testcase và luật độc lập

Cập nhật: 2026-09-14. Đã hoàn tất các đầu việc tiếp nối trong bản status trước: kiểm thử, giao diện, browser demo và tài liệu. Nội dung này được đưa vào commit cùng code; xem `git log -1` để lấy mã commit.

## Luồng hiện hành

**Test cases → Rules → Compare & review → Run & evidence**; Knowledge ở mục 06.

- File testcase thuần XLSX/CSV không cần luật hoặc rule_ids. Có inspect sheet/header, mapping cột, preview diễn giải và ô gốc, Edit/Skip rồi Save.
- Luật nhập riêng bằng văn bản: current + new, hoặc chỉ new. Chọn Pattern/AI provider. Load demo example chỉ điền mẫu, không tạo workflow cố định.
- Confirm/Reject rule proposal có hash và lý do. Compare chọn suite + confirmed proposal, tạo workflow mới IN_REVIEW.
- Bảng nhóm Keep/Change/Add/Check: expected trước/sau, lý do, trích dẫn luật và ô testcase. Not linked hiển thị các dòng bị loại cùng lý do.
- Người dùng duyệt mọi test hiện hành rồi Finalize; chạy SUT, lưu evidence, kiểm tra gate và tải nguồn/báo cáo.
- Cấu hình mock SUT được gợi ý khi chọn workflow, có thể chỉnh lại; không ghi đè chỉnh sửa sau mỗi lần refresh cùng workflow.
- Chỉ luật mới: hiển thị conformity check, không trình bày baseline nội bộ như luật lịch sử.
- Import workbook V1/V2 cũ ở Overview → Advanced. Không còn nút Create synthetic workflow trong luồng chính.

## Code và kiểm thử

Backend suite/archive/parser/interpreter/link đã có trước lượt tiếp nối. Đã bổ sung giao diện vào `web/workspace.html`, `web/workspace.js`, `web/workspace.css` và kiểm thử bổ sung; giữ lại bộ kiểm thử backend có sẵn.

Các lỗi đã sửa:

1. CSV có dòng trống làm lệch tọa độ ô nguồn: giữ dòng trống khi đọc, bỏ qua khi trích xuất nội dung.
2. CSV hoàn toàn rỗng phải bị từ chối.
3. API link suite trả thiếu suite_id/proposal_id: trả summary kèm link và suite.
4. CLI capture dùng đường dẫn tương đối bị lỗi khi in kết quả: resolve output trước khi sử dụng.
5. Test gọi engine trực tiếp cần chuyển chuỗi tiền JSON-safe thành Decimal theo contract constructor.

Kết quả xác minh:

- `python -B -m unittest discover -s tests -q`: **353 tests, OK**, 113.173 giây.
- `node --check web/workspace.js`: pass.
- Browser: import suite, nguồn E3, TC002 DENY → ALLOW, skip TC005, phê duyệt, execute, evidence, GO, download, reload và viewport mobile.
- Browser bổ sung: tự nhập giới hạn tuổi **72**, chỉ luật mới; hiển thị unknown baseline và mock max_age=72.
- `python -B scripts/capture_demo_screens.py --output data/generated/suite-demo-capture`: **11 frames**, gồm GO và Boundary fault → NO-GO.
- Replay: `data/generated/suite-demo-capture/replay.html`. Database của browser/capture nằm trong thư mục tạm; không thay database người dùng.

## Tài liệu và công cụ demo

- Hướng dẫn đầy đủ: `docs/vi/LUONG-TESTCASE-DOC-LAP.md` và `docs/vi/HUONG-DAN-SU-DUNG.md`.
- Cập nhật README, WORKSPACE, API, IMPORT_FORMAT, DEMO_FLOW, COMPETITION_DEMO. Hướng dẫn cũ giữ trong các file `*-LEGACY.md`.
- `scripts/suite_browser_flow.py`: luồng browser dùng chung cho test và capture.
- `scripts/check_workspace_browser.py`: chạy kiểm thử browser bằng database tạm.
- `scripts/build_demo_kit.py`: README kit hướng dẫn nhập testcase riêng; không gắn số test benchmark cũ vào bộ testcase mới.

## Giới hạn cần giữ rõ khi phát triển tiếp

- Diễn giải testcase và liên kết theo trường hiện dùng pattern/deterministic logic, không phải AI semantic mapping tổng quát.
- AI provider phục vụ trích xuất luật; không chạy đánh giá live Ollama trong lượt này. Mock/pattern được ghi rõ trên giao diện, không fallback ngầm.
- Domain executable vẫn là tuổi, số tiền yêu cầu và khấu trừ. Pattern nhận ba dạng nghiệp vụ với giá trị tùy nhập; chưa hỗ trợ mọi luật bảo hiểm tự do.
- Cấu hình mock gợi ý từ luật phục vụ demo; không chứng minh hệ thống thật triển khai đúng. Cần SUT độc lập cho kiểm thử thực tế.
- Suite unresolved có thể được API lưu và sẽ được liệt kê là Not linked; giao diện buộc xử lý Edit/Skip trước khi Save.
- Mỗi lần Compare tạo workflow mới; chưa có idempotency key cho yêu cầu link.

## Chạy lại

```powershell
cd "E:\AI hackathon\rule2test"
python -B scripts/run_demo.py --seed
# Hoặc với profile đã cấu hình:
python -B scripts/run_demo.py --seed --profile data/ai_profiles/ollama-cloud.local.json
```

Khởi động lại server cũ và tải lại trang để nhận giao diện mới. Không cần reset database.
