"""인스타그램 + 스레드 게시 (채널별로 실패해도 다른 채널은 계속 진행)."""
import os

from . import publish


def post_social(content: dict, card_urls: list[str], blog_url: str) -> dict:
    results = {}
    if card_urls:
        publish.wait_until_live(card_urls)

    if os.environ.get("INSTAGRAM_ACCESS_TOKEN"):
        try:
            results["instagram"] = publish.instagram_carousel(card_urls, content["instagram_caption_ko"])
        except Exception as e:
            results["instagram_error"] = str(e)[:300]

    if os.environ.get("THREADS_ACCESS_TOKEN"):
        try:
            link = f"\n\n전문 👉 {blog_url}" if blog_url else ""
            text = content["threads_ko"][: 500 - len(link)] + link
            results["threads"] = publish.threads_post(text, card_urls)
        except Exception as e:
            results["threads_error"] = str(e)[:300]

    print(f"[social] {results}")
    return results
