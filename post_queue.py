"""대기열(queue/)에서 가장 오래된 게시물 N건을 꺼내 블로그·인스타그램·스레드에 올립니다.

사용법: python post_queue.py [건수=1]
PUBLISH_MODE=auto 일 때만 SNS에 게시합니다 (draft 면 블로그에만 게시).
"""
import json
import os
import sys
from pathlib import Path

from radar import config, publish
from radar.social import post_social


def main(count: int) -> None:
    mode = os.environ.get("PUBLISH_MODE", "dry-run")
    site = os.environ.get("SITE_URL", "").rstrip("/")
    queued = [f for f in sorted(Path("queue").glob("*.json"))
              if json.loads(f.read_text(encoding="utf-8"))["status"] == "queued"]
    if not queued:
        print("[queue] empty")
        return
    for n, f in enumerate(queued[:count], start=1):
        item = json.loads(f.read_text(encoding="utf-8"))
        if mode == "dry-run":
            print(f"[queue] would post {item['id']}: {item['theme']}")
            continue
        cards_base = f"{site}/{item.get('cards_base', 'cards/archive/' + item['id'])}"
        item["published"] = publish.site_posts(item["content"], cards_base, item["id"])
        if mode == "auto":
            card_urls = [f"{site}/{p.removeprefix('docs/')}" for p in item["cards_ko"]]
            item["social"] = post_social(item["content"], card_urls, item["published"].get("site_ko", ""))
        item["status"] = "posted"
        f.write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
        left = len(queued) - n
        publish.kakao_notify(f"[{config.BRAND}] 아카이브 게시: {item['content']['title_ko']}\n남은 대기열 {left}건",
                             item["published"].get("site_ko"))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
