"""Export a slide deck to PDF, refusing to write a file in which any slide is clipped.

Printing an HTML deck silently crops whatever does not fit the page box, so a slide can lose its last
lines without anything failing. This measures every slide under print media first and reports the
overflowing ones instead of producing a quietly truncated submission.
"""
import argparse,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/"docs"/"slides"/"final-round2.html"
# 13.333in x 7.5in, the 16:9 page PowerPoint and Google Slides also use.
WIDTH="338mm"
HEIGHT="190mm"

MEASURE="""() => [...document.querySelectorAll('section')].map((s,i) => ({
  index: i + 1,
  title: (s.querySelector('h1,h2') || {}).innerText || '(no heading)',
  scroll: s.scrollHeight,
  client: s.clientHeight,
  overflow: s.scrollHeight - s.clientHeight
}))"""

def export(source,target,*,tolerance):
    from playwright.sync_api import sync_playwright
    problems=[];slides=[]
    with sync_playwright() as engine:
        browser=engine.chromium.launch()
        page=browser.new_page()
        errors=[]
        page.on("pageerror",lambda exc:errors.append(str(exc)))
        page.goto(source.resolve().as_uri())
        page.wait_for_timeout(400)
        # Measure under print media, where the page box and not the viewport decides the height.
        page.emulate_media(media="print")
        page.wait_for_timeout(250)
        slides=page.evaluate(MEASURE)
        problems=[s for s in slides if s["overflow"]>tolerance]
        if not problems:
            page.pdf(path=str(target),width=WIDTH,height=HEIGHT,print_background=True,
                     margin=dict(top="0",right="0",bottom="0",left="0"),prefer_css_page_size=True)
        browser.close()
    return slides,problems,errors

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=DEFAULT)
    parser.add_argument("--output",type=Path,help="Defaults to the source name with a .pdf suffix")
    parser.add_argument("--tolerance",type=int,default=2,help="Pixels of overflow to ignore (rounding)")
    parser.add_argument("--force",action="store_true",help="Write the PDF even if slides are clipped")
    args=parser.parse_args(argv)
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("Cần Playwright:\n  py -3 -m pip install --user -r requirements-browser.txt\n"
              "  py -3 -m playwright install chromium",file=sys.stderr)
        return 2
    source=args.source.resolve()
    if not source.is_file():
        print(f"Không thấy {source}. Chạy scripts/build_final_deck.py trước.",file=sys.stderr);return 2
    target=(args.output.resolve() if args.output else source.with_suffix(".pdf"))
    try:
        slides,problems,errors=export(source,target,tolerance=args.tolerance)
        if problems and not args.force:
            print("Không xuất PDF: các slide sau bị tràn khổ trang và sẽ bị cắt mất nội dung.",file=sys.stderr)
            for slide in problems:
                print(f"  slide {slide['index']:>2}: thừa {slide['overflow']}px — "
                      f"{slide['title'].splitlines()[0][:60]}",file=sys.stderr)
            print("Rút gọn nội dung slide, hoặc dùng --force để chấp nhận bị cắt.",file=sys.stderr)
            return 1
        if problems:
            print("CẢNH BÁO: đã xuất PDF nhưng "+str(len(problems))+" slide bị cắt.",file=sys.stderr)
        def shown(path):
            try:return str(path.relative_to(ROOT))
            except ValueError:return str(path)
        print(json.dumps(dict(source=shown(source),output=shown(target),
            slides=len(slides),page="13.33in x 7.5in (16:9)",
            megabytes=round(target.stat().st_size/1048576,2),
            clipped=len(problems),page_errors=errors),ensure_ascii=False,indent=2))
        return 0
    except Exception as exc:
        print(type(exc).__name__+": "+str(exc)[:300],file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
