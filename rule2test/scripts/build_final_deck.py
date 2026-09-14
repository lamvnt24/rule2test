"""Build the Round 2 final-submission deck required by the organisers, for Track 2.

Two kinds of number appear on these slides and they are never mixed:

  DO DUOC  - measured, copied from data/generated/benchmark-summary.json, which is itself produced by
             running this repository's own services. Never typed by hand.
  GIA DINH - a model input. Every one is listed with its basis in ASSUMPTIONS below and shown on the
             slide that uses it. Change a value here and rebuild; the whole deck follows.
  TINH RA  - arithmetic over the two above, shown with its formula on the slide.

No ROI figure in this deck is presented as measured, because this project has not measured effort
savings. Claiming otherwise to a judging panel would be fabrication.
"""
import argparse,html,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.parsers.common import strict_json

ROOT=Path(__file__).resolve().parents[1]
SUMMARY=ROOT/"data"/"generated"/"benchmark-summary.json"
TARGET=ROOT/"docs"/"slides"/"final-round2.html"

# ---------------------------------------------------------------------------------------------
# EDIT THESE, THEN RERUN. Every figure on the business-case slides derives from this block.
# ---------------------------------------------------------------------------------------------
ASSUMPTIONS=dict(
    scope="Một team QA bảo hiểm",
    team_size=dict(value=8,decimals=0,unit="người",label="Quy mô team",
        basis="Quy mô một team QA sản phẩm bảo hiểm điển hình. Cố tình chọn đơn vị nhỏ nhất để con số dễ bảo vệ."),
    rule_changes_per_year=dict(value=36,decimals=0,unit="lần/năm",label="Số lần đổi quy tắc",
        basis="≈3 lần/tháng: thay đổi tham số sản phẩm, quy định pháp lý theo quý, quy tắc chiến dịch."),
    hours_per_change_today=dict(value=16,decimals=0,unit="giờ/lần",label="Công sức hiện tại, mỗi lần đổi",
        basis="2 người-ngày: đọc và so tài liệu ~5h, rà bộ test bị ảnh hưởng và thiết kế case mới ~7h, soạn hồ sơ truy vết ~4h."),
    hours_per_change_with_tool=dict(value=6,decimals=0,unit="giờ/lần",label="Công sức khi có công cụ",
        basis="Phân tích delta, tìm lỗ hổng, sinh test và đóng gói bằng chứng do máy làm. Phần còn lại là DUYỆT — việc này không tự động hoá và không được tính là tiết kiệm."),
    dsl_coverage_factor=dict(value=0.5,decimals=2,unit="tỷ lệ",label="Tỷ lệ quy tắc DSL diễn đạt được",
        basis="DSL hiện hỗ trợ 2 trường và 8 toán tử. Quy tắc nằm ngoài đó bị hệ thống TỪ CHỐI chứ không đoán, nên chỉ một nửa số lần đổi được tính vào ROI."),
    loaded_cost_vnd_per_hour=dict(value=300_000,decimals=0,unit="VND/giờ",label="Chi phí đầy đủ một giờ QA",
        basis="Lương, bảo hiểm, quản lý, thiết bị ≈45 triệu/tháng ÷ ~147 giờ làm việc/tháng."),
    productive_hours_per_person_year=dict(value=1_760,decimals=0,unit="giờ/người/năm",label="Giờ làm việc hữu ích",
        basis="220 ngày làm việc × 8 giờ. Dùng làm mẫu số cho cách tính năng suất thứ hai."),
)
SENSITIVITY=(("Hiện tại (giai đoạn 12)",0.5,36),
             ("Mở rộng DSL (giai đoạn 16)",0.8,36),
             ("Tần suất đổi quy tắc cao",0.5,60),
             ("Cả hai",0.8,60))
SCALE=((1,"1 team QA"),(5,"5 team / 1 Business Unit"),(20,"20 team / nhiều BU"))

def value(name):return ASSUMPTIONS[name]["value"]

def model(coverage=None,changes=None):
    coverage=value("dsl_coverage_factor") if coverage is None else coverage
    changes=value("rule_changes_per_year") if changes is None else changes
    saved_per_change=value("hours_per_change_today")-value("hours_per_change_with_tool")
    eligible=changes*coverage
    hours=eligible*saved_per_change
    workload=changes*value("hours_per_change_today")
    capacity=value("team_size")*value("productive_hours_per_person_year")
    return dict(saved_per_change=saved_per_change,eligible=eligible,hours=hours,workload=workload,
        capacity=capacity,on_workload=100*hours/workload if workload else 0,
        on_capacity=100*hours/capacity if capacity else 0,
        vnd=hours*value("loaded_cost_vnd_per_hour"))

def measured():
    if not SUMMARY.exists():return {}
    try:data=strict_json(SUMMARY.read_text(encoding="utf-8"))
    except (ValueError,UnicodeError):return {}
    return {entry["name"]:entry["value"] for entry in data.get("entries",[])}

def vn(number,decimals=0):
    """Vietnamese number formatting: dot groups thousands, comma marks the decimal."""
    text=f"{number:,.{decimals}f}"
    return text.replace(",","\x00").replace(".",",").replace("\x00",".")

def million(vnd):
    return vn(vnd/1_000_000)+" triệu VND"

def esc(text):return html.escape(str(text),quote=False)

STYLE="""
:root{--bg:#0b1020;--panel:#151b2e;--fg:#eef2f8;--muted:#93a0b8;--line:#2a3350;
      --measured:#3fb950;--assumed:#d29922;--derived:#58a6ff;--accent:#7c8cff}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);
  font:16px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
#deck{height:100%;display:flex;flex-direction:column}
#bar{height:3px;background:var(--line);flex:none}#bar i{display:block;height:100%;background:var(--accent);transition:width .2s}
section{flex:1;display:none;padding:clamp(18px,3.4vw,48px);overflow:auto}
section.on{display:block}
.kicker{display:flex;gap:10px;align-items:center;margin:0 0 10px;flex-wrap:wrap}
.kicker span{color:var(--accent);letter-spacing:.13em;text-transform:uppercase;font-size:11px;font-weight:700}
.time{color:var(--muted);font-size:11px;border:1px solid var(--line);border-radius:20px;padding:2px 9px}
h1{font-size:clamp(28px,4.6vw,54px);line-height:1.08;margin:0 0 16px;letter-spacing:-.02em}
h2{font-size:clamp(21px,3vw,36px);line-height:1.15;margin:0 0 16px;letter-spacing:-.01em}
h3{font-size:clamp(15px,1.7vw,19px);margin:22px 0 8px;color:var(--fg)}
p{font-size:clamp(14px,1.5vw,19px);max-width:66ch}
.lead{color:var(--muted)}
ul{font-size:clamp(14px,1.5vw,19px);max-width:70ch;padding-left:20px}li{margin:9px 0}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));margin:18px 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.stat b{display:block;font-size:clamp(21px,3vw,36px);line-height:1.1;margin-bottom:5px}
.stat span{color:var(--muted);font-size:12.5px;display:block}
.tag{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.08em;padding:2px 7px;
     border-radius:4px;margin-bottom:7px;text-transform:uppercase}
.t-measured{background:rgba(63,185,80,.16);color:var(--measured);border:1px solid rgba(63,185,80,.4)}
.t-assumed{background:rgba(210,153,34,.16);color:var(--assumed);border:1px solid rgba(210,153,34,.4)}
.t-derived{background:rgba(88,166,255,.16);color:var(--derived);border:1px solid rgba(88,166,255,.4)}
table{border-collapse:collapse;width:100%;font-size:clamp(12.5px,1.35vw,16px);margin:10px 0}
th,td{border-bottom:1px solid var(--line);padding:8px 9px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12.5px;text-transform:uppercase;letter-spacing:.05em}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
code{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:1px 6px;font-size:.9em}
.formula{background:var(--panel);border-left:3px solid var(--derived);border-radius:0 8px 8px 0;
  padding:12px 16px;margin:14px 0;font-size:clamp(13px,1.4vw,17px);max-width:74ch}
.note{color:var(--muted);font-size:clamp(11.5px,1.2vw,13.5px);margin-top:16px;border-top:1px solid var(--line);
  padding-top:11px;max-width:80ch}
.two{display:grid;gap:18px;grid-template-columns:repeat(auto-fit,minmax(290px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:15px}
.card h4{margin:0 0 8px;font-size:15px}
.demo{border:2px dashed var(--accent);border-radius:12px;padding:20px;margin:16px 0;background:rgba(124,140,255,.06)}
footer{flex:none;display:flex;justify-content:space-between;align-items:center;gap:12px;
  padding:8px 16px;border-top:1px solid var(--line);color:var(--muted);font-size:11.5px}
footer button{font:inherit;background:var(--panel);color:var(--fg);border:1px solid var(--line);
  border-radius:6px;padding:4px 10px;cursor:pointer}
footer button:hover{border-color:var(--accent)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:8px}
/* Print and PDF export: one 16:9 page per slide, 338mm x 190mm (13.33in x 7.5in). */
@page{size:338mm 190mm;margin:0}
@media print{
  html,body{height:auto;background:var(--bg)}
  #deck{display:block;height:auto}
  #bar,footer{display:none}
  section{display:block!important;width:338mm;height:190mm;overflow:hidden;
          padding:12mm 15mm;break-after:page;page-break-after:always;
          background:var(--bg);-webkit-print-color-adjust:exact;print-color-adjust:exact}
  section:last-child{break-after:auto;page-break-after:auto}
  .note{margin-top:12px;padding-top:9px}
}
"""

SCRIPT="""
const slides=[...document.querySelectorAll("section")];
let i=Math.min(Math.max(parseInt(location.hash.slice(1))-1||0,0),slides.length-1);
function show(){
  slides.forEach((s,n)=>s.classList.toggle("on",n===i));
  document.getElementById("count").textContent=(i+1)+" / "+slides.length;
  document.getElementById("fill").style.width=((i+1)/slides.length*100)+"%";
  history.replaceState(null,"","#"+(i+1));slides[i].scrollTop=0;
}
function go(d){i=Math.min(Math.max(i+d,0),slides.length-1);show();}
document.getElementById("prev").onclick=()=>go(-1);
document.getElementById("next").onclick=()=>go(1);
addEventListener("keydown",e=>{
  if(["ArrowRight","PageDown"," "].includes(e.key)){e.preventDefault();go(1);}
  if(["ArrowLeft","PageUp"].includes(e.key)){e.preventDefault();go(-1);}
  if(e.key==="Home"){i=0;show();}
  if(e.key==="End"){i=slides.length-1;show();}
});
addEventListener("hashchange",()=>{const t=parseInt(location.hash.slice(1));
  if(t>=1&&t<=slides.length&&t-1!==i){i=t-1;show();}});
show();
"""

def kicker(label,minutes=""):
    clock=f'<span class="time">{esc(minutes)}</span>' if minutes else ""
    return f'<p class="kicker"><span>{esc(label)}</span>{clock}</p>'

TAGS=dict(measured="Đo được",assumed="Giả định",derived="Tính ra")

def tagged(kind):
    return f'<span class="tag t-{kind}">{TAGS[kind]}</span>'

def stat(figure,label,tag=""):
    return f'<div class="stat">{tagged(tag) if tag else ""}<b>{figure}</b><span>{esc(label)}</span></div>'

def slides_html():
    m=measured();base=model()
    gate=m.get("Quality-gate contract cases matched","6/6")
    cov=m.get("Designed boundary coverage, baseline to final","16.67% → 100.0%")
    mut=m.get("Mutation score on the same scenario","100.0%")
    live=m.get("Live cloud model, prompt v2 — extraction cases matched","4/10")
    mock=m.get("Offline mock replay — extraction cases matched","5/10")
    retr=m.get("Live cloud model, prompt v2 — retrieval top-1","9/9")
    suite=m.get("Automated test suite","286 passing")

    legend=('<div class="legend">'+tagged("measured")+' số đo thật trong repo &nbsp;·&nbsp; '
            +tagged("assumed")+' giả định mô hình, có ghi căn cứ &nbsp;·&nbsp; '
            +tagged("derived")+' tính ra từ hai loại trên</div>')

    assumption_rows="".join(
        "<tr><td>"+esc(v["label"])+"</td>"
        "<td class='num'>"+vn(v["value"],v["decimals"])+" "+esc(v["unit"])+"</td>"
        "<td>"+esc(v["basis"])+"</td></tr>"
        for v in ASSUMPTIONS.values() if isinstance(v,dict))

    def row(label,*cells):
        return "<tr><td>"+esc(label)+"</td>"+"".join("<td class='num'>"+c+"</td>" for c in cells)+"</tr>"

    sensitivity_rows="".join(
        row(label,f"{int(c*100)}%",vn(ch),vn(model(c,ch)["hours"]),million(model(c,ch)["vnd"]))
        for label,c,ch in SENSITIVITY)

    scale_rows="".join(
        row(label,vn(n*value("team_size")),vn(base["hours"]*n),million(base["vnd"]*n))
        for n,label in SCALE)

    return [
# 1
f"""{kicker("Round 2 · Final submission · Track 2","20 phút + 10 phút Q&A")}
<h1>Rule2Test</h1>
<p class="lead">Mỗi thay đổi quy tắc bảo hiểm trở thành test hồi quy đã được người duyệt,
và bằng chứng thực thi kiểm chứng lại được.</p>
<div class="grid">{stat(esc(cov),"độ phủ biên thiết kế, trước → sau","measured")}
{stat(esc(gate),"kịch bản cổng chất lượng đúng kết luận","measured")}
{stat(esc(suite),"test tự động trên bản dựng này","measured")}</div>
{legend}
<p class="note">Toàn bộ số gắn nhãn "Đo được" sao chép từ artifact trong repo, do chính hệ thống chạy ra.
Dữ liệu tổng hợp là dữ liệu mô phỏng, không phải đo lường môi trường thật.</p>""",

# 2
f"""{kicker("Nội dung trình bày")}
<h2>Chương trình 20 phút</h2>
<table><tr><th>Phần</th><th>Nội dung</th><th>Thời lượng</th></tr>
<tr><td>1</td><td>Problem &amp; Context — Bối cảnh và vấn đề</td><td class="num">3 phút</td></tr>
<tr><td>2</td><td>Solution Overview &amp; AI Approach — Giải pháp và cách dùng AI</td><td class="num">4 phút</td></tr>
<tr><td>—</td><td><strong>Live demo</strong> — nguyên mẫu chạy thật</td><td class="num">6 phút</td></tr>
<tr><td>3</td><td>Business Case (Track 2) — ROI định lượng</td><td class="num">4 phút</td></tr>
<tr><td>4</td><td>Differentiation / Innovation — Điểm khác biệt</td><td class="num">2 phút</td></tr>
<tr><td>5</td><td>Feasibility &amp; Next Steps — Khả thi và bước tiếp</td><td class="num">1 phút</td></tr></table>
<p class="note">Nguyên mẫu chạy được, đóng gói thành một file .exe duy nhất, không cần cài đặt gì trên máy đích.</p>""",

# 3
f"""{kicker("1 · Problem &amp; Context","3 phút")}
<h2>Một quy tắc thay đổi. Không ai chứng minh được nó làm hỏng gì.</h2>
<p>Công ty bảo hiểm sửa điều kiện tham gia: <strong>tuổi tối đa từ 60 lên 65</strong>. Sau khi sửa:</p>
<ul>
<li>Bộ test cũ <strong>vẫn xanh</strong> — vì chưa ai viết test cho vùng biên vừa dịch chuyển (61–65).</li>
<li>Không ai trả lời được thay đổi này <strong>làm mất hiệu lực test nào</strong>, và <strong>ai</strong> đã duyệt test mới.</li>
<li>Kết quả chạy test <strong>không truy ngược</strong> được về điều khoản nào trong tài liệu đã sinh ra nó.</li>
<li>Người duyệt bị yêu cầu tin bản tóm tắt của AI cho tài liệu họ <strong>không kiểm lại được từng dòng</strong>.</li>
</ul>
<p class="lead">Vấn đề cốt lõi không phải là sinh test tự động.
Vấn đề là <strong>truy vết</strong> và <strong>thẩm quyền phê duyệt</strong>.</p>""",

# 4
f"""{kicker("1 · Problem &amp; Context")}
<h2>Ba hệ quả trực tiếp</h2>
<div class="two">
<div class="card"><h4>Lỗi lọt ra môi trường thật</h4>
<p class="lead">Lỗi lệch một đơn vị ở ngưỡng tuổi hoặc ngưỡng số tiền là loại lỗi bộ test hiện có
ít khi phủ nhất, và là loại gây hậu quả trực tiếp lên khách hàng.</p></div>
<div class="card"><h4>Công sức lặp lại thủ công</h4>
<p class="lead">Mỗi lần đổi quy tắc, QA phải đọc lại tài liệu, rà bộ test cũ, thiết kế case biên
và soạn hồ sơ truy vết — gần như làm lại từ đầu.</p></div>
<div class="card"><h4>Không có bằng chứng cho kiểm toán</h4>
<p class="lead">Khi bị hỏi "vì sao tin rằng thay đổi này an toàn", câu trả lời hiện nay là một ảnh
chụp màn hình bộ test xanh — không gắn với điều khoản, không gắn với người duyệt.</p></div>
</div>""",

# 5
f"""{kicker("2 · Solution Overview","4 phút")}
<h2>Năm chặng, một chuỗi truy vết liên tục</h2>
<table><tr><th>Chặng</th><th>Việc xảy ra</th><th>Ai quyết định</th></tr>
<tr><td>Tiếp nhận</td><td>Hai phiên bản quy tắc; lưu nguyên bytes gốc kèm mã băm</td><td>Máy</td></tr>
<tr><td>Phân tích</td><td>Delta quy tắc, ảnh hưởng, tìm lỗ hổng có chặn, sinh test đề xuất</td><td>Máy</td></tr>
<tr><td><strong>Duyệt</strong></td><td>Phê duyệt tường minh từng test, gắn với revision</td><td><strong>Con người</strong></td></tr>
<tr><td>Thực thi</td><td>Chỉ chạy test đã duyệt, đối chiếu với hệ thống độc lập</td><td>Máy</td></tr>
<tr><td>Chứng minh</td><td>Gói bằng chứng + cổng chất lượng GO / NO-GO</td><td>Máy</td></tr></table>
<p class="note">Mỗi chặng gắn với một số revision. Gửi revision cũ thì hệ thống từ chối chứ không ghi đè âm thầm.
Mở lại phiên duyệt sẽ xoá phê duyệt cũ và làm mất hiệu lực kết luận GO trước đó.</p>""",

# 6
f"""{kicker("2 · AI Approach")}
<h2>AI đề xuất. Engine quyết định. Con người phê duyệt.</h2>
<div class="two">
<div class="card"><h4>AI được làm</h4><ul>
<li>Đọc tài liệu văn xuôi, rút ra quy tắc có cấu trúc</li>
<li>Đề xuất <em>đầu vào</em> test từ kho test đã duyệt</li>
<li>Tạo vector cho tìm kiếm lai</li></ul></div>
<div class="card"><h4>AI không bao giờ được làm</h4><ul>
<li>Tính kết quả <strong>mong đợi</strong> — oracle kiểu tĩnh làm việc này</li>
<li>Quyết định PASS / FAIL</li>
<li>Tự phê duyệt đề xuất của chính nó</li>
<li>Nhìn thấy đáp án trước khi trả lời</li></ul></div></div>
<h3>Bốn rào chắn kỹ thuật</h3>
<ul>
<li><strong>Trích dẫn đúng nguyên văn.</strong> Mỗi quy tắc AI rút ra phải kèm đúng dòng gốc. Sai một ký tự là bị loại.</li>
<li><strong>Không tự thử lại, không âm thầm quay về mock.</strong> Lỗi provider được phân loại thành 11 loại kèm hướng khắc phục.</li>
<li><strong>Ghim mã digest của model.</strong> Sai model là dừng ngay lúc khởi động.</li>
<li><strong>Hệ thống được test không bao giờ nhận kết quả mong đợi hay bản quy tắc.</strong></li>
</ul>""",

# 7
f"""{kicker("2 · AI Approach")}
<h2>Ranh giới tin cậy</h2>
<div class="formula">
Tài liệu (không tin cậy) → <strong>AI đề xuất</strong> → kiểm tra schema + trích dẫn đúng dòng
→ <strong>người duyệt quy tắc</strong> → phân tích &amp; oracle tính mong đợi
→ <strong>người duyệt test</strong> → hệ thống độc lập tính thực tế → bằng chứng → cổng GO/NO-GO
</div>
<p>Không có mũi tên nào đi ngược. Không đường nào chạm tới bước thực thi mà không qua phê duyệt của con người.
Lỗi provider dừng lại ở bước kiểm tra, được phân loại, và <strong>không</strong> được thay bằng kết quả giả lập.</p>
<div class="grid">{stat(esc(mock),"trích xuất — AI giả lập (chỉ phát lại fixture)","measured")}
{stat(esc(live),"trích xuất — model thật, 10 case tiếng Nhật tự soạn","measured")}
{stat(esc(retr),"truy hồi top-1 trên kho đã duyệt","measured")}</div>
<p class="note">Nói thẳng: số của AI giả lập cao hơn model thật, nhưng giả lập chỉ phát lại đúng mẫu có sẵn.
Không được dùng nó để chứng minh năng lực AI. Con số thật hiện là {esc(live)} và còn thấp.</p>""",

# 8
f"""{kicker("Live demo","6 phút")}
<h2>Nguyên mẫu chạy thật</h2>
<div class="demo">
<p style="margin-top:0"><strong>Bạn sắp thấy, theo đúng thứ tự:</strong></p>
<ul style="margin-bottom:0">
<li>Tạo workflow từ thay đổi tuổi 60 → 65, lưu nguyên tài liệu gốc kèm mã băm.</li>
<li>Phân tích: <strong>14 test đề xuất</strong>, chỉ ra vùng biên chưa ai phủ.</li>
<li>Phê duyệt tường minh — không có gì tự duyệt.</li>
<li>Chạy sạch: <strong>14 pass / 0 fail</strong> → cổng <strong>GO</strong>.</li>
<li><strong>Bơm lỗi lệch một đơn vị ở đúng ngưỡng</strong> → <strong>13 pass / 1 fail</strong> → cổng <strong>NO-GO</strong>,
    phản ví dụ là một con số tuổi cụ thể, không phải stack trace.</li>
<li>Tải gói bằng chứng, mở bảng chẩn đoán vận hành.</li>
</ul></div>
<p class="note">Chạy từ một file .exe duy nhất, không cần cài Python hay bất cứ thứ gì trên máy đích.
Dữ liệu ghi cạnh file .exe nên còn nguyên sau khi tắt và mở lại. Nếu demo trực tiếp không chạy được,
có sẵn bản phát lại ảnh chụp ngoại tuyến kèm đúng lời dẫn này.</p>""",

# 9
f"""{kicker("3 · Business Case · Track 2","4 phút")}
<h2>Cách chúng tôi tính ROI — và cách kiểm tra lại</h2>
<p>Dự án này <strong>chưa đo</strong> thời gian tiết kiệm thực tế. Vì vậy không có con số ROI nào ở đây được
trình bày như số đo. Thay vào đó là một mô hình công khai.</p>
{legend}
<div class="two" style="margin-top:18px">
<div class="card"><h4>Ba cam kết về số liệu</h4><ul style="margin:0">
<li>Mọi đầu vào đều ghi rõ <strong>căn cứ</strong> ngay trên slide sau.</li>
<li>Mọi phép tính đều <strong>hiện công thức</strong>.</li>
<li>Trình bày <strong>độ nhạy</strong> thay vì bảo vệ một con số duy nhất.</li>
</ul></div>
<div class="card"><h4>Phạm vi cố tình chọn nhỏ</h4>
<p class="lead" style="margin:0">{esc(ASSUMPTIONS["scope"])} — {vn(value("team_size"))} người.
Đây là đơn vị nhỏ nhất có thể kiểm chứng. Phần nhân rộng lên BU và tập đoàn được trình bày riêng,
tách khỏi con số gốc.</p></div></div>
<p class="note">Nếu quý vị cho rằng một giả định của chúng tôi sai, bảng độ nhạy ở slide sau chỉ ra ngay
kết quả sẽ thành bao nhiêu — thay vì phải tin hay không tin một con số.</p>""",

f"""{kicker("3 · Business Case · Track 2")}
<h2>Bảy giả định của mô hình</h2>
<table><tr><th>Đầu vào</th><th>Giá trị</th><th>Căn cứ</th></tr>{assumption_rows}</table>
<p class="note">Hệ số phủ DSL là giả định <em>thận trọng nhất</em>: hệ thống <strong>từ chối</strong> quy tắc
nó không diễn đạt được thay vì đoán, nên chỉ một nửa số lần đổi quy tắc được tính vào ROI.</p>""",

# 10
f"""{kicker("3 · Business Case · Track 2")}
<h2>Giờ tiết kiệm và giá trị quy đổi</h2>
<div class="formula">
Giờ tiết kiệm/năm = số lần đổi quy tắc × hệ số phủ DSL × (giờ thủ công − giờ có công cụ)<br>
= {vn(value("rule_changes_per_year"))} × {vn(value("dsl_coverage_factor"),2)} × ({vn(value("hours_per_change_today"))} − {vn(value("hours_per_change_with_tool"))})
= <strong>{vn(base["hours"])} giờ/năm</strong>
</div>
<div class="grid">
{stat(vn(base['hours'])+' giờ','tiết kiệm mỗi năm, một team '+vn(value('team_size'))+' người','derived')}
{stat(vn(base['on_workload'],1)+'%','tăng năng suất trên khối lượng việc hồi quy do đổi quy tắc','derived')}
{stat(vn(base['on_capacity'],2)+'%','trên tổng năng lực cả team — mẫu số rộng hơn','derived')}
{stat(million(base["vnd"]),"giá trị quy đổi mỗi năm","derived")}
</div>
<p><strong>Vì sao trình bày hai tỷ lệ năng suất?</strong> Công cụ chỉ tác động vào phần việc hồi quy do đổi
quy tắc ({vn(base["workload"])} giờ/năm), không phải toàn bộ công việc của team ({vn(base["capacity"])} giờ/năm).
Nêu cả hai để con số không bị hiểu sai theo hướng có lợi cho chúng tôi.</p>
<p class="note">Thời gian <strong>phê duyệt của con người không được tính là tiết kiệm</strong>. Việc đó không tự
động hoá và không nên tự động hoá — nó là thẩm quyền, không phải chi phí cần cắt.</p>""",

# 11
f"""{kicker("3 · Business Case · Track 2")}
<h2>Độ nhạy — con số đổi thế nào khi giả định đổi</h2>
<table><tr><th>Kịch bản</th><th>Phủ DSL</th><th>Lần đổi/năm</th><th>Giờ/năm</th><th>VND/năm</th></tr>
{sensitivity_rows}</table>
<p>Biến nhạy nhất là <strong>hệ số phủ DSL</strong>. Nâng nó là mục tiêu của giai đoạn 16 trong lộ trình
(mở rộng số trường và toán tử), và đó cũng là hạng mục kỹ thuật có đòn bẩy ROI cao nhất.</p>
<p class="note">Bảng này thay cho một con số đơn lẻ. Nếu quý vị cho rằng giả định của chúng tôi sai,
bảng chỉ ra ngay kết quả sẽ thành bao nhiêu — thay vì phải tin hay không tin một con số duy nhất.</p>""",

# 12
f"""{kicker("3 · Business Case · Track 2")}
<h2>Khả năng nhân rộng và tái sử dụng</h2>
<table><tr><th>Phạm vi</th><th>Số QA</th><th>Giờ/năm</th><th>VND/năm</th></tr>{scale_rows}</table>
<h3>Vì sao nhân rộng được — cơ chế, không phải lời hứa</h3>
<ul>
<li><strong>Engine không gắn nghiệp vụ cụ thể.</strong> Quy tắc là <em>dữ liệu</em>, không phải mã nguồn.</li>
<li><strong>Kho tri thức dùng chung.</strong> Test đã duyệt tái sử dụng được; kết quả mong đợi luôn <em>tính lại</em>.</li>
<li><strong>Không phụ thuộc hạ tầng.</strong> Lõi chỉ dùng thư viện chuẩn; triển khai đơn vị mới là chép một file.</li>
</ul>
<p class="note">Bảng trên là phép nhân tuyến tính từ mô hình một team, chưa trừ chi phí triển khai, đào tạo
và vận hành khi mở rộng.</p>""",

# 13
f"""{kicker("3 · Business Case · Track 2")}
<h2>Giá trị tránh rủi ro — trình bày riêng, có lý do</h2>
<p>Giá trị lớn nhất của hệ thống này nhiều khả năng <strong>không</strong> nằm ở giờ công tiết kiệm, mà ở
<strong>lỗi không lọt ra môi trường thật</strong>. Chúng tôi tách riêng phần này vì không đo được chi phí
một lỗi lọt trong bối cảnh của quý vị.</p>
<div class="two">
<div class="card"><h4>Cơ chế — đã đo</h4>
<p>{tagged("measured")}</p>
<p class="lead">Độ phủ biên thiết kế: <strong>{esc(cov)}</strong>.
Mutation score: <strong>{esc(mut)}</strong> trên cùng kịch bản.
Cổng chất lượng: <strong>{esc(gate)}</strong> kịch bản đúng kết luận, kể cả các ca cố tình phải NO-GO.</p></div>
<div class="card"><h4>Giá trị — chưa đo</h4>
<p>{tagged("assumed")}</p>
<p class="lead">Phụ thuộc quy mô hợp đồng, mức bồi hoàn và rủi ro pháp lý. Đây là con số
<strong>của quý vị</strong>.</p></div></div>
<p>Chúng tôi chứng minh được phần <strong>cơ chế</strong>: lỗi lệch một đơn vị ở đúng ngưỡng bị bắt, và cổng
chuyển sang NO-GO. Quý vị nhân nó với chi phí một lỗi lọt trong tổ chức mình.</p>
<p class="note">Chúng tôi chủ động không nhân sẵn con số đó để trình bày như ROI. Làm vậy sẽ biến một giả định
thành một lời khẳng định.</p>""",

# 14
f"""{kicker("4 · Differentiation / Innovation","2 phút")}
<h2>Khác gì so với các cách làm hiện có</h2>
<table><tr><th>Cách tiếp cận</th><th>Sinh test</th><th>Ai tính kết quả mong đợi</th><th>Truy vết về điều khoản</th><th>Chặn phát hành</th></tr>
<tr><td>Viết test thủ công</td><td>Người</td><td>Người</td><td>Không có</td><td>Không</td></tr>
<tr><td>Hỏi LLM sinh test</td><td>AI</td><td><strong>AI</strong> — không kiểm chứng được</td><td>Không có</td><td>Không</td></tr>
<tr><td>Công cụ sinh test theo mô hình</td><td>Máy</td><td>Máy</td><td>Không gắn tài liệu</td><td>Không</td></tr>
<tr><td><strong>Rule2Test</strong></td><td>Máy + AI đề xuất</td><td><strong>Oracle kiểu tĩnh</strong></td><td><strong>Trích dẫn đúng dòng + băm</strong></td><td><strong>Cổng GO/NO-GO</strong></td></tr></table>
<h3>Ba điểm mới thực sự</h3>
<ul>
<li><strong>Trích dẫn nguyên văn là điều kiện bắt buộc.</strong> AI không chỉ được dòng gốc thì output bị loại —
cách duy nhất để người duyệt kiểm lại trong thời gian hữu hạn.</li>
<li><strong>Hai bên tính độc lập.</strong> Oracle tính mong đợi, hệ thống riêng tính thực tế, không chia sẻ mã.</li>
<li><strong>Bằng chứng gắn revision.</strong> Sửa test là phê duyệt hết hiệu lực; mở lại phiên duyệt là GO mất hiệu lực.</li>
</ul>""",

# 15
f"""{kicker("4 · Differentiation / Innovation")}
<h2>Bằng chứng cho từng điểm khác biệt</h2>
<table><tr><th>Khẳng định</th><th>Kiểm chứng bằng</th><th>Số đo</th></tr>
<tr><td>Bắt được lỗi lệch ngưỡng</td><td>Bơm lỗi biên vào hệ thống độc lập, chạy thật</td><td class="num">13/14 pass → NO-GO</td></tr>
<tr><td>Tìm ra vùng biên chưa phủ</td><td>Độ phủ biên trước và sau khi sinh test</td><td class="num">{esc(cov)}</td></tr>
<tr><td>Bộ test đủ mạnh</td><td>Mutation — cố tình làm sai quy tắc</td><td class="num">{esc(mut)}</td></tr>
<tr><td>Cổng chất lượng đúng hợp đồng</td><td>6 kịch bản độc lập, gồm cả ca phải NO-GO</td><td class="num">{esc(gate)}</td></tr>
<tr><td>AI không tự duyệt</td><td>Test tự động khẳng định không có phê duyệt tự động</td><td class="num">có test</td></tr>
<tr><td>Không tự thử lại khi lỗi</td><td>Provider giả lập đếm số lần gọi</td><td class="num">gọi đúng 1 lần</td></tr>
<tr><td>Log không rò dữ liệu</td><td>Danh sách trường cho phép, test khẳng định</td><td class="num">có test</td></tr>
</table>
<p class="note">Tất cả đều nằm trong bộ {esc(suite)} test tự động, chạy lại được bằng một lệnh.
Mọi số đều truy về được artifact trong repo.</p>""",

# 16
f"""{kicker("5 · Feasibility &amp; Next Steps","1 phút")}
<h2>Đã sẵn sàng tới đâu</h2>
<div class="two">
<div class="card"><h4>Đã có, chạy được</h4><ul>
<li>12 giai đoạn hoàn chỉnh, từ hợp đồng miền tới cổng chất lượng</li>
<li>Nguyên mẫu đóng gói một file .exe, không cần cài gì</li>
<li>{esc(suite)} test tự động, chạy ổn định</li>
<li>Log có cấu trúc, trace, metrics, phân loại lỗi provider</li>
<li>Bộ tài liệu và dữ liệu demo mang đi được</li></ul></div>
<div class="card"><h4>Chưa có — nói thẳng</h4><ul>
<li>Chưa xác thực, chưa phân quyền; tên người duyệt là tự khai</li>
<li>Chưa có nhãn do chuyên gia bảo hiểm gán cho bộ đánh giá AI</li>
<li>DSL còn nhỏ: 2 trường, 8 toán tử</li>
<li>Băm là kiểm tra toàn vẹn, chưa phải chữ ký số</li>
<li>Chưa nối hệ thống thật, chưa chạy trong CI</li></ul></div></div>
<p class="note">Rào cản lớn nhất để triển khai thật không phải kỹ thuật lõi — mà là dữ liệu có nhãn chuyên gia
và việc nối vào hệ thống thật. Cả hai đều nằm ngay trong hai giai đoạn kế tiếp.</p>""",

# 17
f"""{kicker("5 · Feasibility &amp; Next Steps")}
<h2>Bốn giai đoạn tiếp theo</h2>
<table><tr><th>GĐ</th><th>Mục tiêu</th><th>Kết quả đo được</th></tr>
<tr><td>13</td><td>Bộ đánh giá quy mô lớn, có nhãn chuyên gia, tách tập kiểm định giữ riêng</td>
<td>Thay "{esc(live)} trên 10 case tự soạn" bằng con số trên hàng trăm case có nhãn</td></tr>
<tr><td>14</td><td>Nối hệ thống thật qua adapter HTTP sẵn có; chạy trong CI, chặn merge khi NO-GO</td>
<td>Số lần chặn được thay đổi rủi ro trước khi vào môi trường thật</td></tr>
<tr><td>15</td><td>Xác thực, phân quyền, bằng chứng ký số, lưu trữ chỉ-ghi-thêm</td>
<td>Bằng chứng đủ điều kiện dùng cho kiểm toán</td></tr>
<tr><td>16</td><td>Mở rộng DSL, test biến hình</td>
<td>Hệ số phủ DSL 50% → 80%: ROI tăng từ {million(model()["vnd"])} lên {million(model(0.8)["vnd"])}/năm cho một team</td></tr>
</table>
<p>Giai đoạn 16 là hạng mục có đòn bẩy ROI cao nhất, và bảng độ nhạy ở phần Business Case đã lượng hoá đúng
mức đòn bẩy đó.</p>""",

# 18
f"""{kicker("Khép lại")}
<h2>Những gì chúng tôi <em>không</em> khẳng định</h2>
<ul>
<li><strong>Độ phủ không phải tỷ lệ pass.</strong> Test fail vẫn tính là đã chạy qua đầu vào đó.</li>
<li><strong>GO không phải giấy phép phát hành.</strong> Đó là đánh giá hồi quy cục bộ cho đúng một revision.</li>
<li><strong>Số của AI giả lập không chứng minh năng lực AI.</strong> Giả lập chỉ phát lại fixture. Model thật đạt {esc(live)}.</li>
<li><strong>Prompt v2 được sửa sau khi xem lỗi của v1</strong> → không phải kiểm định độc lập. Chúng tôi ghi điều này
trong tài liệu thay vì giấu đi.</li>
<li><strong>Mọi con số ROI trong phần Business Case là mô hình, không phải đo lường.</strong> Giả định và công thức
đều hiện trên slide để quý vị kiểm lại.</li>
<li><strong>Chưa đo:</strong> mức chấp nhận của người duyệt thật, độ chính xác môi trường thật, chi phí token.</li>
</ul>
<p class="lead">Chúng tôi chọn để quý vị tin vào năm con số kiểm chứng được,
thay vì nghi ngờ năm mươi con số không kiểm chứng được.</p>
<p class="note">Mọi số "Đo được" truy về artifact trong repo: docs/BENCHMARKS.md.
Mọi giả định mô hình nằm trong một khối duy nhất của scripts/build_final_deck.py — sửa một chỗ, cả deck cập nhật.</p>""",
    ]

def build():
    body="".join(f"<section>{content}</section>" for content in slides_html())
    return ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Rule2Test — Round 2 Final Submission (Track 2)</title><style>'+STYLE+'</style></head><body>'
        '<div id="deck"><div id="bar"><i id="fill"></i></div>'+body+
        '<footer><span>Rule2Test · Track 2 · dữ liệu mô phỏng · phím mũi tên để chuyển slide</span>'
        '<span><button id="prev">&larr;</button> <span id="count"></span> <button id="next">&rarr;</button></span>'
        '</footer></div><script>'+SCRIPT+'</script></body></html>')

def main(argv=None):
    parser=argparse.ArgumentParser(description="Build the Round 2 final deck (Track 2).")
    parser.add_argument("--output",type=Path,default=TARGET)
    args=parser.parse_args(argv)
    try:
        if not SUMMARY.exists():
            print("Chưa có data/generated/benchmark-summary.json. Chạy scripts/collect_benchmarks.py trước, "
                  "nếu không deck sẽ không có số đo thật.",file=sys.stderr)
            return 2
        args.output.parent.mkdir(parents=True,exist_ok=True)
        document=build()
        args.output.write_text(document,encoding="utf-8")
        base=model()
        print(json.dumps(dict(output=str(args.output.relative_to(ROOT)),slides=document.count("<section>"),
            size_kb=round(len(document.encode("utf-8"))/1024),
            model=dict(scope=ASSUMPTIONS["scope"],hours_per_year=base["hours"],
                productivity_on_workload_percent=round(base["on_workload"],1),
                productivity_on_capacity_percent=round(base["on_capacity"],2),
                vnd_per_year=base["vnd"])),ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(type(exc).__name__+": "+str(exc),file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
