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
def site_post(lang: str, title: str, html: str, excerpt: str, tags: list[str], cta: str = "") -> str:
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
    (folder / f"{d}-brief.html").write_text(f"{front}\n{body}\n", encoding="utf-8")
    base = os.environ.get("SITE_URL", "").rstrip("/")
    return f"{base}/{lang}/{d:%Y/%m/%d}/brief/"


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


# ---------- Threads ----------
THREADS_API = "https://graph.threads.net/v1.0"


def threads_post(text: str) -> str:
    user_id, token = os.environ["THREADS_USER_ID"], os.environ["THREADS_ACCESS_TOKEN"]
    r = requests.post(f"{THREADS_API}/{user_id}/threads", timeout=TIMEOUT,
                      params={"media_type": "TEXT", "text": text, "access_token": token})
    r.raise_for_status()
    time.sleep(5)  # Meta 권장: 컨테이너 생성 후 잠시 대기
    r = requests.post(f"{THREADS_API}/{user_id}/threads_publish", timeout=TIMEOUT,
                      params={"creation_id": r.json()["id"], "access_token": token})
    r.raise_for_status()
    return r.json()["id"]


def threads_token_days_left() -> int | None:
    """토큰 만료까지 남은 일수 (확인 실패 시 None)."""
    try:
        r = requests.get("https://graph.threads.net/v1.0/debug_token", timeout=TIMEOUT,
                         params={"input_token": os.environ["THREADS_ACCESS_TOKEN"],
                                 "access_token": os.environ["THREADS_ACCESS_TOKEN"]})
        expires = r.json()["data"]["expires_at"]
        return int((expires - time.time()) // 86400) if expires else None
    except Exception:
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
