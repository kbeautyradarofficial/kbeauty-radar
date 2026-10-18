"""수집한 기사로 한국어/영어 콘텐츠를 만듭니다."""
import json
from datetime import date

from . import config
from .llm import call_json

BASE_RULES = """
Coverage (the whole K-beauty business, not only export numbers):
  export & trade data, marketplaces/retail channels (Amazon, TikTok Shop, Shopee, Olive Young, Sephora, Ulta,
  Costco, Daiso...), new product launches & ingredient trends, brand ambassadors/models & ad campaigns,
  marketing tactics that worked, M&A/investment, regulation & certification (MoCRA, CPNP...).
  Skip pure celebrity gossip, giveaways and press releases with no business insight.
Category tags (use exactly one per story): 수출·통계 / 채널·플랫폼 / 신제품·성분 / 모델·광고 / 마케팅 사례 /
  M&A·투자 / 규제·인증  (EN: Export data / Channels / Launches / Ambassadors & ads / Marketing case / Deals / Regulation)
Facts: use ONLY facts from the provided articles. Never invent numbers, quotes, companies or dates.
  Paraphrase; never copy article sentences. Always credit the outlet.
Headline formula (benchmarked on the best-performing beauty newsletters): lead with a concrete number or a
  surprising contrast, then a question or tension. e.g. "미국 아마존 1위, 비결은 '상세페이지'?" / "+46%, 향수가 뜬다".
Korean tone: what/why end with "~습니다/~입니다", action ends with "~하세요". Never use 반말.
No investment advice.

cards_ko / cards_en (Instagram carousel, Korean / English edition):
  Number-first, scannable, no emoji, no hashtags. Use "\\n" only for intentional line breaks.
  cover.badge: series name (max 16 chars). cover.hero_number: the single most striking REAL number, max 6 chars
  (e.g. "+14%", "$100B", "1,200회"). cover.hero_label: what that number is (max 22 chars).
  cover.headline: 2 lines max, ~13 chars per line (KO) / ~22 (EN), with a tension or question hook.
  cover.sub: one line teaser (max 40 chars).
  slides: 3-5. category: one of the category tags. headline: max 24 chars (KO) / 45 (EN).
  stat: a real number from that story or "" if none; stat_label: max 20 chars.
  what/why/action: one sentence each, max 55 chars (KO) / 95 (EN). action is a concrete instruction to brands/
  marketers (KO) or to buyers/retailers (EN). source: outlet name(s) only.

instagram_caption_ko (Korean, max 1800 chars), structured like the top Korean beauty-insight accounts:
  line 1: hook with the key number. blank line. Then one block per story:
  "1️⃣ 제목" + 2-3 lines starting with "-" (what / why / action). blank line between blocks.
  Then "📌 저장해두고 필요할 때 꺼내 보세요" and "🔗 전문과 출처: 프로필 링크".
  Then "출처: outlet, outlet". Then "AI의 도움을 받아 작성했습니다." Then 6-8 hashtags on the last line
  (mix of #K뷰티 #화장품수출 #뷰티마케팅 and story-specific tags).
threads_ko: under 400 characters, hook first line, 3 short "•" lines, one closing question to invite replies,
  at most 1 hashtag."""

SYSTEM = f"""You are the editor of "{config.BRAND}", a daily K-beauty industry intelligence brief.
Readers: Korean beauty brands, marketers and sellers (Korean edition), and global buyers, distributors
and retailers sourcing K-beauty (English edition).
{BASE_RULES}

Daily brief rules:
- Pick the 3-5 stories from today's articles with the most business insight. Each: what happened -> why it
  matters -> one practical takeaway. cover.badge: "데일리 브리프" / "Daily brief" style.
- Korean edition: natural Korean for brand/marketing operators. English edition: written for overseas
  buyers, not a literal translation.
- HTML bodies: use <h2>, <p>, <ul>, <li>, <a href>. No <html>/<body> tags, no inline styles. Link each fact
  to its source article. End each body with a sources list and the line
  (KO) "이 브리프는 AI의 도움을 받아 작성되었습니다." / (EN) "This brief was prepared with AI assistance."
- linkedin_en: 600-1200 characters, professional, ends with a question to invite comments."""

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
        "instagram_caption_ko": {"type": "string"},
    },
    "required": ["title_ko", "excerpt_ko", "body_ko_html", "threads_ko", "title_en", "excerpt_en",
                 "body_en_html", "linkedin_en", "tags", "cards_ko", "cards_en", "instagram_caption_ko"],
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
