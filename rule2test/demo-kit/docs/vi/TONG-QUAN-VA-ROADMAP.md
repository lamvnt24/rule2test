# Rule2Test — Tổng quan hệ thống và lộ trình

*Tài liệu này viết cho đồng đội và giám khảo: hiểu hệ thống làm gì, làm bằng cách nào, đang ở đâu và đi tiếp
thế nào. Hướng dẫn thao tác nằm ở [HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md).*

---

## 1. Vấn đề

Một công ty bảo hiểm sửa quy tắc nghiệp vụ — ví dụ tuổi được tham gia đổi từ **60 lên 65**. Sau khi sửa:

- Bộ test cũ **vẫn xanh**, vì chưa ai viết test cho vùng biên vừa dịch chuyển (tuổi 61–65).
- Không ai trả lời được **thay đổi này làm hỏng test nào**, ai đã duyệt test mới.
- Kết quả chạy test không truy ngược được về **điều khoản nào** trong tài liệu đã gây ra nó.
- Người duyệt bị yêu cầu tin vào bản tóm tắt của AI cho một tài liệu họ không kiểm tra lại được từng dòng.

Vấn đề cốt lõi **không phải là sinh test tự động**. Vấn đề là **truy vết và thẩm quyền**.

## 2. Giải pháp trong một câu

> Mỗi thay đổi quy tắc trở thành test hồi quy đã được người duyệt, và bằng chứng thực thi kiểm chứng lại được.

## 3. Nguyên tắc bất biến

Đây là phần quan trọng nhất của hệ thống. Mọi thứ khác chỉ là chi tiết triển khai.

| Nguyên tắc | Nghĩa là |
|---|---|
| **AI đề xuất** | AI đọc tài liệu và đề xuất quy tắc, đề xuất *đầu vào* test. Chỉ vậy. |
| **Engine quyết định** | Kết quả **mong đợi** do oracle kiểu tĩnh tính từ quy tắc đã duyệt. AI không bao giờ tính. |
| **Người duyệt** | Không có gì được duyệt tự động — không quy tắc, không test, không cả đề xuất của chính AI. |
| **Hai bên độc lập** | Kết quả **thực tế** do một hệ thống riêng (SUT) tính. SUT **không bao giờ** nhận kết quả mong đợi hay bản quy tắc. |
| **Không tự thử lại** | Provider lỗi thì báo lỗi có phân loại. Không retry ngầm, không âm thầm quay về mock, không "sửa" output. |
| **Trích dẫn đúng nguyên văn** | Mỗi quy tắc AI rút ra phải kèm **đúng dòng gốc**. Trích dẫn sai một ký tự là bị loại. |

Ba thứ cuối là lý do hệ thống này khác một công cụ "hỏi AI sinh test".

## 4. Kiến trúc

```
Trình duyệt (workspace.html/js/css)
        ↓  HTTP loopback, có session token, kiểm tra Host/Origin, CSP nghiêm ngặt
factory/server.py  →  factory/api/routes  (REST /api/v1)
        ↓
factory/services   (workflow, duyệt, bằng chứng, phân tích, AI, cổng chất lượng)
        ↓
factory/models     (hợp đồng bất biến, băm nội dung)
factory/engines    (oracle, mock bảo hiểm độc lập, bộ thực thi)
        ↓
factory/providers  (LLM, embedding, vector, SUT)   factory/repositories (SQLite append-only)
```

Phụ thuộc chỉ đi **một chiều xuống**. Engine không biết gì về HTTP. API không cài lại logic nghiệp vụ.
Tầng quan sát (`factory/observability`) vẽ bằng nét đứt vì nó **chỉ quan sát**, không bao giờ đổi quyết định.

Chi tiết sơ đồ: [DIAGRAMS.md](../DIAGRAMS.md) (3 sơ đồ Mermaid, xem được ngay trên GitHub).

## 5. Vòng đời một workflow

```
draft → analyzed → in_review → approved → executing → executed → evidenced
                       ↑                      ↓
                       └──── interrupted ─────┘
```

- Mỗi bước chuyển là **hành động có chủ đích của con người**, gắn với số **revision** hiện tại.
- Gửi revision cũ → hệ thống **từ chối** (HTTP 409), không ghi đè âm thầm.
- Mở lại review sẽ **xoá sạch các phê duyệt** — và làm mất hiệu lực kết luận GO trước đó.
- Sửa một test sau khi đã duyệt → phê duyệt của test đó **hết hiệu lực**.

## 6. Đã xây dựng những gì

| Giai đoạn | Nội dung |
|---|---|
| 1 | Hợp đồng miền bất biến, kiểu dữ liệu nghiêm ngặt, quy tắc có phiên bản, băm nội dung |
| 2 | Oracle kiểu tĩnh, mock bảo hiểm độc lập, bộ thực thi test đã duyệt, adapter SUT qua HTTP |
| 3 | Delta quy tắc, phân tích ảnh hưởng, tìm lỗ hổng có chặn, sinh test, độ phủ, mutation |
| 4 | Snapshot SQLite, kiểm tra revision, review tường minh, nhật ký thực thi, bằng chứng |
| 5 | Import JSON/XLSX có kiểm tra, trích dẫn nguồn, lưu nguyên bytes gốc |
| 6 | Rút quy tắc bằng Mock/Ollama, kiểm tra trích dẫn đúng dòng, đề xuất bất biến, review quy tắc |
| 7 | Kho tri thức đã duyệt, embedding, tìm kiếm lai (từ khoá + vector), gợi ý có căn cứ |
| 8 | Workspace trình duyệt hợp nhất, REST có phiên bản, review nhiều test nguyên tử, tải xuống, audit |
| 9 | Cổng chất lượng hồi quy, báo cáo gắn revision, benchmark tổng hợp |
| 10 | Hồ sơ AI ghim digest, kiểm tra sẵn sàng, công cụ đánh giá 3 vai trò AI |
| 11 | Log có cấu trúc, trace, metrics, phân loại lỗi provider, đóng gói chạy demo |
| 12 | Tổng hợp benchmark, sơ đồ, kịch bản demo tính giờ, slide, bản phát lại dự phòng |
| — | Đóng gói `.exe` chạy độc lập + bộ `demo-kit` mang đi được |

## 7. Số liệu thực đo

Mọi con số dưới đây **sao chép từ artifact trong repo**, không ước lượng. Chi tiết kèm nguồn:
[BENCHMARKS.md](../BENCHMARKS.md).

| Đo cái gì | Giá trị | Nhưng **không** chứng minh |
|---|---|---|
| Hợp đồng cổng chất lượng | **6/6** kịch bản đúng kết luận | Không phải độ chính xác mô hình |
| Độ phủ biên (thiết kế) | **16,67% → 100%** | Độ phủ không phải tỷ lệ pass, không phải phê duyệt phát hành |
| Mutation score | **100%** | Bộ mutant nhỏ, một kịch bản |
| Trích xuất — mock | **5/10** | Đây là **phát lại fixture**, không phải hiểu ngôn ngữ |
| Trích xuất — model thật v1 | **2/10** | 10 case tự soạn, chưa có nhãn chuyên gia |
| Trích xuất — model thật v2 | **4/10** | Prompt v2 sửa sau khi xem lỗi v1 → **không phải** kiểm định độc lập |
| Truy hồi top‑1 (model thật) | **9/9** | Corpus chỉ 3 bản ghi — rất nhỏ |
| Độ trễ trích xuất (trung vị) | **4.678 ms** | Một máy, một lần chạy, gồm cả thời gian nạp model |
| Bộ test tự động | **286 passing** | Số lượng test không phải thước đo chất lượng |

**Phải nói thẳng khi trình bày:** con số mock 5/10 *cao hơn* model thật 4/10, nhưng mock chỉ phát lại đúng
fixture. Không được dùng nó để chứng minh năng lực AI.

## 8. Giới hạn — nói thẳng

- **Không phải engine suy luận bảo hiểm tổng quát.** DSL cố tình nhỏ: chỉ 2 trường (`age` kiểu số nguyên,
  `claim_amount` kiểu tiền), 8 toán tử, 5 loại kết quả. Cái gì không diễn đạt được thì **từ chối**, không đoán.
- **Chưa sẵn sàng chạy thật.** Tên người duyệt là tự khai. Không xác thực, không phân quyền, không tăng cường
  bảo mật triển khai. Chỉ chạy loopback trên máy cá nhân.
- **GO không phải giấy phép phát hành.** Đó là đánh giá hồi quy cục bộ cho **một revision**.
- **SHA-256 là kiểm tra toàn vẹn, không phải chữ ký số.** Người có quyền ghi database có thể sửa dữ liệu rồi
  tính lại băm.
- **Chưa đo:** mức chấp nhận của người duyệt thật, thời gian tiết kiệm, độ chính xác môi trường thật, chi phí
  token, nhãn do chuyên gia bảo hiểm gán.
- **Kịch bản `deductible` luôn NO-GO** kể cả khi không bơm lỗi — tìm kiếm có chặn không chứng minh được nhánh
  mặc định nên còn nghĩa vụ chưa giải quyết. Đây là **hợp đồng cố ý**, hãy nói vậy nếu bị hỏi.
- **File `.exe` chỉ chạy Windows x64 và chưa ký số** → SmartScreen cảnh báo lần đầu.

## 9. Nợ kỹ thuật đã biết

| Chỗ nào | Tình trạng |
|---|---|
| `streamlit_app/` | Khung rỗng, chưa triển khai. Nên xoá hoặc giữ kèm ghi chú. |
| `factory/providers/llm/openai.py` | Khung rỗng, nhưng `config.py` vẫn chấp nhận `llm_provider=openai`. |
| Giao diện `/legacy` | Bản cũ, dùng database riêng `data/factory.db`, không được đo đạc. |
| Phân tích biên | Mạnh với bảng một trường; bảng nhiều trường còn hạn chế. |
| Metrics | Chỉ trong tiến trình, mất khi restart, không xuất ra đâu cả. |
| Máy chủ | Luồng đồng bộ, không có hàng đợi nền, không huỷ được lời gọi LLM đang chạy. |

## 10. Lộ trình tiếp theo

### Giai đoạn 13 — Chứng minh năng lực AI bằng dữ liệu thật
Mục tiêu: thay "4/10 trên 10 case tự soạn" bằng một con số đáng tin.

- Mở rộng bộ đánh giá lên **quy mô hàng trăm case**, lấy từ tài liệu bảo hiểm thật (đã ẩn danh).
- Nhờ **chuyên gia nghiệp vụ gán nhãn** — đây là mắt xích thiếu lớn nhất hiện nay.
- Tách **tập kiểm định giữ riêng**, không được xem trước khi sửa prompt. Prompt v2 hiện tại vi phạm điều này.
- Đo từng loại lỗi: sai ngưỡng, sai toán tử, sai nhánh mặc định, bịa dữ kiện.

### Giai đoạn 14 — Ghép vào quy trình thật
- Nối **SUT thật** qua adapter HTTP đã có sẵn (`factory/providers/sut/http.py`).
- Chạy trong **CI**: mỗi lần sửa quy tắc tự động sinh test, chặn merge khi NO-GO.
- Xuất kết quả theo định dạng công cụ test phổ biến (JUnit XML) để ghép vào dashboard sẵn có.

### Giai đoạn 15 — Đủ chuẩn vận hành
- **Xác thực và phân quyền**: tách vai trò BA / QA / người phê duyệt. Bỏ tên tự khai.
- **Bằng chứng ký số** và **lưu trữ chỉ-ghi-thêm** — để băm trở thành bằng chứng thật sự.
- Giám sát vận hành: xuất metrics ra hệ thống ngoài thay vì chỉ giữ trong tiến trình.
- Hàng đợi nền cho các lời gọi AI lâu, huỷ được.

### Giai đoạn 16 — Mở rộng năng lực phân tích
- Mở rộng DSL: nhiều trường hơn, ngày hiệu lực, bảng quyết định lồng nhau.
- **Test biến hình (metamorphic)**: kiểm tra quan hệ giữa các đầu vào, không chỉ từng điểm biên.
- Giải quyết điểm yếu nhánh mặc định đang làm `deductible` luôn NO-GO.
- Hỗ trợ nhiều nền tảng: bản dựng cho Linux/macOS, và ký số cho bản Windows.

### Thay thế hạ tầng khi cần
Kiến trúc đã tách sẵn ranh giới. Khi cần mở rộng, có thể thay **FastAPI** cho tầng vận chuyển,
**PostgreSQL** cho lưu trữ, mà không đụng tới engine và hợp đồng miền.

## 11. Đọc tiếp

| Tài liệu | Nội dung |
|---|---|
| [HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md) | Hướng dẫn thao tác từng bước (tiếng Việt) |
| [DIAGRAMS.md](../DIAGRAMS.md) | 3 sơ đồ kiến trúc |
| [BENCHMARKS.md](../BENCHMARKS.md) | Mọi con số kèm nguồn và giới hạn |
| [COMPETITION_DEMO.md](../COMPETITION_DEMO.md) | Kịch bản demo 5 và 10 phút, có đường lui khi hỏng |
| [OBSERVABILITY.md](../OBSERVABILITY.md) | Log, trace, metrics, phân loại lỗi provider |
| [PACKAGING.md](../PACKAGING.md) | Đóng gói `.exe`, dữ liệu ghi ở đâu |
| [QUALITY_GATE.md](../QUALITY_GATE.md) | Ngưỡng cổng chất lượng và mã thoát |
| [LIVE_AI.md](../LIVE_AI.md) | Cấu hình model thật và kết quả đánh giá |
