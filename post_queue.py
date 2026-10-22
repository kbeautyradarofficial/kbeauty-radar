"""대기열(queue/)에서 가장 오래된 게시물 N건을 꺼내 블로그·스레드에 올리고, 인스타그램은 속도 제한에 맞춰 따로 올립니다.

사용법: python post_queue.py [건수=1]
PUBLISH_MODE=auto 일 때만 SNS에 게시합니다 (draft 면 블로그에만 게시).
실행 순서:
1. 최근 스레드 게시 실패분 재시도 (항목당 하루 1번)
2. 새 대기열 항목 → 블로그 + 스레드
3. 인스타그램 1건 (오늘 브리프가 안 올라갔으면 브리프, 아니면 가장 오래된 미게시 리포트) — radar.social 의 하루 2건·3시간 간격·차단 시 48시간 정지 규칙 적용
"""
import json
import os
import random
import sys
import time
from datetime import timedelta
from pathlib import Path

from radar import config, publish
from radar.social import (failed_channels, instagram_blocked_reason, instagram_pending, now_kst,
                          post_instagram_for, post_social, retry_failed)


def _card_urls(site: str, paths: list[str]) -> list[str]:
    return [f"{site}/{p.removeprefix('docs/')}" for p in paths]


def _cards(rec: dict) -> list[str]:
    return rec.get("cards_ko") or rec.get("published", {}).get("cards_ko", [])


def _load(f: Path) -> dict:
    return json.loads(f.read_text(encoding="utf-8"))


def _save(f: Path, rec: dict) -> None:
    f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")


def _todays_brief() -> Path | None:
    """오늘(KST) 아침 브리프 기록. 파일명은 실행 시점의 UTC 날짜(전날)입니다."""
    today = now_kst().date()
    for d in (today - timedelta(days=1), today):
        f = Path(config.OUTPUT_DIR) / f"{d}.json"
        if f.exists() and _load(f).get("mode") == "auto":
            return f
    return None


def retry_threads(site: str) -> None:
    files = sorted(Path("queue").glob("*.json"))
    files += [Path(config.OUTPUT_DIR) / f"{now_kst().date() - timedelta(days=i)}.json" for i in range(3)]
    for f in files:
        if not f.exists():
            continue
        rec = _load(f)
        if "threads" not in failed_channels(rec.get("social")):
            continue
        print(f"[queue] retrying threads for {f.name}")
        if retry_failed(rec, _card_urls(site, _cards(rec)), rec.get("published", {}).get("site_ko", ""), ["threads"]):
            _save(f, rec)


def post_instagram_one(site: str) -> None:
    reason = instagram_blocked_reason()
    if reason:
        print(f"[queue] instagram skipped: {reason}")
        return
    candidates = []
    brief = _todays_brief()
    if brief:
        candidates.append(brief)
    candidates += [f for f in sorted(Path("queue").glob("*.json")) if _load(f)["status"] == "posted"]
    for f in candidates:
        rec = _load(f)
        if instagram_pending(rec):
            print(f"[queue] instagram -> {f.name}")
            post_instagram_for(rec, _card_urls(site, _cards(rec)))
            _save(f, rec)
            return
    print("[queue] instagram: nothing pending")


def main(count: int) -> None:
    mode = os.environ.get("PUBLISH_MODE", "dry-run")
    site = os.environ.get("SITE_URL", "").rstrip("/")
    if mode == "auto" and os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        time.sleep(random.randint(0, 25 * 60))  # 매일 같은 시각에 올라가지 않도록
    if mode == "auto":
        retry_threads(site)
    queued = [f for f in sorted(Path("queue").glob("*.json")) if _load(f)["status"] == "queued"]
    if not queued:
        print("[queue] empty")
    for n, f in enumerate(queued[:count], start=1):
        item = _load(f)
        if mode == "dry-run":
            print(f"[queue] would post {item['id']}: {item['theme']}")
            continue
        cards_base = f"{site}/{item.get('cards_base', 'cards/archive/' + item['id'])}"
        item["published"] = publish.site_posts(item["content"], cards_base, item["id"])
        if mode == "auto":
            item["social"] = post_social(item["content"], _card_urls(site, item["cards_ko"]),
                                         item["published"].get("site_ko", ""), channels=("threads",))
        item["status"] = "posted"
        _save(f, item)
        failed = failed_channels(item.get("social"))
        note = f"\n⚠️ SNS 실패(다음 실행 때 재시도): {failed}" if failed else ""
        publish.kakao_notify(f"[{config.BRAND}] 게시: {item['content']['title_ko']}\n남은 대기열 {len(queued) - n}건{note}",
                             item["published"].get("site_ko"))
    if mode == "auto":
        post_instagram_one(site)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
