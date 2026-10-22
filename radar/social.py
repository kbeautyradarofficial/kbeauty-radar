"""인스타그램 + 스레드 게시 (채널별로 실패해도 다른 채널은 계속 진행).

인스타그램은 신생 계정 스팸 제한을 피하려고 속도를 제한합니다:
- 하루(KST) 최대 IG_DAILY_LIMIT 건, 게시 간격 최소 IG_MIN_GAP_HOURS 시간
- '활동 제한(action is blocked)' 응답을 받으면 IG_BLOCK_PAUSE_HOURS 시간 자동 일시정지
- 상태는 output/instagram_state.json 에 저장 (워크플로가 커밋)
실패한 채널은 기록해 두었다가 retry_failed() 로 하루 한 번까지만 다시 시도합니다.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import publish

CHANNELS = ("instagram", "threads")
MAX_RETRIES = 6
KST = timezone(timedelta(hours=9))
IG_STATE = Path("output/instagram_state.json")
IG_DAILY_LIMIT = 2
IG_MIN_GAP_HOURS = 3
IG_BLOCK_PAUSE_HOURS = 48
DEFERRED = "deferred"


def now_kst() -> datetime:
    return datetime.now(KST)


def _ig_state() -> dict:
    if IG_STATE.exists():
        return json.loads(IG_STATE.read_text(encoding="utf-8"))
    return {"paused_until": None, "posts": []}


def _save_ig_state(state: dict) -> None:
    state["posts"] = state["posts"][-50:]
    IG_STATE.parent.mkdir(parents=True, exist_ok=True)
    IG_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def instagram_blocked_reason() -> str | None:
    """지금 인스타그램에 올리면 안 되는 이유. 올려도 되면 None."""
    state, now = _ig_state(), now_kst()
    if state.get("paused_until") and now < datetime.fromisoformat(state["paused_until"]):
        return f"paused until {state['paused_until']}"
    posts = [datetime.fromisoformat(p) for p in state["posts"]]
    if sum(p.date() == now.date() for p in posts) >= IG_DAILY_LIMIT:
        return f"daily limit {IG_DAILY_LIMIT}"
    if posts and now - max(posts) < timedelta(hours=IG_MIN_GAP_HOURS):
        return f"min gap {IG_MIN_GAP_HOURS}h"
    return None


def _post_instagram(card_urls: list[str], caption: str) -> dict:
    reason = instagram_blocked_reason()
    if reason:
        return {"instagram_error": f"{DEFERRED}: {reason}"}
    state = _ig_state()
    try:
        post_id = publish.instagram_carousel(card_urls, caption)
    except Exception as e:
        msg = str(e)
        if "2207051" in msg or "action is blocked" in msg:
            state["paused_until"] = (now_kst() + timedelta(hours=IG_BLOCK_PAUSE_HOURS)).isoformat(timespec="minutes")
            print(f"[social] instagram action blocked -> paused until {state['paused_until']}")
        state["posts"].append(now_kst().isoformat(timespec="minutes"))  # 실패한 시도도 간격 계산에 포함
        _save_ig_state(state)
        return {"instagram_error": msg[:300]}
    state["posts"].append(now_kst().isoformat(timespec="minutes"))
    _save_ig_state(state)
    return {"instagram": post_id}


def post_social(content: dict, card_urls: list[str], blog_url: str, channels=CHANNELS) -> dict:
    results = {}
    if card_urls:
        publish.wait_until_live(card_urls)

    if "instagram" in channels and os.environ.get("INSTAGRAM_ACCESS_TOKEN"):
        results.update(_post_instagram(card_urls, content["instagram_caption_ko"]))

    if "threads" in channels and os.environ.get("THREADS_ACCESS_TOKEN"):
        try:
            link = f"\n\n전문 👉 {blog_url}" if blog_url else ""
            text = content["threads_ko"][: 500 - len(link)] + link
            results["threads"] = publish.threads_post(text, card_urls)
        except Exception as e:
            results["threads_error"] = str(e)[:300]

    print(f"[social] {results}")
    return results


def failed_channels(social: dict | None) -> list[str]:
    social = social or {}
    return [ch for ch in CHANNELS if f"{ch}_error" in social and ch not in social]


def instagram_pending(record: dict) -> bool:
    """인스타그램에 아직 안 올라간 게시물인지 (보류·실패 포함)."""
    social = record.get("social") or {}
    return "instagram" not in social and record.get("ig_attempts", 0) < 3


def post_instagram_for(record: dict, card_urls: list[str]) -> bool:
    """이미 블로그·스레드에 올라간 항목을 인스타그램에만 게시. 실제로 시도했으면 True."""
    if instagram_blocked_reason() or not instagram_pending(record):
        return False
    result = post_social(record["content"], card_urls, "", channels=("instagram",))
    social = record.setdefault("social", {})
    social.pop("instagram_error", None)
    social.update(result)
    record["ig_attempts"] = record.get("ig_attempts", 0) + 1
    return True


def retry_failed(record: dict, card_urls: list[str], blog_url: str, channels=None) -> bool:
    """실패했던 채널만 다시 게시 (항목당 하루 1번). 실제로 시도했으면 True."""
    channels = [ch for ch in failed_channels(record.get("social")) if channels is None or ch in channels]
    if "instagram" in channels and instagram_blocked_reason():
        channels.remove("instagram")  # 보류 중: 시도 횟수에 넣지 않음
    today = str(now_kst().date())
    tries = record.get("social_retries", 0)
    if not channels or tries >= MAX_RETRIES or record.get("social_retry_day") == today:
        return False
    result = post_social(record["content"], card_urls, blog_url, channels)
    social = record["social"]
    for ch in channels:
        if ch in result:
            social[ch] = result[ch]
            social.pop(f"{ch}_error", None)
        elif f"{ch}_error" in result:
            social[f"{ch}_error"] = result[f"{ch}_error"]
    if "instagram" in channels and not str(result.get("instagram_error", "")).startswith(DEFERRED):
        record["ig_attempts"] = record.get("ig_attempts", 0) + 1
    record["social_retries"] = tries + 1
    record["social_retry_day"] = today
    return True
