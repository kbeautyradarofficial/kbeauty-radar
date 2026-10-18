"""과거 인사이트 백필: 지난 기사 중 '지금도 알아둘 가치가 있는' 주제를 골라 콘텐츠를 미리 만들어 둡니다.

사용법: python backfill.py [개수=20]
결과: queue/<id>.json (게시 대기) + docs/cards/archive/<id>/ (카드 이미지, 커밋 후 공개 URL)
게시는 post_queue.py 가 하루 2회 1건씩 꺼내서 블로그·인스타그램·스레드에 올립니다.
"""
import json
import os
import sys
from datetime import date
from pathlib import Path

from radar import cards, config
from radar.collect import collect_archive
from radar.generate import BASE_RULES, SCHEMA, _check
from radar.llm import call_json

QUEUE = Path("queue")

CURATE_SYSTEM = f"""You curate an archive series for "{config.BRAND}", a K-beauty industry insight account
that is just launching. From past news headlines (2024 to now), pick topics that are STILL useful to know
today for K-beauty brands, marketers and buyers: lasting trends, case studies of what worked (launches,
ambassador/model choices, ad campaigns, channel strategies), market shifts, deals, regulation.
Rules: each topic groups 2-6 related articles (by id) about the same story or trend. Prefer stories with
concrete numbers. Spread topics across all categories, not only export. Skip one-off gossip, events that
are over with no lasting lesson, and anything in the 'already covered' list. Order topics so that the
most broadly interesting ones come first."""

CURATE_SCHEMA = {
    "type": "object",
    "properties": {"topics": {"type": "array", "items": {
        "type": "object",
        "properties": {"theme": {"type": "string"}, "category": {"type": "string"},
                       "why_still_relevant": {"type": "string"},
                       "article_ids": {"type": "array", "items": {"type": "integer"}}},
        "required": ["theme", "category", "why_still_relevant", "article_ids"],
        "additionalProperties": False}}},
    "required": ["topics"],
    "additionalProperties": False,
}

WRITE_SYSTEM = f"""You are the editor of "{config.BRAND}". Write ONE archive insight post ("인사이트 아카이브")
about a past K-beauty story that is still worth knowing today. Readers: Korean beauty brands/marketers
(Korean edition) and global buyers (English edition).
{BASE_RULES}

Archive post rules:
- Always say when it happened (e.g. "2025년 3월") — never present past news as today's news.
- Structure: what happened -> why it worked / why it matters -> what is still valid now -> one takeaway.
- cards: cover.badge "인사이트 아카이브" / "Insight archive"; slides break the story into 3-4 angles
  (background, numbers, strategy, lesson). Each slide's source = the outlet.
- title_ko/title_en: the headline formula. Bodies: 400-700 words, HTML (<h2>,<p>,<ul>,<li>,<a href>),
  link facts to the articles, end with sources and the AI-assistance line.
- linkedin_en: 600-1200 characters. tags: 4-8 keywords."""


def main(count: int) -> None:
    QUEUE.mkdir(exist_ok=True)
    covered = [json.loads(f.read_text(encoding="utf-8"))["theme"] for f in QUEUE.glob("*.json")]

    items = collect_archive(date.fromisoformat(config.BACKFILL_START), config.BACKFILL_WINDOW_DAYS)
    print(f"[backfill] collected {len(items)} past articles")
    headlines = [{"id": i, "title": it["title"], "source": it["source"],
                  "date": date.fromtimestamp(it["published"]).isoformat()} for i, it in enumerate(items)]
    topics = call_json(CURATE_SYSTEM, json.dumps({"already_covered": covered, "headlines": headlines},
                                                 ensure_ascii=False), CURATE_SCHEMA)["topics"][:count]
    print(f"[backfill] selected {len(topics)} topics")

    site = os.environ.get("SITE_URL", "").rstrip("/")
    start = len(list(QUEUE.glob("*.json")))
    for n, topic in enumerate(topics, start=start + 1):
        arts = [{"title": items[i]["title"], "source": items[i]["source"], "url": items[i]["link"],
                 "date": date.fromtimestamp(items[i]["published"]).isoformat()}
                for i in topic["article_ids"] if 0 <= i < len(items)]
        if not arts:
            continue
        try:
            content = call_json(WRITE_SYSTEM, json.dumps({"topic": topic, "articles": arts}, ensure_ascii=False),
                                SCHEMA)
            _check(content)
        except Exception as e:
            print(f"[backfill] skip '{topic['theme']}': {e}")
            continue
        item_id = f"archive-{n:03d}"
        card_dir = Path("docs/cards/archive") / item_id
        oldest = min(a["date"] for a in arts)[:7].replace("-", ".")
        for lang in ("ko", "en"):
            paths = cards.render(content[f"cards_{lang}"], lang, oldest, card_dir, site.replace("https://", ""))
        (QUEUE / f"{item_id}.json").write_text(json.dumps({
            "id": item_id, "theme": topic["theme"], "category": topic["category"], "status": "queued",
            "articles": arts, "content": content,
            "cards_ko": [p.as_posix() for p in sorted(card_dir.glob("ko-*.jpg"))],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[backfill] queued {item_id}: {topic['theme']}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
