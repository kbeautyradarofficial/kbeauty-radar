"""인스타그램 + 스레드 게시 (채널별로 실패해도 다른 채널은 계속 진행).

게시에 실패한 채널은 기록해 두었다가 retry_failed() 로 다음 실행 때 다시 시도합니다.
"""
import os

from . import publish

CHANNELS = ("instagram", "threads")
MAX_RETRIES = 6


def post_social(content: dict, card_urls: list[str], blog_url: str, channels=CHANNELS) -> dict:
    results = {}
    if card_urls:
        publish.wait_until_live(card_urls)

    if "instagram" in channels and os.environ.get("INSTAGRAM_ACCESS_TOKEN"):
        try:
            results["instagram"] = publish.instagram_carousel(card_urls, content["instagram_caption_ko"])
        except Exception as e:
            results["instagram_error"] = str(e)[:300]

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


def retry_failed(record: dict, card_urls: list[str], blog_url: str) -> bool:
    """실패했던 채널만 다시 게시. 기록(record['social'])을 갱신했으면 True."""
    channels = failed_channels(record.get("social"))
    tries = record.get("social_retries", 0)
    if not channels or tries >= MAX_RETRIES:
        return False
    result = post_social(record["content"], card_urls, blog_url, channels)
    social = record["social"]
    for ch in channels:
        if ch in result:
            social[ch] = result[ch]
            social.pop(f"{ch}_error", None)
        elif f"{ch}_error" in result:
            social[f"{ch}_error"] = result[f"{ch}_error"]
    record["social_retries"] = tries + 1
    return True
