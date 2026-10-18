"""현시점(최근 90일) 기준 시리즈 생성: 키플레이어 / 국가별 마켓 / 인더스트리 리포트.

사용법: python series.py [개수=전체]
결과: queue/series-<NNN>.json + docs/cards/series/<id>/ (카드 이미지)
게시는 post_queue.py 가 하루 3회 꺼내서 블로그·인스타그램·스레드에 올립니다.
이전 '과거 인사이트(archive-*)' 대기열은 실행 시 모두 취소 처리합니다.
"""
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from radar import cards, config
from radar.collect import _fetch, _norm
from radar.competitors import competitor_notes
from radar.generate import BASE_RULES, COMPETITOR_RULE, review, write
from radar.research import research

QUEUE = Path("queue")

SERIES_SYSTEM = f"""You are the editor of "{config.BRAND}". Write ONE "{{series}} 리포트" about "{{topic}}"
for K-beauty brand, marketing and export practitioners, as of {date.today():%Y년 %m월} (the current moment).
{BASE_RULES}

Series rules:
- Use only the fact sheet (researched from the last {config.SERIES_LOOKBACK_DAYS} days). This is a 'what is true
  NOW' report, not history. Prefer the newest facts; anything older than the window is out.
- 키플레이어: latest launches/hero products, campaigns & ambassadors, channel moves (Amazon, TikTok Shop,
  Olive Young, offline retail abroad), latest results/numbers, and what peers can copy or watch.
- 국가별 마켓: latest export value/growth and K-beauty's share or rank in that market (with reference period),
  winning categories/brands, main channels, regulation/tariff points, and a practical checklist for exporters.
- 인더스트리: the current state of the theme with numbers, who is winning, what changes next quarter.
- cards: cover.badge = "{{series}} 리포트" (e.g. "키플레이어 리포트"); 3-5 slides, each a different angle.
- title_ko/title_en: headline formula with the strongest current number. Bodies: 400-700 words, HTML
  (<h2>,<p>,<ul>,<li>,<a href>), link facts to articles, end with sources and the AI-tools line.
- linkedin_en: 600-1200 characters. tags: 4-8 keywords."""


def _recent_articles(queries: list[str]) -> list[dict]:
    start = date.today() - timedelta(days=config.SERIES_LOOKBACK_DAYS)
    seen, out = set(), []
    for q in queries:
        time.sleep(0.5)
        lang = "en" if q.isascii() else "ko"
        for it in _fetch(q, lang, f"after:{start}")[:15]:
            key = _norm(it["title"])
            if key not in seen:
                seen.add(key)
                out.append({"title": it["title"], "source": it["source"], "url": it["link"],
                            "date": date.fromtimestamp(it["published"]).isoformat()})
    return sorted(out, key=lambda a: a["date"], reverse=True)[:30]


def cancel_archive() -> None:
    for f in QUEUE.glob("archive-*.json"):
        item = json.loads(f.read_text(encoding="utf-8"))
        if item["status"] == "queued":
            item["status"] = "cancelled"
            f.write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")


def build(series: str, topic: str, queries: list[str], item_id: str, notes: list[str]) -> bool:
    """조사(검색 상한) → 작성 → 검수 → 카드 렌더링 → queue/<item_id>.json 저장. 실패 시 False."""
    arts = _recent_articles(queries)
    if len(arts) < 4:
        print(f"[series] skip {topic}: only {len(arts)} recent articles")
        return False
    system = SERIES_SYSTEM.replace("{series}", series).replace("{topic}", topic)
    facts = research(f"{series} report on '{topic}' as of {date.today():%Y-%m}: latest numbers with "
                     "reference periods, key moves, product launches and campaign pages (find visuals), "
                     "and what practitioners should do.", arts, notes, uses=8)
    content = write(system, f"Write the {series} report on {topic} from the fact sheet.", facts, notes)
    content = review(content, facts, notes)
    site = os.environ.get("SITE_URL", "").rstrip("/")
    card_dir = Path("docs/cards/series") / item_id
    for old in card_dir.glob("*.jpg"):
        old.unlink()  # 다시 만들 때 이전 카드 이미지 제거
    for lang in ("ko", "en"):
        cards.render(content[f"cards_{lang}"], lang, f"{date.today():%Y.%m} 기준", card_dir,
                     site.replace("https://", ""))
    (QUEUE / f"{item_id}.json").write_text(json.dumps({
        "id": item_id, "theme": f"{series}:{topic}", "category": series, "status": "queued",
        "articles": arts, "facts": facts, "content": content,
        "cards_ko": [p.as_posix() for p in sorted(card_dir.glob("ko-*.jpg"))],
        "cards_base": f"cards/series/{item_id}",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[series] saved {item_id}: {series} / {topic}")
    return True


def _stop(e: Exception) -> bool:
    return "credit balance" in str(e) or "Run budget" in str(e)


def redo(ids: list[str]) -> None:
    """이미 대기열에 있는 항목을 같은 번호로 새로 만듦 (게시 전 항목만)."""
    notes = competitor_notes()
    topics = {f"{s}:{t}": (s, t, q) for s, t, q in config.SERIES}
    for item_id in ids:
        f = QUEUE / f"{item_id}.json"
        item = json.loads(f.read_text(encoding="utf-8"))
        if item["status"] != "queued":
            print(f"[series] skip {item_id}: already {item['status']}")
            continue
        try:
            build(*topics[item["theme"]], item_id, notes)
        except Exception as e:
            print(f"[series] redo failed {item_id}: {e}")
            if _stop(e):
                break


def main(limit: int | None) -> None:
    QUEUE.mkdir(exist_ok=True)
    cancel_archive()
    done = {json.loads(f.read_text(encoding="utf-8"))["theme"] for f in QUEUE.glob("series-*.json")}
    notes = competitor_notes()
    n = len(list(QUEUE.glob("series-*.json")))
    made = 0
    # 키플레이어 → 국가별 → 인더스트리 순으로 번갈아 배치 (피드가 한 종류로 몰리지 않게)
    groups = {}
    for s in config.SERIES:
        groups.setdefault(s[0], []).append(s)
    order = [g[i] for i in range(max(map(len, groups.values()))) for g in groups.values() if i < len(g)]
    for series, topic, queries in order:
        if f"{series}:{topic}" in done or (limit and made >= limit):
            continue
        try:
            if build(series, topic, queries, f"series-{n + 1:03d}", notes):
                n += 1
                made += 1
        except Exception as e:
            print(f"[series] skip {topic}: {e}")
            if _stop(e):
                break


if __name__ == "__main__":
    # python series.py 5            → 새 주제 5건 생성
    # python series.py redo 002,003 → 대기열 series-002, series-003 을 새로 생성
    if len(sys.argv) > 2 and sys.argv[1] == "redo":
        redo([f"series-{x.strip().zfill(3)}" for x in sys.argv[2].split(",") if x.strip()])
    else:
        main(int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else None)
