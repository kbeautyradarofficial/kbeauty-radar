"""대기열(queue/)에서 가장 오래된 게시물 N건을 꺼내 블로그·인스타그램·스레드에 올립니다.

사용법: python post_queue.py [건수=1]
PUBLISH_MODE=auto 일 때만 SNS에 게시합니다 (draft 면 블로그에만 게시).
새 게시 전에, 최근 SNS 게시에 실패했던 항목(대기열·데일리 브리프)을 먼저 다시 시도합니다.
"""
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from radar import config, publish
from radar.social import failed_channels, post_social, retry_failed


def _card_urls(site: str, paths: list[str]) -> list[str]:
    return [f"{site}/{p.removeprefix('docs/')}" for p in paths]


def retry_previous(site: str) -> None:
    """SNS 게시에 실패했던 항목을 다시 시도 (블로그는 이미 올라가 있으므로 SNS만)."""
    files = [f for f in Path("queue").glob("*.json")]
    for i in range(3):  # 최근 3일 데일리 브리프
        f = Path(config.OUTPUT_DIR) / f"{date.today() - timedelta(days=i)}.json"
        if f.exists():
            files.append(f)
    for f in files:
        rec = json.loads(f.read_text(encoding="utf-8"))
        if not failed_channels(rec.get("social")):
            continue
        cards = rec.get("cards_ko") or rec.get("published", {}).get("cards_ko", [])
        blog = rec.get("published", {}).get("site_ko", "")
        print(f"[queue] retrying SNS for {f.name}: {failed_channels(rec['social'])}")
        if retry_failed(rec, _card_urls(site, cards), blog):
            f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")


def main(count: int) -> None:
    mode = os.environ.get("PUBLISH_MODE", "dry-run")
    site = os.environ.get("SITE_URL", "").rstrip("/")
    if mode == "auto":
        retry_previous(site)
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
            item["social"] = post_social(item["content"], _card_urls(site, item["cards_ko"]),
                                         item["published"].get("site_ko", ""))
        item["status"] = "posted"
        f.write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
        failed = failed_channels(item.get("social"))
        note = f"\n⚠️ SNS 실패(다음 실행 때 재시도): {failed}" if failed else ""
        publish.kakao_notify(f"[{config.BRAND}] 게시: {item['content']['title_ko']}\n남은 대기열 {len(queued) - n}건{note}",
                             item["published"].get("site_ko"))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
