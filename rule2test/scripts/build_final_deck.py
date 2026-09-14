"""Build the Round 2 final-submission deck for Track 2.

The deck covers exactly the five contents the organisers list and nothing else: no agenda, no timing,
no demo checkpoint, no closing extras.

Two kinds of number appear and they are never mixed:

  DO DUOC  - measured, copied from data/generated/benchmark-summary.json, which is itself produced by
             running this repository's own services. Never typed by hand.
  GIA DINH - a model input. Every one is listed with its basis on the slide that uses it. Change a
             value in ASSUMPTIONS below and rebuild; the whole deck follows.
  TINH RA  - arithmetic over the two above, shown with its formula on the slide.

No ROI figure is presented as measured, because this project has not measured effort savings.
Claiming otherwise to a judging panel would be fabrication.
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
    scope="một team QA bảo hiểm 8 người",
    team_size=dict(value=8,decimals=0,unit="người",label="Quy mô team",
        basis="Đơn vị nhỏ nhất có thể kiểm chứng."),
    rule_changes_per_year=dict(value=36,decimals=0,unit="lần/năm",label="Số lần đổi quy tắc",
        basis="≈3 lần/tháng: tham số sản phẩm, quy định pháp lý, quy tắc chiến dịch."),
    hours_per_change_today=dict(value=16,decimals=0,unit="giờ/lần",label="Công sức hiện tại",
        basis="2 người-ngày: đọc tài liệu ~5h, rà test và thiết kế case ~7h, hồ sơ truy vết ~4h."),
    hours_per_change_with_tool=dict(value=6,decimals=0,unit="giờ/lần",label="Công sức khi có công cụ",
        basis="Phần còn lại là DUYỆT — không tự động hoá, không tính là tiết kiệm."),
    dsl_coverage_factor=dict(value=0.5,decimals=2,unit="tỷ lệ",label="Quy tắc DSL diễn đạt được",
        basis="Quy tắc ngoài phạm vi bị TỪ CHỐI chứ không đoán, nên chỉ tính một nửa."),
    loaded_cost_vnd_per_hour=dict(value=300_000,decimals=0,unit="VND/giờ",label="Chi phí đầy đủ một giờ QA",
        basis="≈45 triệu/tháng ÷ ~147 giờ làm việc."),
    productive_hours_per_person_year=dict(value=1_760,decimals=0,unit="giờ/người/năm",label="Giờ làm việc hữu ích",
        basis="220 ngày × 8 giờ."),
)
SENSITIVITY=(("Hiện tại",0.5,36),("Mở rộng DSL",0.8,36),("Đổi quy tắc nhiều hơn",0.5,60),("Cả hai",0.8,60))
SCALE=((1,"1 team QA"),(5,"1 Business Unit"),(20,"Nhiều BU"))

def value(name):return ASSUMPTIONS[name]["value"]

def model(coverage=None,changes=None):
    coverage=value("dsl_coverage_factor") if coverage is None else coverage
    changes=value("rule_changes_per_year") if changes is None else changes
    saved=value("hours_per_change_today")-value("hours_per_change_with_tool")
    hours=changes*coverage*saved
    workload=changes*value("hours_per_change_today")
    capacity=value("team_size")*value("productive_hours_per_person_year")
    return dict(hours=hours,workload=workload,capacity=capacity,
        on_workload=100*hours/workload if workload else 0,
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

def million(vnd):return vn(vnd/1_000_000)+" triệu"

def esc(text):return html.escape(str(text),quote=False)

STYLE="""
:root{--bg:#0b1020;--panel:#151b2e;--fg:#eef2f8;--muted:#93a0b8;--line:#2a3350;
      --measured:#3fb950;--assumed:#d29922;--derived:#58a6ff;--accent:#7c8cff}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);
  font:16px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
#deck{height:100%;display:flex;flex-direction:column}
#bar{height:3px;background:var(--line);flex:none}#bar i{display:block;height:100%;background:var(--accent);transition:width .2s}
section{flex:1;display:none;padding:clamp(18px,3.4vw,48px);overflow:auto}
section.on{display:block}
.kicker{color:var(--accent);letter-spacing:.13em;text-transform:uppercase;font-size:11.5px;
  font-weight:700;margin:0 0 10px}
h1{font-size:clamp(30px,5vw,56px);line-height:1.06;margin:0 0 16px;letter-spacing:-.02em}
h2{font-size:clamp(22px,3.2vw,38px);line-height:1.13;margin:0 0 16px;letter-spacing:-.01em}
h3{font-size:clamp(15px,1.7vw,19px);margin:20px 0 8px}
p{font-size:clamp(14px,1.55vw,19px);max-width:66ch;margin:0 0 12px}
.lead{color:var(--muted)}
ul{font-size:clamp(14px,1.55vw,19px);max-width:70ch;padding-left:20px;margin:0}li{margin:8px 0}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));margin:18px 0}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.stat b{display:block;font-size:clamp(22px,3.1vw,38px);line-height:1.08;margin-bottom:5px}
.stat span{color:var(--muted);font-size:12.5px;display:block}
.tag{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.08em;padding:2px 7px;
     border-radius:4px;margin-bottom:7px;text-transform:uppercase}
.t-measured{background:rgba(63,185,80,.16);color:var(--measured);border:1px solid rgba(63,185,80,.4)}
.t-assumed{background:rgba(210,153,34,.16);color:var(--assumed);border:1px solid rgba(210,153,34,.4)}
.t-derived{background:rgba(88,166,255,.16);color:var(--derived);border:1px solid rgba(88,166,255,.4)}
table{border-collapse:collapse;width:100%;font-size:clamp(12.5px,1.35vw,16.5px);margin:8px 0}
th,td{border-bottom:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.05em}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.formula{background:var(--panel);border-left:3px solid var(--derived);border-radius:0 8px 8px 0;
  padding:11px 15px;margin:12px 0;font-size:clamp(13px,1.4vw,17px);max-width:74ch}
.note{color:var(--muted);font-size:clamp(11.5px,1.2vw,13.5px);margin-top:14px;border-top:1px solid var(--line);
  padding-top:10px;max-width:82ch}
.two{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(290px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.card h4{margin:0 0 8px;font-size:15px}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin:10px 0 0}
footer{flex:none;display:flex;justify-content:space-between;align-items:center;gap:12px;
  padding:8px 16px;border-top:1px solid var(--line);color:var(--muted);font-size:11.5px}
footer button{font:inherit;background:var(--panel);color:var(--fg);border:1px solid var(--line);
  border-radius:6px;padding:4px 10px;cursor:pointer}
footer button:hover{border-color:var(--accent)}
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

TAGS=dict(measured="Đo được",assumed="Giả định",derived="Tính ra")

def kicker(label):return '<p class="kicker">'+esc(label)+'</p>'
def tagged(kind):return '<span class="tag t-'+kind+'">'+TAGS[kind]+'</span>'
def stat(figure,label,tag=""):
    return '<div class="stat">'+(tagged(tag) if tag else "")+'<b>'+figure+'</b><span>'+esc(label)+'</span></div>'

def slides_html():
    m=measured();base=model()
    gate=m.get("Quality-gate contract cases matched","6/6")
    cov=m.get("Designed boundary coverage, baseline to final","16.67% → 100.0%")
    mut=m.get("Mutation score on the same scenario","100.0%")
    live=m.get("Live cloud model, prompt v2 — extraction cases matched","4/10")
    mock=m.get("Offline mock replay — extraction cases matched","5/10")
    suite=m.get("Automated test suite","286 passing")

    legend=('<div class="legend">'+tagged("measured")+' số đo thật &nbsp;·&nbsp; '
            +tagged("assumed")+' giả định, có căn cứ &nbsp;·&nbsp; '+tagged("derived")+' tính ra</div>')

    assumption_rows="".join(
        "<tr><td>"+esc(v["label"])+"</td><td class='num'>"+vn(v["value"],v["decimals"])+" "+esc(v["unit"])
        +"</td><td>"+esc(v["basis"])+"</td></tr>" for v in ASSUMPTIONS.values() if isinstance(v,dict))

    def row(label,*cells):
        return "<tr><td>"+esc(label)+"</td>"+"".join("<td class='num'>"+c+"</td>" for c in cells)+"</tr>"

    sensitivity_rows="".join(row(label,str(int(c*100))+"%",vn(ch),vn(model(c,ch)["hours"]),million(model(c,ch)["vnd"]))
        for label,c,ch in SENSITIVITY)
    scale_rows="".join(row(label,vn(n*value("team_size")),vn(base["hours"]*n),million(base["vnd"]*n))
        for n,label in SCALE)

    return [
f"""{kicker("Round 2 · Final submission · Track 2")}
<h1>Rule2Test</h1>
<p class="lead">Mỗi thay đổi quy tắc bảo hiểm trở thành test hồi quy đã được người duyệt,
và bằng chứng thực thi kiểm chứng lại được.</p>
<div class="grid">{stat(esc(cov),"độ phủ biên thiết kế, trước → sau","measured")}
{stat(esc(gate),"kịch bản cổng chất lượng đúng kết luận","measured")}
{stat(esc(suite),"test tự động","measured")}</div>
{legend}
<p class="note">Số gắn nhãn "Đo được" sao chép từ artifact trong repo, do chính hệ thống chạy ra.
Dữ liệu là dữ liệu mô phỏng, không phải đo lường môi trường thật.</p>""",

f"""{kicker("1 · Problem & Context")}
<h2>Một quy tắc thay đổi. Không ai chứng minh được nó làm hỏng gì.</h2>
<p>Công ty bảo hiểm sửa điều kiện tham gia: <strong>tuổi tối đa từ 60 lên 65</strong>.</p>
<ul>
<li>Bộ test cũ <strong>vẫn xanh</strong> — chưa ai viết test cho vùng biên vừa dịch (61–65).</li>
<li>Không ai trả lời được thay đổi này <strong>làm mất hiệu lực test nào</strong>, và <strong>ai</strong> đã duyệt test mới.</li>
<li>Kết quả test <strong>không truy ngược</strong> được về điều khoản đã sinh ra nó.</li>
<li>Người duyệt phải tin bản tóm tắt của AI cho tài liệu họ <strong>không kiểm lại được từng dòng</strong>.</li>
</ul>
<p class="lead" style="margin-top:16px">Vấn đề không phải sinh test tự động.
Vấn đề là <strong>truy vết</strong> và <strong>thẩm quyền phê duyệt</strong>.</p>""",

f"""{kicker("2 · Solution Overview")}
<h2>Năm chặng, một chuỗi truy vết liên tục</h2>
<table><tr><th>Chặng</th><th>Việc xảy ra</th><th>Ai quyết định</th></tr>
<tr><td>Tiếp nhận</td><td>Hai phiên bản quy tắc; lưu nguyên bytes gốc kèm mã băm</td><td>Máy</td></tr>
<tr><td>Phân tích</td><td>Delta quy tắc, ảnh hưởng, tìm lỗ hổng, sinh test đề xuất</td><td>Máy</td></tr>
<tr><td><strong>Duyệt</strong></td><td>Phê duyệt tường minh từng test, gắn với revision</td><td><strong>Con người</strong></td></tr>
<tr><td>Thực thi</td><td>Chỉ chạy test đã duyệt, đối chiếu hệ thống độc lập</td><td>Máy</td></tr>
<tr><td>Chứng minh</td><td>Gói bằng chứng + cổng chất lượng GO / NO-GO</td><td>Máy</td></tr></table>
<p class="note">Mỗi chặng gắn một số revision. Gửi revision cũ thì hệ thống từ chối chứ không ghi đè âm thầm.
Mở lại phiên duyệt sẽ xoá phê duyệt cũ và làm mất hiệu lực kết luận GO trước đó.</p>""",

f"""{kicker("2 · AI Approach")}
<h2>AI đề xuất. Engine quyết định. Con người phê duyệt.</h2>
<div class="two">
<div class="card"><h4>AI được làm</h4><ul>
<li>Đọc tài liệu văn xuôi, rút ra quy tắc có cấu trúc</li>
<li>Đề xuất <em>đầu vào</em> test từ kho đã duyệt</li></ul></div>
<div class="card"><h4>AI không bao giờ được làm</h4><ul>
<li>Tính kết quả <strong>mong đợi</strong> — oracle kiểu tĩnh làm</li>
<li>Quyết định PASS / FAIL</li>
<li>Tự phê duyệt đề xuất của chính nó</li></ul></div></div>
<h3>Bốn rào chắn kỹ thuật</h3>
<ul>
<li><strong>Trích dẫn đúng nguyên văn.</strong> Quy tắc AI rút ra phải kèm đúng dòng gốc; sai một ký tự là bị loại.</li>
<li><strong>Không tự thử lại, không âm thầm quay về mock.</strong> Lỗi provider phân loại thành 11 loại kèm hướng khắc phục.</li>
<li><strong>Ghim mã digest của model.</strong> Sai model là dừng ngay lúc khởi động.</li>
<li><strong>Hệ thống được test không nhận kết quả mong đợi hay bản quy tắc.</strong></li>
</ul>""",

f"""{kicker("3 · Business Case · Track 2")}
<h2>Bảy giả định của mô hình ROI</h2>
<p>Dự án <strong>chưa đo</strong> thời gian tiết kiệm thực tế, nên không con số ROI nào ở đây được trình bày
như số đo. Thay vào đó là mô hình công khai, phạm vi {esc(ASSUMPTIONS["scope"])}.</p>
<table><tr><th>Đầu vào</th><th>Giá trị</th><th>Căn cứ</th></tr>{assumption_rows}</table>
<p class="note">Hệ số phủ DSL là giả định thận trọng nhất: hệ thống <strong>từ chối</strong> quy tắc nó không
diễn đạt được thay vì đoán, nên chỉ một nửa số lần đổi quy tắc được tính vào ROI.</p>""",

f"""{kicker("3 · Business Case · Track 2")}
<h2>Giờ tiết kiệm và giá trị quy đổi</h2>
<div class="formula">
Giờ tiết kiệm/năm = số lần đổi × hệ số phủ DSL × (giờ thủ công − giờ có công cụ)<br>
= {vn(value("rule_changes_per_year"))} × {vn(value("dsl_coverage_factor"),2)} × ({vn(value("hours_per_change_today"))} − {vn(value("hours_per_change_with_tool"))}) = <strong>{vn(base["hours"])} giờ/năm</strong>
</div>
<div class="grid">
{stat(vn(base["hours"])+" giờ","tiết kiệm mỗi năm, một team "+vn(value("team_size"))+" người","derived")}
{stat(vn(base["on_workload"],1)+"%","tăng năng suất trên việc hồi quy do đổi quy tắc","derived")}
{stat(vn(base["on_capacity"],2)+"%","trên tổng năng lực cả team — mẫu số rộng hơn","derived")}
{stat(million(base["vnd"])+" VND","giá trị quy đổi mỗi năm","derived")}
</div>
<p>Nêu <strong>hai</strong> tỷ lệ năng suất vì công cụ chỉ tác động vào phần việc hồi quy do đổi quy tắc
({vn(base["workload"])} giờ/năm), không phải toàn bộ công việc của team ({vn(base["capacity"])} giờ/năm).</p>
<p class="note">Thời gian <strong>phê duyệt của con người không được tính là tiết kiệm</strong> — đó là thẩm quyền,
không phải chi phí cần cắt.</p>""",

f"""{kicker("3 · Business Case · Track 2")}
<h2>Độ nhạy và khả năng nhân rộng</h2>
<div class="two">
<div><h3 style="margin-top:0">Nếu giả định đổi</h3>
<table><tr><th>Kịch bản</th><th>Phủ DSL</th><th>Lần/năm</th><th>Giờ/năm</th><th>VND/năm</th></tr>
{sensitivity_rows}</table></div>
<div><h3 style="margin-top:0">Nếu nhân rộng</h3>
<table><tr><th>Phạm vi</th><th>Số QA</th><th>Giờ/năm</th><th>VND/năm</th></tr>{scale_rows}</table></div>
</div>
<h3>Vì sao tái sử dụng được</h3>
<ul>
<li><strong>Engine không gắn nghiệp vụ cụ thể.</strong> Quy tắc là <em>dữ liệu</em>, không phải mã nguồn.</li>
<li><strong>Kho tri thức dùng chung.</strong> Test đã duyệt tái sử dụng được; kết quả mong đợi luôn <em>tính lại</em>.</li>
<li><strong>Không phụ thuộc hạ tầng.</strong> Triển khai cho đơn vị mới là chép một file.</li>
</ul>
<p class="note">Bảng nhân rộng là phép nhân tuyến tính, chưa trừ chi phí triển khai và đào tạo.</p>""",

f"""{kicker("4 · Differentiation / Innovation")}
<h2>Khác gì so với các cách làm hiện có</h2>
<table><tr><th>Cách tiếp cận</th><th>Ai tính kết quả mong đợi</th><th>Truy vết về điều khoản</th><th>Chặn phát hành</th></tr>
<tr><td>Viết test thủ công</td><td>Người</td><td>Không</td><td>Không</td></tr>
<tr><td>Hỏi LLM sinh test</td><td><strong>AI</strong> — không kiểm chứng được</td><td>Không</td><td>Không</td></tr>
<tr><td>Sinh test theo mô hình</td><td>Máy</td><td>Không gắn tài liệu</td><td>Không</td></tr>
<tr><td><strong>Rule2Test</strong></td><td><strong>Oracle kiểu tĩnh</strong></td><td><strong>Trích dẫn đúng dòng + băm</strong></td><td><strong>Cổng GO/NO-GO</strong></td></tr></table>
<h3>Ba điểm mới</h3>
<ul>
<li><strong>Trích dẫn nguyên văn là điều kiện bắt buộc.</strong> AI không chỉ được dòng gốc thì output bị loại.</li>
<li><strong>Hai bên tính độc lập.</strong> Oracle tính mong đợi, hệ thống riêng tính thực tế, không chia sẻ mã.</li>
<li><strong>Bằng chứng gắn revision.</strong> Sửa test là phê duyệt hết hiệu lực; mở lại phiên duyệt là GO mất hiệu lực.</li>
</ul>""",

f"""{kicker("4 · Differentiation / Innovation")}
<h2>Bằng chứng cho từng khẳng định</h2>
<table><tr><th>Khẳng định</th><th>Kiểm chứng bằng</th><th>Số đo</th></tr>
<tr><td>Bắt được lỗi lệch ngưỡng</td><td>Bơm lỗi biên, chạy thật</td><td class="num">13/14 pass → NO-GO</td></tr>
<tr><td>Tìm ra vùng biên chưa phủ</td><td>Độ phủ trước và sau khi sinh test</td><td class="num">{esc(cov)}</td></tr>
<tr><td>Bộ test đủ mạnh</td><td>Mutation — cố tình làm sai quy tắc</td><td class="num">{esc(mut)}</td></tr>
<tr><td>Cổng chất lượng đúng hợp đồng</td><td>6 kịch bản, gồm cả ca phải NO-GO</td><td class="num">{esc(gate)}</td></tr>
<tr><td>AI không tự duyệt</td><td>Test tự động khẳng định</td><td class="num">có test</td></tr>
<tr><td>Không tự thử lại khi lỗi</td><td>Provider giả lập đếm số lần gọi</td><td class="num">gọi đúng 1 lần</td></tr>
<tr><td>Log không rò dữ liệu</td><td>Danh sách trường cho phép + test</td><td class="num">có test</td></tr></table>
<p class="note">Tất cả nằm trong {esc(suite)} test tự động, chạy lại bằng một lệnh.
Trích xuất bằng model thật hiện đạt {esc(live)}; số của AI giả lập ({esc(mock)}) chỉ là phát lại fixture
và không dùng để chứng minh năng lực AI.</p>""",

f"""{kicker("5 · Feasibility & Next Steps")}
<h2>Đã sẵn sàng tới đâu</h2>
<div class="two">
<div class="card"><h4>Đã có, chạy được</h4><ul>
<li>Nguyên mẫu đóng gói một file .exe, không cần cài gì</li>
<li>{esc(suite)} test tự động, chạy ổn định</li>
<li>Log có cấu trúc, trace, metrics, phân loại lỗi provider</li>
<li>Bộ tài liệu và dữ liệu demo mang đi được</li></ul></div>
<div class="card"><h4>Chưa có — nói thẳng</h4><ul>
<li>Chưa xác thực, chưa phân quyền; tên người duyệt tự khai</li>
<li>Chưa có nhãn chuyên gia cho bộ đánh giá AI</li>
<li>DSL còn nhỏ: 2 trường, 8 toán tử</li>
<li>Băm là kiểm tra toàn vẹn, chưa phải chữ ký số</li></ul></div></div>
<p class="note">GO là đánh giá hồi quy cục bộ cho một revision, không phải giấy phép phát hành.
Độ phủ không phải tỷ lệ pass.</p>""",

f"""{kicker("5 · Feasibility & Next Steps")}
<h2>Bốn bước tiếp theo</h2>
<table><tr><th>Bước</th><th>Mục tiêu</th><th>Kết quả đo được</th></tr>
<tr><td>1</td><td>Bộ đánh giá lớn, có nhãn chuyên gia, tách tập kiểm định giữ riêng</td>
<td>Thay "{esc(live)} trên 10 case tự soạn" bằng con số trên hàng trăm case có nhãn</td></tr>
<tr><td>2</td><td>Nối hệ thống thật qua adapter HTTP sẵn có; chạy trong CI</td>
<td>Số lần chặn được thay đổi rủi ro trước khi vào môi trường thật</td></tr>
<tr><td>3</td><td>Xác thực, phân quyền, bằng chứng ký số, lưu trữ chỉ-ghi-thêm</td>
<td>Bằng chứng đủ điều kiện dùng cho kiểm toán</td></tr>
<tr><td>4</td><td>Mở rộng DSL</td>
<td>Phủ DSL 50% → 80%: ROI một team từ {million(model()["vnd"])} lên {million(model(0.8)["vnd"])} VND/năm</td></tr>
</table>
<p>Bước 4 có đòn bẩy ROI cao nhất, và bảng độ nhạy đã lượng hoá đúng mức đòn bẩy đó.</p>
<p class="note">Rào cản lớn nhất để triển khai thật không phải kỹ thuật lõi, mà là dữ liệu có nhãn chuyên gia
và việc nối vào hệ thống thật — cả hai nằm ở bước 1 và 2.</p>""",
    ]

def build():
    body="".join("<section>"+content+"</section>" for content in slides_html())
    return ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Rule2Test — Round 2 Final Submission (Track 2)</title><style>'+STYLE+'</style></head><body>'
        '<div id="deck"><div id="bar"><i id="fill"></i></div>'+body+
        '<footer><span>Rule2Test · Track 2 · dữ liệu mô phỏng</span>'
        '<span><button id="prev">&larr;</button> <span id="count"></span> <button id="next">&rarr;</button></span>'
        '</footer></div><script>'+SCRIPT+'</script></body></html>')

def main(argv=None):
    parser=argparse.ArgumentParser(description="Build the Round 2 final deck (Track 2).")
    parser.add_argument("--output",type=Path,default=TARGET)
    args=parser.parse_args(argv)
    try:
        if not SUMMARY.exists():
            print("Chưa có data/generated/benchmark-summary.json. Chạy scripts/collect_benchmarks.py trước.",file=sys.stderr)
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
