# Hướng dẫn luồng testcase độc lập

## Khởi động

Chạy trong thư mục `E:\AI hackathon\rule2test`:

```powershell
python -B scripts/run_demo.py --seed
```

Nếu muốn dùng Ollama đã cấu hình, thay lệnh trên bằng:

```powershell
python -B scripts/run_demo.py --seed --profile data/ai_profiles/ollama-cloud.local.json
```

Mở http://localhost:8000. Nhập Reviewer identity. Không cần reset database; khởi động lại server và tải lại trang sau khi cập nhật code.

## 1. Test cases

Upload file `.xlsx` hoặc CSV UTF-8, tối đa 10 MiB. File chỉ cần chứa testcase, không chứa luật, policy hoặc rule_ids. Các cột thường gặp: Test Case ID, Title, Preconditions, Steps, Test Data, Expected Result.

Chọn **Inspect file**, chọn sheet, xác nhận dòng tiêu đề và ánh xạ cột. Mapping dùng chữ cột A/B/C…; bắt buộc Expected và ít nhất một cột Test Data/Title/Steps. Chọn **Preview interpretation**. Bộ đọc pattern nhận diện tuổi, số tiền, expected thông dụng; chưa phải AI diễn giải testcase tổng quát.

Kiểm tra nội dung gốc và diễn giải cạnh nhau. Dòng mơ hồ phải **Edit** rồi **Stage correction**, hoặc **Skip**. Form sửa hỗ trợ tuổi, số tiền, currency, expected; `empty`, `missing` và chuỗi trong dấu nháy dùng cho exception. Sau cùng chọn **Save test suite**. File và ô nguồn được lưu nguyên bản. Load demo example chỉ điền dữ liệu mẫu, không tạo workflow hoặc duyệt thay người dùng.

## 2. Rules

Gõ luật hiện tại và luật mới riêng biệt. Có thể để trống Current rule nếu không biết baseline; khi đó chỉ kiểm tra testcase phù hợp luật mới, không kết luận lịch sử thay đổi.

Chọn **Pattern** cho bộ đọc offline, hoặc **AI provider** để gọi provider cấu hình lúc khởi động. Provider mock được ghi rõ là mô phỏng. Không có tự động fallback. Pattern hỗ trợ ba dạng câu nghiệp vụ (khoảng tuổi, ngưỡng bồi thường, khấu trừ) với giá trị tự nhập; đây không phải giới hạn ở ba bộ số demo. Domain thực thi vẫn giới hạn tuổi và số tiền. Luật ngoài domain cần mở rộng engine/schema; chọn AI không tự loại bỏ giới hạn này.

Chọn **Interpret rules**, kiểm tra điều kiện, default outcome và trích dẫn nguồn. Ghi lý do rồi **Confirm rules** hoặc **Reject rules**. Nếu needs_clarification/invalid_output, sửa văn bản và tạo đề xuất mới.

## 3. Compare & review

Chọn suite đã lưu và luật đã xác nhận, nhấn **Compare**. Mỗi lần Compare tạo workflow mới. Bảng nhóm đề xuất Keep/Change/Add/Check hiển thị input, expected trước/sau, lý do và nguồn. Not linked liệt kê các dòng bị skip, chưa xác nhận hoặc không liên quan.

Ví dụ luật tuổi 18–60 đổi thành 18–65: TC001 tuổi 60 giữ ALLOW; TC002 tuổi 61 đổi DENY → ALLOW; bổ sung boundary quanh 65. Bản suite gốc không bị ghi đè.

Kiểm tra từng đề xuất, tick chọn và nhập Test review reason, rồi **Approve selected** hoặc **Reject selected**. Tất cả test hiện hành phải có quyết định trước **Finalize review**. Test đã sửa cần được duyệt lại. Các dòng không được liên kết không có nghĩa là đã được kiểm thử; xem riêng danh sách này khi đánh giá coverage.

## 4. Run & evidence

Mock SUT được điền cấu hình gợi ý từ luật mới khi chọn workflow. Có thể sửa cấu hình triển khai và Injected fault trước khi chạy. Đây là kiểm thử mock; cấu hình sinh từ luật không chứng minh hệ thống bảo hiểm thật đã triển khai đúng. Nghiệp vụ thực tế cần adapter tới SUT độc lập.

Chọn **Execute approved tests → Create evidence pack → Evaluate current revision**. Xem PASS/FAIL và tải evidence JSON, nguồn gốc và báo cáo gate. Muốn demo lỗi: Reopen review, duyệt/finalize lại, chọn Boundary, chạy lại, tạo evidence mới rồi đánh giá gate. GO/NO-GO chỉ áp dụng snapshot hiện hành.

## API đầu vào độc lập

Các POST yêu cầu session CSRF như API workspace hiện có.

| Endpoint | Payload/nội dung |
|---|---|
| POST `/api/v1/suites/inspect` | filename, content_base64 → sheets, headers, suggested mapping |
| POST `/api/v1/suites/preview` | file + sheet, mapping, header_row tùy chọn → rows, questions |
| POST `/api/v1/suites` | như preview + actor, resolutions tùy chọn → suite đã lưu |
| GET `/api/v1/suites` | Danh sách suite |
| GET `/api/v1/suites/{id}` | Suite và nguồn ô |
| GET `/api/v1/suites/{id}/source` | File gốc |
| POST `/api/v1/extract` | sources (v1+v2 hoặc chỉ v2), actor, engine: pattern/provider |
| POST `/api/v1/proposals/{id}/review` | proposal_hash, decision: approved/rejected, reason, actor |
| POST `/api/v1/suites/{id}/link` | proposal_id, proposal_hash, actor → workflow IN_REVIEW |
| GET `/api/v1/workflows/{id}` | workflow, proposal nhóm đề xuất, excluded, sut_suggestion, link, suite |

Mapping ví dụ: `{"test_id":"A","title":"B","test_data":"E","expected":"F"}`.
Resolution ví dụ: `{"row_number":6,"inputs":[{"field":"age","value":"70"}],"expected":{"outcome":"deny"}}`; hoặc `{"row_number":6,"skip":true}`.

Import workbook tổng hợp V1/V2 cũ vẫn ở **Overview → Advanced**, dành cho template có cấu trúc. Không dùng template đó để mô tả yêu cầu của file testcase thuần.
