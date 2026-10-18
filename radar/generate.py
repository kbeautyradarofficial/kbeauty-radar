"""수집한 기사로 한국어/영어 콘텐츠를 만듭니다."""
import json
from datetime import date

from . import config
from .llm import call_json

SYSTEM = f"""You are the editor of "{config.BRAND}", a daily K-beauty export intelligence brief.
Readers: Korean beauty brands and sellers expanding abroad (Korean edition), and global buyers,
distributors and retailers sourcing K-beauty (English edition).

Rules:
- Use ONLY facts from the provided articles. Never invent numbers, quotes, companies or dates.
- Paraphrase in your own words; never copy article sentences. Link each fact to its source article.
- Pick the 3-5 stories that matter most for export / overseas marketplace (Amazon, TikTok Shop,
  Shopee, Olive Young Global, US/EU/Japan/SEA retail) decisions. Skip celebrity gossip and ads.
- Each story: what happened -> why it matters -> one practical takeaway.
- Korean edition: natural Korean for Korean brand/seller operators. English edition: written for
  overseas buyers, not a literal translation.
- No investment advice. Neutral, concise, number-first.
- HTML bodies: use <h2>, <p>, <ul>, <li>, <a href>. No <html>/<body> tags, no inline styles.
  End each body with a sources list and the line
  (KO) "이 브리프는 AI의 도움을 받아 작성되었습니다." / (EN) "This brief was prepared with AI assistance."
- threads_ko: under 400 characters, hook first line, 3 short bullet-like lines, 2-3 hashtags.
- linkedin_en: 600-1200 characters, professional, ends with a question to invite comments.
- cards_ko / cards_en: Instagram carousel text for the same stories (Korean / English edition).
  Number-first, scannable, no emoji, no hashtags. Use "\\n" only for intentional line breaks.
  cover.badge: market + "데일리 브리프" / "Daily brief" (max 16 chars).
  cover.hero_number: the single most striking REAL number from the articles, max 6 chars (e.g. "+14%", "$100B", "1,200회").
  cover.hero_label: what that number is (max 22 chars). cover.headline: 2 lines max, ~13 chars per line (KO) / ~22 (EN),
  with a tension or question hook. cover.sub: one line teaser of the other stories (max 40 chars).
  slides: one per story (3-5). category: 2-4 word tag (e.g. 수출 통계, 아마존, 통상 리스크).
  headline: max 24 chars (KO) / 45 (EN). stat: a real number from that story or "" if none; stat_label: max 20 chars.
  what/why/action: one sentence each, max 55 chars (KO) / 95 (EN). action is a concrete instruction to brands/sellers
  (KO) or to buyers/retailers (EN). source: outlet name(s) only."""

_CARD = {
    "type": "object",
    "properties": {
        "cover": {
            "type": "object",
            "properties": {k: {"type": "string"} for k in ("badge", "hero_number", "hero_label", "headline", "sub")},
            "required": ["badge", "hero_number", "hero_label", "headline", "sub"],
            "additionalProperties": False,
        },
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {k: {"type": "string"} for k in
                               ("category", "headline", "stat", "stat_label", "what", "why", "action", "source")},
                "required": ["category", "headline", "stat", "stat_label", "what", "why", "action", "source"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["cover", "slides"],
    "additionalProperties": False,
}

SCHEMA = {
    "type": "object",
    "properties": {
        "title_ko": {"type": "string"},
        "excerpt_ko": {"type": "string"},
        "body_ko_html": {"type": "string"},
        "threads_ko": {"type": "string"},
        "title_en": {"type": "string"},
        "excerpt_en": {"type": "string"},
        "body_en_html": {"type": "string"},
        "linkedin_en": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "cards_ko": _CARD,
        "cards_en": _CARD,
    },
    "required": ["title_ko", "excerpt_ko", "body_ko_html", "threads_ko",
                 "title_en", "excerpt_en", "body_en_html", "linkedin_en", "tags", "cards_ko", "cards_en"],
    "additionalProperties": False,
}


def generate(items: list[dict]) -> dict:
    articles = [{"id": i, "title": it["title"], "source": it["source"], "lang": it["lang"], "url": it["link"]}
                for i, it in enumerate(items)]
    user = (f"Date: {date.today()}\n\nArticles collected in the last 24h (JSON):\n"
            f"{json.dumps(articles, ensure_ascii=False, indent=1)}\n\nWrite today's brief.")
    content = call_json(SYSTEM, user, SCHEMA)
    _check(content)
    return content


def _check(c: dict) -> None:
    """간단한 품질 검사. 통과 못 하면 발행하지 않고 실패 처리합니다."""
    for key in ("body_ko_html", "body_en_html"):
        if len(c[key]) < 500 or "<a " not in c[key]:
            raise ValueError(f"Quality check failed: {key} too short or has no source links")
    for key in ("cards_ko", "cards_en"):
        if not c[key]["slides"]:
            raise ValueError(f"Quality check failed: {key} has no slides")
        c[key]["slides"] = c[key]["slides"][:5]
    if len(c["threads_ko"]) > config.THREADS_MAX_CHARS:
        c["threads_ko"] = c["threads_ko"][: config.THREADS_MAX_CHARS - 1] + "…"
