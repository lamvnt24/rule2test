# Rule2Test — Hướng dẫn sử dụng

*Viết cho người trực tiếp dùng tool. Không cần biết lập trình. Muốn hiểu hệ thống làm gì và đi tới đâu, xem
[TONG-QUAN-VA-ROADMAP.md](TONG-QUAN-VA-ROADMAP.md).*

---

## Tool này làm gì, nói cho dễ hiểu

Bạn sửa một quy tắc bảo hiểm. Ví dụ: **tuổi được tham gia đổi từ 60 lên 65**.

Tool sẽ:

1. So hai phiên bản quy tắc, chỉ ra **cái gì đã đổi**.
2. Tìm ra **những tình huống chưa ai test** — đặc biệt là vùng biên vừa dịch (tuổi 64, 65, 66).
3. Sinh ra các **test đề xuất**, nhưng **bạn phải tự duyệt** từng cái.
4. Chạy test đã duyệt, so **kết quả mong đợi** với **kết quả thực tế** do một hệ thống riêng tính.
5. Đóng gói thành **bằng chứng** có mã băm, kiểm chứng lại được.
6. Cho một kết luận **GO / NO-GO**: có nên yên tâm không.

**Điều quan trọng nhất cần nhớ:** AI chỉ *đề xuất*. Máy tính kết quả mong đợi. **Bạn** là người duyệt.
Tool không tự duyệt bất cứ thứ gì.

---

## 1. Chạy lên

### Cách dễ nhất — dùng file `.exe`

Mở thư mục có file `rule2test.exe`, nháy đúp vào nó.

- Một cửa sổ đen hiện ra, chạy tự kiểm tra rồi **tự mở trình duyệt**.
- Nếu trình duyệt không tự mở, gõ vào thanh địa chỉ: `http://127.0.0.1:8000`
- **Muốn tắt:** nhấn `Ctrl + C` trong cửa sổ đen, hoặc đóng cửa sổ đó.

> **Windows cảnh báo "Windows protected your PC"?**
> File chưa được ký số. Bấm **More info → Run anyway**. Đây là hạn chế đã biết.

Vài lệnh hữu ích (mở PowerShell trong thư mục chứa file):

```powershell
.\rule2test.exe                 # chạy bình thường
.\rule2test.exe --port 8010     # dùng cổng khác, khi 8000 đã bị chiếm
.\rule2test.exe --no-browser    # không tự mở trình duyệt
.\rule2test.exe check           # chỉ tự kiểm tra rồi thoát
.\rule2test.exe doctor          # xem máy có model AI nào
```

### Nếu bạn có mã nguồn

```powershell
py -3 -B scripts/run_demo.py --seed
```

### Dữ liệu của bạn nằm ở đâu

Trong thư mục **`data`** **nằm cạnh file `.exe`**. Cửa sổ đen in ra đường dẫn chính xác mỗi lần chạy.

Nghĩa là: chép file `.exe` vào USB → dữ liệu đi theo USB. Tắt tool rồi bật lại, **mọi thứ vẫn còn**.

---

## 2. Màn hình có gì

Cột trái có 6 mục:

| # | Tên | Dùng để |
|---|---|---|
| 01 | **Overview** | Xem tổng quan, danh sách workflow, kiểm tra cấu hình AI và tình trạng chạy |
| 02 | **Document intake** | Đưa tài liệu quy tắc vào (tạo mẫu có sẵn, hoặc import JSON/Excel) |
| 03 | **AI rule review** | Cho AI đọc tài liệu văn xuôi và rút ra quy tắc — **bạn duyệt trước khi dùng** |
| 04 | **Test workspace** | Phân tích thay đổi, xem test đề xuất, **duyệt test** |
| 05 | **Knowledge & reuse** | Tái sử dụng test đã duyệt từ workflow khác |
| 06 | **Run & evidence** | Chạy test, tạo bằng chứng, chấm GO/NO-GO |

Ô **Reviewer identity** góc trên bên phải: gõ tên bạn vào. Bắt buộc, vì mọi quyết định đều ghi lại ai duyệt.

> Tên này là **tự khai**, tool không xác thực. Đây là bản demo chạy trên máy cá nhân.

Thanh thông báo ở giữa màn hình cho biết việc vừa rồi thành công hay lỗi. **Đọc nó** — nó luôn nói phải làm gì tiếp.

---

## 3. Làm trọn một vòng — 5 phút

Đây là luồng chính. Làm đúng thứ tự này.

### Bước 1 — Gõ tên bạn
Góc trên bên phải, ô **Reviewer identity**.

### Bước 2 — Tạo tài liệu mẫu
**02 Document intake** → chọn **Eligibility · age 60 → 65** → bấm **Create synthetic workflow**.

*Bạn sẽ thấy:* thông báo "Draft created", màn hình nhảy sang **04 Test workspace**, trạng thái **draft**.

### Bước 3 — Phân tích thay đổi
Bấm **Analyze & generate**.

*Bạn sẽ thấy:* **14 test đề xuất**, trạng thái đổi thành **analyzed**.

Mở phần **Rule delta, impact, gaps & baseline coverage** để xem tool đã tìm ra gì: quy tắc nào đổi, test nào bị
ảnh hưởng, vùng nào chưa ai phủ.

### Bước 4 — Mở phiên duyệt
Bấm **Open test review**. Trạng thái đổi thành **in_review**.

### Bước 5 — Duyệt test  ← **đây là phần của bạn**
1. Xem qua bảng test: cột **Inputs** là đầu vào, cột **Expected** là kết quả tool tính ra.
2. Tick chọn test bạn đồng ý (hoặc tick **Select all displayed tests for review**).
3. Gõ lý do vào ô **Test review reason**. Bắt buộc.
4. Bấm **Approve selected**.
5. Bấm **Finalize review** → trạng thái **approved**.

*Bạn sẽ thấy:* "14 explicit review decisions saved", rồi "Review finalized".

> Có thể **Reject selected** (loại bỏ) hoặc **Request changes** (yêu cầu sửa). Test bị loại sẽ không được chạy.
> Còn test nào chưa quyết định thì **không finalize được**.

### Bước 6 — Chạy test
**06 Run & evidence** → để **Injected fault** = **None** → bấm **Execute approved tests**.

*Bạn sẽ thấy:* **14 pass, 0 fail**. Mỗi dòng có **Expected** cạnh **Actual**.

### Bước 7 — Tạo bằng chứng và chấm điểm
1. Bấm **Create evidence pack** → thông báo kèm mã băm SHA-256.
2. Bấm **Evaluate current revision** → kết luận **GO**.
3. Muốn lấy file: **Download verified evidence JSON**.

### Bước 8 — Thử nghiệm bơm lỗi  ← **phần thuyết phục nhất**

Giờ giả lập lập trình viên code sai lệch đúng một đơn vị ở ngưỡng:

1. Ô **Reason** (mục Workflow controls) gõ lý do → bấm **Reopen review**.
2. Sang **04 Test workspace** → chọn lại tất cả → gõ lý do → **Approve selected** → **Finalize review**.
3. Về **06 Run & evidence** → đổi **Injected fault** thành **Boundary** → **Execute approved tests**.
4. **Create evidence pack** → **Evaluate current revision**.

*Bạn sẽ thấy:* **13 pass, 1 fail**, kết luận **NO-GO**, và test hỏng chỉ đúng một con tuổi cụ thể.

**Đây là điểm mấu chốt:** bộ test xanh thôi chưa đủ. Lỗi nằm đúng ngay cái biên vừa dịch chuyển, và tool bắt được.

---

## 4. Import tài liệu có sẵn

**02 Document intake** → mục **Import JSON or Excel** → chọn file → **Validate & import**.

- Hỗ trợ **.json** và **.xlsx**, tối đa 10 MB.
- File mẫu nằm trong `data/import/` (nếu bạn dùng bộ demo-kit) hoặc `data/demo/`.
- Tool **lưu lại nguyên bytes file gốc** kèm mã băm. Tải lại được bất cứ lúc nào ở mục **Run & evidence**.
- File sai định dạng sẽ bị **từ chối kèm danh sách lỗi cụ thể** — chỉ rõ sheet nào, ô nào.

---

## 5. Cho AI đọc tài liệu văn xuôi

Dùng khi quy tắc nằm trong văn bản, chưa có dạng bảng.

**03 AI rule review:**

1. Bấm **Load sample text** để nạp cặp tài liệu mẫu (tiếng Nhật), hoặc tự dán nội dung vào hai ô
   **Version 1** và **Version 2**.
2. Bấm **Extract rule proposal**.
3. Xem kết quả: mở **Extracted rule output & citations**.

**Bắt buộc kiểm tra:** mỗi quy tắc AI rút ra phải kèm **đúng dòng gốc** trong tài liệu. Nếu trích dẫn không
khớp nguyên văn, tool **tự loại bỏ** — không chấp nhận AI nói suông.

4. Gõ lý do vào **Rule review reason** → **Approve proposal** (hoặc **Reject proposal**).
5. Chỉ sau khi duyệt mới bấm được **Promote approved proposal** để biến nó thành workflow thật.

> Ô **Existing tests JSON** nằm trong phần gập lại — bấm vào để mở nếu cần. Bỏ trống cũng được.

**Trạng thái đề xuất nghĩa là gì:**

| Trạng thái | Nghĩa |
|---|---|
| `pending_review` | AI đọc được, đang chờ bạn duyệt |
| `needs_clarification` | Tài liệu thiếu/mơ hồ, AI **từ chối đoán** và hỏi lại — đây là hành vi đúng |
| `invalid_output` | AI trả về sai định dạng hoặc trích dẫn sai → bị loại |
| `provider_error` | Không gọi được AI. Xem phần Xử lý sự cố bên dưới |

Mặc định tool chạy **AI giả lập ngoại tuyến** (mock) — nó chỉ phát lại đúng vài mẫu có sẵn, **không phải AI
thật hiểu ngôn ngữ**. Mọi kết quả đều gắn nhãn `simulated`.

---

## 6. Tái sử dụng test đã duyệt

**05 Knowledge & reuse** — lấy test người khác đã duyệt ở workflow khác dùng lại cho workflow hiện tại.

1. Tick chọn workflow nguồn → **Build knowledge index**.
2. Gõ từ khoá vào ô **Query** → **Search knowledge** để xem kết quả tìm được.
3. Bấm **Propose tests for active workflow** → tool đề xuất một lô test.
4. Xem kỹ lô đó → **Attach batch for review**.

Quan trọng: tool chỉ mượn **đầu vào**. Kết quả mong đợi luôn được **tính lại** theo quy tắc mới. Lô test gắn vào
vẫn ở trạng thái **chờ duyệt** — bạn vẫn phải duyệt.

---

## 7. Cổng chất lượng — 11 mục kiểm tra

Bấm **Evaluate current revision** ở mục **06 Run & evidence**.

| Mục kiểm | Yêu cầu |
|---|---|
| `current_evidence` | Workflow phải ở trạng thái **evidenced** |
| `complete_run` | Mỗi test đã duyệt phải có đúng một lần chạy, trong một run hoàn tất |
| `execution_results` | **Mọi** test phải PASS. Không có FAIL/ERROR/SKIPPED |
| `rule_coverage` | Phủ ≥ 90% nghĩa vụ theo đầu vào đã chạy |
| `branch_coverage` | Phủ ≥ 90% |
| `boundary_coverage` | Phủ ≥ 90% |
| `exception_coverage` | Phủ ≥ 90% |
| `resolved_obligations` | Không còn nghĩa vụ nào chưa giải quyết |
| `candidate_acceptance` | ≥ 70% test mới do tool sinh được duyệt |
| `archived_rule_traceability` | Mỗi lần chạy truy ngược được về bản quy tắc và bytes gốc đã lưu |
| `evidence_consistency` | Bằng chứng khớp với snapshot đã duyệt và nhật ký chạy |

**GO** nghĩa là: **ở revision này**, không thấy dấu hiệu hồi quy. **Không phải** giấy phép phát hành.

> **Lưu ý về kịch bản `deductible`:** nó luôn **NO-GO** kể cả khi không bơm lỗi, vì tìm kiếm có chặn không
> chứng minh được nhánh mặc định. Đây là **thiết kế cố ý**, không phải lỗi tool.

Mở lại review → kết luận GO cũ **mất hiệu lực** ngay. Đúng như vậy: kết luận luôn gắn với một revision.

---

## 8. Kiểm tra tình trạng khi có sự cố

**01 Overview** → mục **Run diagnostics** → bấm **Inspect this run**.

Bạn thấy: mức log, số chuỗi đo, phiên bản database, phiên bản Python, thư viện tuỳ chọn nào đang có, bảng đếm
request và thời gian xử lý.

> Các số đếm này **chỉ tồn tại trong lần chạy hiện tại**, tắt tool là mất. Chúng **không bao giờ** chứa nội dung
> tài liệu, prompt, tên người duyệt hay session token.

Mỗi thông báo lỗi đều kèm một **Trace** (mã 16 ký tự). Mã đó cũng xuất hiện trong cửa sổ đen — dùng nó để dò
đúng dòng log tương ứng.

---

## 9. Xử lý sự cố

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Windows chặn file `.exe` | Chưa ký số | **More info → Run anyway** |
| "Port 8000 is already in use" | Cổng bị chiếm | Chạy `.\rule2test.exe --port 8010` |
| Preflight báo `[FAIL]` | Có điều kiện chưa thoả | Đọc dòng FAIL — nó ghi rõ lý do. Không có gì bị cài hay xoá |
| Nút bị mờ, bấm không được | Sai trạng thái | Xem nhãn trạng thái cạnh tên workflow. Phải làm bước trước đó |
| "Revision or state conflict" (409) | Hai thao tác giẫm chân nhau | Bấm **Refresh list**, mở lại workflow, làm lại. Tool từ chối ghi đè thay vì phá dữ liệu |
| "Select at least one test to review" | Chưa tick test nào | Tick test rồi bấm lại |
| Không finalize được | Còn test chưa quyết định | Duyệt hoặc loại hết các test còn `pending` |
| Báo lỗi **Provider failure** | Không gọi được AI | Đọc dòng **remediation** ngay dưới — nó nói chính xác phải làm gì |
| `model_mismatch` | Model chưa cài trên máy | Chạy `.\rule2test.exe doctor` xem có model nào, dùng đúng tên đó |
| `unreachable` | Dịch vụ AI chưa chạy | Bật Ollama lên. Tool **không tự cài, không tự tải** gì cả |
| `timeout` | Model chạy quá lâu | Tăng `RULE2TEST_AI_TIMEOUT_SECONDS` (1–120) hoặc dùng model nhỏ hơn |
| Import bị từ chối | File sai định dạng | Danh sách lỗi chỉ rõ sheet/ô nào sai. Xem `docs/IMPORT_FORMAT.md` |

**Nguyên tắc khi lỗi:** tool **không bao giờ tự thử lại**, **không âm thầm quay về AI giả lập**, và **không tự
sửa** kết quả AI trả về. Lỗi luôn hiện ra để bạn quyết định.

---

## 10. Bật ghi log chi tiết

Mở PowerShell trong thư mục chứa `.exe`:

```powershell
$env:RULE2TEST_LOG_LEVEL="debug"
.\rule2test.exe
```

Muốn ghi ra file thay vì màn hình:

```powershell
$env:RULE2TEST_LOG_FILE="nhat-ky.log"
.\rule2test.exe
```

Mức log: `off` · `debug` · `info` (mặc định) · `warn` · `error`.

---

## 11. Dùng AI thật thay vì AI giả lập

Cần cài sẵn **Ollama** trên máy, kèm một model chat và một model embedding.

```powershell
.\rule2test.exe doctor                       # xem máy có model nào, tên chính xác là gì
```

Rồi tạo hồ sơ (cần mã nguồn):

```powershell
py -3 -B scripts/ai_doctor.py --chat-model "TÊN_MODEL_CHAT" --embedding-model "TÊN_MODEL_EMBEDDING" `
  --dimensions 768 --write-profile data/ai_profiles/ollama.local.json
```

Chạy với hồ sơ đó:

```powershell
.\rule2test.exe --profile data\ai_profiles\ollama.local.json
```

Tool **kiểm tra mã digest của model lúc khởi động**. Sai model là báo lỗi ngay, không chạy tiếp. Không tự tải
model, không tự chọn model. Chi tiết: `docs/LIVE_AI.md`.

---

## 12. Bảng thuật ngữ

| Từ | Nghĩa dễ hiểu |
|---|---|
| **Workflow** | Một lần xử lý trọn vẹn cho một thay đổi quy tắc |
| **Revision** | Số phiên bản của workflow. Mỗi thay đổi tăng thêm 1 |
| **Oracle** | Bộ máy tính ra **kết quả mong đợi** từ quy tắc. Không phải AI |
| **SUT** | Hệ thống được đem ra test, tính **kết quả thực tế**. Độc lập hoàn toàn với oracle |
| **Expected / Actual** | Mong đợi (oracle tính) / Thực tế (SUT tính). Khác nhau là FAIL |
| **Injected fault** | Lỗi cố ý bơm vào SUT để chứng minh test bắt được lỗi thật |
| **Coverage** | Tỷ lệ tình huống đã được test phủ. **Không phải** tỷ lệ pass |
| **Boundary** | Vùng biên — giá trị sát ngưỡng (60, 65, 66). Nơi lỗi hay nấp nhất |
| **Gap / Obligation** | Tình huống bắt buộc phải test mà chưa ai phủ |
| **Mutation** | Cố tình làm sai quy tắc để xem bộ test có phát hiện không |
| **Evidence pack** | Gói bằng chứng: quy tắc + phê duyệt + đầu vào + mong đợi + thực tế + người duyệt, dưới một mã băm |
| **Quality gate** | Cổng chấm GO/NO-GO cho revision hiện tại |
| **Proposal** | Đề xuất quy tắc do AI rút ra, **chờ người duyệt** |
| **Simulated** | Nhãn cho biết kết quả do AI giả lập tạo ra, không phải AI thật |
| **Trace** | Mã 16 ký tự gắn với một request, dùng để dò log |

---

## 13. Ba điều đừng nhầm

1. **Coverage 100% không có nghĩa là không còn lỗi.** Nó chỉ nói các tình huống đã liệt kê đều được chạy qua.
2. **GO không phải là được phép phát hành.** Nó là đánh giá hồi quy cục bộ cho đúng một revision.
3. **AI giả lập (mock) đạt 5/10 không chứng minh AI giỏi.** Mock chỉ phát lại đúng mẫu có sẵn. AI thật hiện đạt
   4/10 trên 10 case tự soạn — con số thật và còn thấp. Đừng dùng số của mock để nói về năng lực AI.
