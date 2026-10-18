"""조사 단계: 웹 검색으로 사실을 확인해 '검증된 팩트 시트'만 짧게 만듭니다.

비용 구조의 핵심: 검색 도구는 이 단계에서만 쓰고, 결과는 짧은 팩트 시트(수천 토큰)로 압축합니다.
작성·검수 단계는 도구 없이 이 팩트 시트만 보고 쓰므로 원문 수십만 토큰을 반복해서 읽지 않습니다.
"""
import json
from datetime import date

from . import config
from .llm import call_json

FACTS_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "claim": {"type": "string"},      # 한 문장 사실
                "number": {"type": "string"},     # 핵심 수치 (없으면 "")
                "period": {"type": "string"},     # 기준 시점 (예: 2026년 1~9월 누적)
                "source": {"type": "string"},     # 매체·기관명
                "url": {"type": "string"},
                "verified": {"type": "boolean"},  # 원문/1차 자료로 직접 확인했는지
            },
            "required": ["claim", "number", "period", "source", "url", "verified"],
            "additionalProperties": False}},
        "angles": {"type": "array", "items": {"type": "string"}},  # 경쟁 계정이 놓친 실무 포인트
    },
    "required": ["facts", "angles"],
    "additionalProperties": False,
}

SYSTEM = f"""You are the research desk of "{config.BRAND}" (K-beauty industry intelligence for practitioners).
Today is {date.today()}. Build a compact, verified FACT SHEET for the assignment.

How to work (budget matters - stay within the limits below):
- Start from the provided article list. Search only for what is needed to verify the key numbers or to find the
  primary source (관세청·식약처·KITA·회사 IR/공시·플랫폼 공지). Do not browse broadly.
- Prefer search result snippets; fetch a page only when a number cannot be confirmed from snippets.
- Output 8-20 facts. Each fact = one sentence, with the number, its reference period, the outlet and the URL.
  verified=true only if you saw it in the source text; otherwise false.
- Time-sensitive data (share, rank, growth, export value) must have a reference period; if articles disagree,
  keep the newest and note the definition (e.g. 식약처 vs 관세청 기준).
- angles: 2-4 practical angles competitors (see context) have not covered.
Output only the JSON."""


def research(assignment: str, articles: list[dict], notes: list[str], uses: int) -> dict:
    user = json.dumps({"assignment": assignment, "articles": articles[:30],
                       "competitor_context": notes[:30]}, ensure_ascii=False)
    facts = call_json(SYSTEM, user, FACTS_SCHEMA, effort="medium", research=uses, purpose="research",
                      max_budget_usd=1.0)
    facts["facts"] = [f for f in facts["facts"] if f["claim"].strip()]
    print(f"[research] {len(facts['facts'])} facts ({sum(f['verified'] for f in facts['facts'])} verified)")
    return facts
