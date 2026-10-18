"""Google News RSS에서 최근 K-뷰티 기사를 모읍니다."""
import calendar
import json
import re
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import feedparser

from . import config

LOCALES = {
    "ko": "hl=ko&gl=KR&ceid=KR:ko",
    "en": "hl=en-US&gl=US&ceid=US:en",
}


def _fetch(query: str, lang: str, period: str = "when:1d") -> list[dict]:
    q = urllib.parse.quote(f"{query} {period}")
    url = f"https://news.google.com/rss/search?q={q}&{LOCALES[lang]}"
    feed = feedparser.parse(url)
    items = []
    for e in feed.entries:
        source = getattr(getattr(e, "source", None), "title", "") or ""
        title = e.title
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        published = calendar.timegm(e.published_parsed) if getattr(e, "published_parsed", None) else time.time()
        items.append({"title": title.strip(), "link": e.link, "source": source, "lang": lang, "published": int(published)})
    return items


def _seen_links() -> set[str]:
    seen = set()
    out = Path(config.OUTPUT_DIR)
    for i in range(1, config.SEEN_LOOKBACK_DAYS + 1):
        f = out / f"{date.today() - timedelta(days=i)}.json"
        if f.exists():
            seen.update(item["link"] for item in json.loads(f.read_text(encoding="utf-8")).get("items", []))
    return seen


def _norm(title: str) -> str:
    return re.sub(r"[\W_]+", "", title.lower())[:40]


def collect_archive(start: date, window_days: int, per_window: int = 12) -> list[dict]:
    """과거 기사 수집: start부터 오늘까지 기간을 나눠 검색어별로 모읍니다 (백필용)."""
    items, keys, cursor = [], set(), start
    while cursor < date.today():
        end = min(cursor + timedelta(days=window_days), date.today())
        period = f"after:{cursor} before:{end}"
        window = []
        for q in config.BACKFILL_QUERIES:
            time.sleep(0.5)  # Google News 요청 간격
            lang = "ko" if re.search(r"[가-힣]", q) else "en"
            for it in _fetch(q, lang, period)[:per_window]:
                key = _norm(it["title"])
                if re.search(r"(?i)blog|블로그|tistory|brunch|youtube", it["source"]):
                    continue  # 개인 블로그·영상은 출처로 쓰지 않음
                if key not in keys:
                    keys.add(key)
                    window.append(it)
        items += window
        cursor = end
    return items


def collect() -> list[dict]:
    raw = [i for q in config.QUERIES_KO for i in _fetch(q, "ko")]
    raw += [i for q in config.QUERIES_EN for i in _fetch(q, "en")]
    seen, keys, items = _seen_links(), set(), []
    for item in sorted(raw, key=lambda i: i["published"], reverse=True):
        key = _norm(item["title"])
        if item["link"] in seen or key in keys:
            continue
        keys.add(key)
        items.append(item)
    return items[: config.MAX_ITEMS]
