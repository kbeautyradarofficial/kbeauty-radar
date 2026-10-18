"""카드뉴스(1080x1350) 이미지 생성: HTML 템플릿 -> Playwright(Chromium) 스크린샷.

디자인 원칙 (경쟁 채널 벤치마킹 결과)
- 표지: 사진 대신 '큰 숫자' 타이포 + 레이더 그래픽 → 저작권 걱정 없이 매일 자동 생성, 피드에서 눈에 띔
- 본문: 밝은 종이색 배경, 카테고리 배지, 큰 숫자 1개, '무슨 일 / 왜 중요 / 실행 포인트' 3단 구조
- 모든 장 하단에 출처 표기 + 페이지 번호, 마지막 장은 팔로우·저장 유도
"""
import html
from pathlib import Path

from . import config

W, H = 1080, 1350

LABELS = {
    "ko": {"what": "무슨 일", "why": "왜 중요", "action": "실행 포인트", "swipe": "넘겨서 보기 →",
           "source": "출처", "close_title": "매일 아침 7시,<br>K-뷰티 수출 3분 브리프",
           "close_sub": "아마존 · 틱톡샵 · 쇼피 · 해외 리테일 트렌드를<br>숫자로 빠르게 정리합니다.",
           "cta": ["팔로우", "저장", "공유"], "more": "전문과 출처 링크는 블로그에서"},
    "en": {"what": "What happened", "why": "Why it matters", "action": "Takeaway", "swipe": "Swipe →",
           "source": "Source", "close_title": "Your 3-minute<br>K-beauty export brief",
           "close_sub": "Amazon · TikTok Shop · Shopee · global retail,<br>every morning, number-first.",
           "cta": ["Follow", "Save", "Share"], "more": "Full brief & sources on the blog"},
}

CSS = """
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
:root{--navy:#0E1A3A;--navy2:#1B2C5E;--mint:#3EE6C1;--coral:#FF6B5B;--paper:#F6F4EF;--ink:#14161C;--gray:#6B7080;--line:#E3DFD6}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1350px;overflow:hidden}
body{font-family:Pretendard,'Malgun Gothic','Apple SD Gothic Neo',sans-serif;letter-spacing:-0.025em;word-break:keep-all;-webkit-font-smoothing:antialiased}
.card{width:1080px;height:1350px;padding:84px 84px 72px;position:relative;display:flex;flex-direction:column;overflow:hidden}
.dark{background:radial-gradient(120% 90% at 85% 15%,var(--navy2) 0%,var(--navy) 60%);color:#fff}
.light{background:var(--paper);color:var(--ink)}
.top{display:flex;justify-content:space-between;align-items:center;position:relative;z-index:2}
.logo{display:flex;align-items:center;gap:14px;font-weight:800;font-size:28px;letter-spacing:.14em}
.logo i{width:22px;height:22px;border-radius:50%;border:4px solid currentColor;position:relative;display:inline-block}
.logo i:after{content:'';position:absolute;width:6px;height:6px;border-radius:50%;background:var(--coral);top:4px;left:4px}
.dark .logo{color:var(--mint)} .light .logo{color:var(--navy)}
.date{font-size:26px;font-weight:600;opacity:.7}
.radar{position:absolute;right:-260px;top:-260px;width:900px;height:900px;z-index:1}
.radar span{position:absolute;border:2px solid rgba(62,230,193,.16);border-radius:50%;inset:0;margin:auto}
.radar .sweep{border:none;background:conic-gradient(from 200deg,rgba(62,230,193,.22),transparent 60deg);}
.blip{position:absolute;width:18px;height:18px;border-radius:50%;background:var(--coral);box-shadow:0 0 0 10px rgba(255,107,91,.18);right:250px;top:330px;z-index:2}
.badge{align-self:flex-start;border:2px solid var(--mint);color:var(--mint);border-radius:999px;padding:12px 26px;font-size:28px;font-weight:700}
.hero{font-size:290px;font-weight:900;color:var(--coral);line-height:.95;letter-spacing:-0.05em;margin-top:28px}
.hero-label{font-size:34px;font-weight:600;color:#C9D2EA;margin-top:14px}
.cover-head{font-size:78px;font-weight:800;line-height:1.2;margin-top:56px}
.cover-sub{font-size:32px;color:#A9B3CF;line-height:1.45;margin-top:24px}
.foot{margin-top:auto;display:flex;justify-content:space-between;align-items:flex-end;font-size:24px;padding-top:24px}
.dark .foot{color:#8E99BA} .light .foot{color:var(--gray);border-top:2px solid var(--line)}
.foot b{color:var(--mint);font-weight:700}
.num{font-size:44px;font-weight:900;color:var(--coral)}
.cat{background:var(--navy);color:#fff;border-radius:999px;padding:10px 24px;font-size:26px;font-weight:700;margin-left:18px}
.head{font-size:66px;font-weight:800;line-height:1.22;margin-top:44px}
.stat{display:flex;align-items:baseline;gap:22px;margin-top:30px}
.stat strong{font-size:138px;font-weight:900;color:var(--coral);letter-spacing:-0.05em;line-height:1}
.stat span{font-size:30px;color:var(--gray);font-weight:600;line-height:1.3}
.rows{flex:1;padding:40px 0 24px;display:flex;flex-direction:column;justify-content:center;gap:24px}
.row{display:flex;gap:26px;align-items:flex-start;padding:32px 32px;border-radius:24px;background:#fff}
.row.act{background:var(--navy);color:#fff}
.row em{font-style:normal;flex:0 0 auto;font-size:24px;font-weight:800;padding:8px 16px;border-radius:12px;background:var(--paper);color:var(--navy);margin-top:4px}
.row.act em{background:var(--mint);color:var(--navy)}
.row p{font-size:36px;line-height:1.45;font-weight:500}
.mid{margin:auto 0;position:relative;z-index:2;display:flex;flex-direction:column}
.close-title{font-size:100px;font-weight:900;line-height:1.15}
.close-sub{font-size:36px;color:#C9D2EA;line-height:1.5;margin-top:36px}
.ctas{display:flex;gap:18px;margin-top:64px}
.ctas span{background:var(--mint);color:var(--navy);font-weight:800;font-size:34px;padding:18px 36px;border-radius:999px}
.cover-head,.head,.stat span,.hero-label,.cover-sub{white-space:pre-line}
.ctas span+span{background:transparent;color:var(--mint);border:2px solid var(--mint)}
"""

# 글자가 넘치면 data-max(px) 높이에 맞을 때까지 폰트를 줄입니다.
FIT_JS = """
for (const el of document.querySelectorAll('[data-max]')) {
  let fs = parseFloat(getComputedStyle(el).fontSize);
  while (el.scrollHeight > +el.dataset.max && fs > 18) { fs -= 2; el.style.fontSize = fs + 'px'; }
}
const card = document.querySelector('.card');
const rows = document.querySelectorAll('.row p');
let guard = 0;
while (card.scrollHeight > card.clientHeight && guard++ < 30) {
  rows.forEach(p => p.style.fontSize = (parseFloat(getComputedStyle(p).fontSize) - 1) + 'px');
}
"""


def _e(s: str) -> str:
    return html.escape(s or "")


def _page(body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"


def _logo() -> str:
    return f"<div class='logo'><i></i>{_e(config.BRAND.upper())}</div>"


def cover_html(c: dict, lang: str, date: str, sources: str, total: int) -> str:
    L = LABELS[lang]
    rings = "".join(f"<span style='width:{r}px;height:{r}px'></span>" for r in (300, 520, 740, 900))
    return _page(f"""
<div class='card dark'>
  <div class='radar'>{rings}<span class='sweep' style='width:900px;height:900px'></span></div><div class='blip'></div>
  <div class='top'>{_logo()}<div class='date'>{_e(date)}</div></div>
  <div class='mid' style='padding-top:60px'>
    <div class='badge'>{_e(c['badge'])}</div>
    <div class='hero' data-max='300'>{_e(c['hero_number'])}</div>
    <div class='hero-label'>{_e(c['hero_label'])}</div>
    <div class='cover-head' data-max='290'>{_e(c['headline'])}</div>
    <div class='cover-sub' data-max='140'>{_e(c['sub'])}</div>
  </div>
  <div class='foot'><span>{L['source']} · {_e(sources)}</span><span><b>{L['swipe']}</b> &nbsp;1/{total}</span></div>
</div>""")


def slide_html(s: dict, idx: int, lang: str, total: int) -> str:
    L = LABELS[lang]
    stat = (f"<div class='stat'><strong data-max='150'>{_e(s['stat'])}</strong><span>{_e(s['stat_label'])}</span></div>"
            if s.get("stat") else "")
    rows = "".join(
        f"<div class='row{' act' if k == 'action' else ''}'><em>{L[k]}</em><p>{_e(s[k])}</p></div>"
        for k in ("what", "why", "action"))
    return _page(f"""
<div class='card light'>
  <div class='top'><div style='display:flex;align-items:center'><span class='num'>{idx:02d}</span><span class='cat'>{_e(s['category'])}</span></div>{_logo()}</div>
  <div class='head' data-max='250'>{_e(s['headline'])}</div>
  {stat}
  <div class='rows'>{rows}</div>
  <div class='foot'><span>{L['source']} · {_e(s['source'])}</span><span>{idx + 1}/{total}</span></div>
</div>""")


def closing_html(lang: str, site: str, total: int) -> str:
    L = LABELS[lang]
    ctas = "".join(f"<span>{c}</span>" for c in L["cta"])
    return _page(f"""
<div class='card dark'>
  <div class='top'>{_logo()}<div class='date'>{total}/{total}</div></div>
  <div class='mid'>
    <div class='close-title'>{L['close_title']}</div>
    <div class='close-sub'>{L['close_sub']}</div>
    <div class='ctas'>{ctas}</div>
  </div>
  <div class='foot' style='margin-top:0'><span>{L['more']}</span><span><b>{_e(site)}</b></span></div>
</div>""")


def build_pages(cards: dict, lang: str, date: str, site: str) -> list[str]:
    slides = cards["slides"]
    total = len(slides) + 2
    sources = ", ".join(dict.fromkeys(s["source"] for s in slides))
    pages = [cover_html(cards["cover"], lang, date, sources, total)]
    pages += [slide_html(s, i + 1, lang, total) for i, s in enumerate(slides)]
    pages.append(closing_html(lang, site, total))
    return pages


def render(cards: dict, lang: str, date: str, out_dir: Path, site: str = "") -> list[Path]:
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H})
        for i, doc in enumerate(build_pages(cards, lang, date, site), start=1):
            page.set_content(doc, wait_until="networkidle")
            page.evaluate("document.fonts.ready.then(() => true)")
            page.evaluate(FIT_JS)
            path = out_dir / f"{lang}-{i:02d}.jpg"
            page.screenshot(path=str(path), type="jpeg", quality=88)
            paths.append(path)
        browser.close()
    return paths
