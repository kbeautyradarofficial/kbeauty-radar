"""발행 채널: GitHub Pages 블로그, Kit 뉴스레터, Threads, 카카오톡 나에게 보내기."""
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

TIMEOUT = 30
POSTS_DIR = Path("docs/_posts")


# ---------- GitHub Pages (Jekyll) ----------
def site_post(lang: str, title: str, html: str, excerpt: str, tags: list[str], cta: str = "",
              slug: str = "brief") -> str:
    """docs/_posts/{lang}/ 에 글 파일을 쓰고, 배포될 URL을 돌려줍니다.
    파일은 워크플로가 커밋하면 GitHub Pages가 1~2분 안에 사이트에 반영합니다."""
    d = date.today()
    folder = POSTS_DIR / lang
    folder.mkdir(parents=True, exist_ok=True)
    # JSON 문자열은 그대로 유효한 YAML이라 따옴표·특수문자 이스케이프가 안전합니다.
    front = "\n".join([
        "---",
        "layout: post",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"description: {json.dumps(excerpt[:300], ensure_ascii=False)}",
        f"categories: {lang}",
        f"lang: {lang}",
        f"tags: {json.dumps(tags, ensure_ascii=False)}",
        "---",
    ])
    # raw 블록: 본문에 {{ }} 같은 문자가 있어도 Jekyll이 해석하지 않게 함
    body = "{% raw %}\n" + html + "\n{% endraw %}\n" + cta
    (folder / f"{d}-{slug}.html").write_text(f"{front}\n{body}\n", encoding="utf-8")
    base = os.environ.get("SITE_URL", "").rstrip("/")
    return f"{base}/{lang}/{d:%Y/%m/%d}/{slug}/"


def site_posts(content: dict, cards_base: str, slug: str) -> dict:
    """한/영 블로그 글을 함께 씁니다. 글 맨 위에 표지 카드, 맨 아래에 뉴스레터 구독 문구."""
    from . import config

    urls = {}
    for lang, cta in (("ko", config.CTA_KO), ("en", config.CTA_EN)):
        if not content.get(f"body_{lang}_html"):
            continue
        form = os.environ.get(f"KIT_FORM_{lang.upper()}")
        cover = f'<p><img src="{cards_base}/{lang}-01.jpg" alt="cover" width="540"></p>\n'
        urls[f"site_{lang}"] = site_post(
            lang, content[f"title_{lang}"], cover + content[f"body_{lang}_html"], content[f"excerpt_{lang}"],
            content["tags"], cta.format(url=form) if form else "", slug)
    return urls


def wait_until_live(urls: list[str], timeout: int = 600) -> None:
    """GitHub Pages 배포가 끝나 이미지가 공개 URL로 열릴 때까지 기다립니다 (Meta가 URL로 이미지를 가져가기 때문)."""
    deadline = time.time() + timeout
    pending = list(urls)
    while pending and time.time() < deadline:
        pending = [u for u in pending if requests.head(u, timeout=TIMEOUT).status_code != 200]
        if pending:
            time.sleep(15)
    if pending:
        raise RuntimeError(f"Images not live after {timeout}s: {pending[:2]}")


# ---------- Kit 뉴스레터 ----------
def kit_broadcast(subject: str, html: str, preview: str, tag_id: str | None, send: bool) -> int:
    """Kit 브로드캐스트 생성. send=True면 10분 뒤 발송 예약, False면 초안으로 저장."""
    send_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat() if send else None
    payload = {
        "subject": subject, "content": html, "preview_text": preview[:150], "description": subject,
        "public": False, "published_at": datetime.now(timezone.utc).isoformat(), "send_at": send_at,
        "subscriber_filter": [{"all": [{"type": "tag", "ids": [int(tag_id)]}]}] if tag_id else [],
    }
    r = requests.post("https://api.kit.com/v4/broadcasts", json=payload, timeout=TIMEOUT,
                      headers={"X-Kit-Api-Key": os.environ["KIT_API_KEY"]})
    if not r.ok:
        raise RuntimeError(f"Kit API {r.status_code}: {r.text[:300]}")
    return r.json()["broadcast"]["id"]


# ---------- Meta 공통 (Instagram / Threads 게시 흐름이 같음) ----------
def _meta(method: str, url: str, token: str, **params) -> dict:
    r = requests.request(method, url, params={**params, "access_token": token}, timeout=TIMEOUT)
    if not r.ok:
        raise RuntimeError(f"Meta API {r.status_code} {url.split('/')[-1]}: {r.text[:300]}")
    return r.json()


def _wait_container(api: str, cid: str, token: str, field: str) -> None:
    """컨테이너가 FINISHED 상태가 될 때까지 대기 (이미지 처리 시간)."""
    for _ in range(30):
        status = _meta("GET", f"{api}/{cid}", token, fields=field).get(field)
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Container {cid} status {status}")
        time.sleep(4)
    raise RuntimeError(f"Container {cid} not ready")


# ---------- Instagram (Instagram 로그인 방식 API: Facebook 페이지 불필요) ----------
IG_API = "https://graph.instagram.com/v26.0"


def instagram_carousel(image_urls: list[str], caption: str) -> str:
    """JPEG 이미지 URL 2~10장으로 슬라이드 게시물을 올리고 게시물 ID를 돌려줍니다."""
    token = os.environ["INSTAGRAM_ACCESS_TOKEN"]
    ig_id = _meta("GET", f"{IG_API}/me", token, fields="user_id")["user_id"]
    children = []
    for url in image_urls[:10]:
        cid = _meta("POST", f"{IG_API}/{ig_id}/media", token, image_url=url, is_carousel_item="true")["id"]
        children.append(cid)
    for cid in children:
        _wait_container(IG_API, cid, token, "status_code")
    carousel = _meta("POST", f"{IG_API}/{ig_id}/media", token, media_type="CAROUSEL",
                     children=",".join(children), caption=caption[:2200])["id"]
    _wait_container(IG_API, carousel, token, "status_code")
    return _meta("POST", f"{IG_API}/{ig_id}/media_publish", token, creation_id=carousel)["id"]


def instagram_refresh_token() -> int | None:
    """장기 토큰 유효기간을 60일로 연장하고 남은 일수를 돌려줍니다 (매 실행마다 호출)."""
    try:
        r = _meta("GET", "https://graph.instagram.com/refresh_access_token",
                  os.environ["INSTAGRAM_ACCESS_TOKEN"], grant_type="ig_refresh_token")
        return int(r.get("expires_in", 0) // 86400)
    except Exception as e:
        print(f"[instagram] token refresh failed: {e}")
        return None


# ---------- Threads ----------
THREADS_API = "https://graph.threads.net/v1.0"


def threads_post(text: str, image_urls: list[str] | None = None) -> str:
    """텍스트(최대 500자) 게시. image_urls가 있으면 카드 이미지 슬라이드와 함께 게시."""
    token = os.environ["THREADS_ACCESS_TOKEN"]
    user = os.environ.get("THREADS_USER_ID") or _meta("GET", f"{THREADS_API}/me", token, fields="id")["id"]
    if image_urls:
        children = [_meta("POST", f"{THREADS_API}/{user}/threads", token, media_type="IMAGE",
                          image_url=u, is_carousel_item="true")["id"] for u in image_urls[:20]]
        for cid in children:
            _wait_container(THREADS_API, cid, token, "status")
        cid = _meta("POST", f"{THREADS_API}/{user}/threads", token, media_type="CAROUSEL",
                    children=",".join(children), text=text[:500])["id"]
    else:
        cid = _meta("POST", f"{THREADS_API}/{user}/threads", token, media_type="TEXT", text=text[:500])["id"]
    time.sleep(5)  # Meta 권장: 컨테이너 생성 후 잠시 대기
    return _meta("POST", f"{THREADS_API}/{user}/threads_publish", token, creation_id=cid)["id"]


def threads_refresh_token() -> int | None:
    try:
        r = _meta("GET", "https://graph.threads.net/refresh_access_token",
                  os.environ["THREADS_ACCESS_TOKEN"], grant_type="th_refresh_token")
        return int(r.get("expires_in", 0) // 86400)
    except Exception as e:
        print(f"[threads] token refresh failed: {e}")
        return None


# ---------- 카카오톡 나에게 보내기 (선택) ----------
def kakao_notify(text: str, link: str | None = None) -> None:
    rest_key, refresh = os.environ.get("KAKAO_REST_API_KEY"), os.environ.get("KAKAO_REFRESH_TOKEN")
    if not (rest_key and refresh):
        print(f"[notify] Kakao not configured. Message: {text}")
        return
    data = {"grant_type": "refresh_token", "client_id": rest_key, "refresh_token": refresh}
    if os.environ.get("KAKAO_CLIENT_SECRET"):
        data["client_secret"] = os.environ["KAKAO_CLIENT_SECRET"]
    token = requests.post("https://kauth.kakao.com/oauth/token", data=data, timeout=TIMEOUT).json()["access_token"]
    url = link or os.environ.get("SITE_URL") or "https://github.com"
    template = {"object_type": "text", "text": text[:200], "button_title": "보기",
                "link": {"web_url": url, "mobile_web_url": url}}
    r = requests.post("https://kapi.kakao.com/v2/api/talk/memo/default/send", timeout=TIMEOUT,
                      headers={"Authorization": f"Bearer {token}"},
                      data={"template_object": json.dumps(template, ensure_ascii=False)})
    r.raise_for_status()
