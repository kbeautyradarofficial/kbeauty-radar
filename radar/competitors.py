"""경쟁 채널 모니터링: 경쟁 매체·뉴스레터의 최근 글 제목 + 스레드 'K뷰티' 인기 글.

여기서 모은 내용은 '이미 다른 곳에서 다룬 것'을 알려주는 참고자료로만 쓰입니다 (사실 근거로 쓰지 않음).
"""
import os
import re

import feedparser
import requests

# 공개 RSS / 아카이브가 있는 경쟁·벤치마크 채널
FEEDS = {
    "Glossy": "https://www.glossy.co/feed/",
    "BeautyMatter": "https://beautymatter.com/feed",
    "Beauty Independent": "https://www.beautyindependent.com/feed/",
    "Cosmetics Business": "https://cosmeticsbusiness.com/rss",
    "Personal Care Insights": "https://www.personalcareinsights.com/rss/news.xml",
}
STIBEE_ARCHIVES = {"트렌디어 뉴스레터": "https://page.stibee.com/archives/175669"}
THREADS_QUERIES = ["K뷰티", "화장품 수출", "뷰티 마케팅"]


def _feeds(per_feed: int = 8) -> list[str]:
    out = []
    for name, url in FEEDS.items():
        try:
            for e in feedparser.parse(url).entries[:per_feed]:
                out.append(f"[{name}] {e.title}")
        except Exception:
            continue
    return out


def _stibee(per_archive: int = 8) -> list[str]:
    out = []
    for name, url in STIBEE_ARCHIVES.items():
        try:
            html = requests.get(url, timeout=20).text
            titles = re.findall(r'class="[^"]*title[^"]*"[^>]*>([^<]{8,120})<', html)
            out += [f"[{name}] {t.strip()}" for t in titles[:per_archive]]
        except Exception:
            continue
    return out


def _threads(per_query: int = 6) -> list[str]:
    """스레드 키워드 검색 (앱에 threads_keyword_search 권한이 있어야 동작, 없으면 건너뜀)."""
    token = os.environ.get("THREADS_ACCESS_TOKEN")
    if not token:
        return []
    out = []
    for q in THREADS_QUERIES:
        try:
            r = requests.get("https://graph.threads.net/v1.0/keyword_search", timeout=20, params={
                "q": q, "search_type": "TOP", "fields": "text,username,timestamp", "access_token": token})
            if not r.ok:
                return out
            for p in r.json().get("data", [])[:per_query]:
                text = (p.get("text") or "").replace("\n", " ")[:160]
                if text:
                    out.append(f"[Threads @{p.get('username', '?')}] {text}")
        except Exception:
            continue
    return out


def competitor_notes() -> list[str]:
    notes = _feeds() + _stibee() + _threads()
    print(f"[competitors] {len(notes)} items")
    return notes
