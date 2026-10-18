"""카드에 넣을 시각 자료: 제품 이미지 / 웹페이지 화면 캡처.

- product: 브랜드 공식 페이지·보도자료 URL → 이미지면 그대로, 웹페이지면 대표 이미지(og:image)를 가져옴
- ui: 웹페이지 URL → 모바일 화면 크기로 직접 캡처 (예: 공식몰 AI 피부 상담 화면)
가져오지 못하면 None → 카드는 시각 자료 없이 그대로 만들어짐.
"""
import base64
import re
from urllib.parse import urljoin

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}


def _data_uri(content: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(content).decode()}"


CLEAN_JS = """
// 쿠키 동의창·채팅 위젯·하단 고정 배너처럼 화면을 가리는 요소 제거
for (const el of document.querySelectorAll('body *')) {
  const s = getComputedStyle(el);
  if ((s.position === 'fixed' || s.position === 'sticky') && el.getBoundingClientRect().top > innerHeight * 0.35) el.remove();
}
document.querySelectorAll('iframe, [id*=cookie i], [class*=cookie i], [id*=consent i], [class*=consent i]')
  .forEach(e => e.remove());
"""


def product_image(url: str) -> str | None:
    from urllib.parse import urlparse
    if urlparse(url).path.strip("/") == "":
        print(f"[visuals] skip homepage URL for product image (shows logo, not product): {url}")
        return None
    try:
        r = requests.get(url, headers=UA, timeout=20)
        mime = r.headers.get("content-type", "").split(";")[0]
        if r.ok and mime.startswith("image/"):
            return _data_uri(r.content, mime) if len(r.content) < 6_000_000 else None
        if not r.ok:
            return None
        # 웹페이지면 대표 이미지(og:image / twitter:image) 사용
        m = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)',
                      r.text, re.I) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)', r.text, re.I)
        if not m:
            return None
        img = requests.get(urljoin(url, m.group(1)), headers=UA, timeout=20)
        mime = img.headers.get("content-type", "").split(";")[0]
        if img.ok and mime.startswith("image/") and len(img.content) < 6_000_000:
            return _data_uri(img.content, mime)
    except Exception as e:
        print(f"[visuals] product image failed {url}: {e}")
    return None


def ui_screenshot(browser, url: str) -> str | None:
    try:
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                  user_agent=UA["User-Agent"] + " Mobile", locale="ko-KR")
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # 슬라이드 전환 애니메이션 중간에 찍혀 흐릿해지지 않도록 애니메이션 정지
        page.add_style_tag(content="*,*::before,*::after{animation-duration:0s!important;"
                                   "transition-duration:0s!important}")
        page.wait_for_timeout(4000)  # 이미지·스크립트 로딩 대기
        page.evaluate(CLEAN_JS)
        page.wait_for_timeout(500)
        img = page.screenshot(type="jpeg", quality=82)
        ctx.close()
        if len(img) < 35_000:  # 거의 단색(빈 화면·접속 차단) → 쓰지 않음
            print(f"[visuals] screenshot looks blank, skipped: {url}")
            return None
        return _data_uri(img, "image/jpeg")
    except Exception as e:
        print(f"[visuals] screenshot failed {url}: {e}")
        return None


def resolve(browser, slide: dict) -> dict | None:
    kind, url = slide.get("visual_type", "none"), (slide.get("visual_url") or "").strip()
    if kind not in ("product", "ui") or not url.startswith("http"):
        return None
    src = product_image(url) if kind == "product" else ui_screenshot(browser, url)
    return {"kind": kind, "src": src, "credit": slide.get("visual_credit", "")} if src else None
