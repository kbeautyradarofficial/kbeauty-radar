"""Claude 호출 헬퍼: JSON 스키마에 맞는 결과만 돌려받습니다.

1순위: Claude Code CLI + Max 구독 토큰 (CLAUDE_CODE_OAUTH_TOKEN) → 추가 비용 없이 구독 사용량으로 처리
2순위: Anthropic API (ANTHROPIC_API_KEY) → 구독 한도 초과·오류 시 자동으로 넘어감 (크레딧 차감)

비용 안전장치
- research > 0 일 때만 웹 검색 허용 (조사 단계 전용). 검색 횟수·페이지 열람 횟수·페이지당 분량에 상한.
- 호출 1회 예산(max_budget_usd)과 실행 1회 총예산(RUN_BUDGET_USD, 기본 $6)을 넘기면 중단.
- 모든 호출의 토큰·예상 비용을 output/usage.jsonl 에 기록 (월별 점검용).
"""
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import anthropic

MODEL = "claude-opus-5-5"
PRICE_IN, PRICE_OUT, PRICE_SEARCH = 4 / 1e6, 20 / 1e6, 10 / 1000
PRICE_CACHE_READ, PRICE_CACHE_WRITE = 0.2 / 1e6, 5 / 1e6
RUN_BUDGET_USD = float(os.environ.get("RUN_BUDGET_USD", "6"))
USAGE_LOG = Path("output/usage.jsonl")
_spent = 0.0  # 이번 실행에서 쓴 금액(목록가 기준)

_workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")
_client = anthropic.Anthropic(default_headers={"anthropic-workspace-id": _workspace} if _workspace else None)


def research_tools(uses: int) -> list[dict]:
    return [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": uses},
        # 페이지 열람은 검색의 절반까지만, 페이지당 4천 토큰까지만 읽음
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": max(1, uses // 2),
         "max_content_tokens": 4000},
    ]


def _log(purpose: str, path: str, cost: float, **extra) -> None:
    global _spent
    _spent += cost
    USAGE_LOG.parent.mkdir(exist_ok=True)
    row = {"ts": datetime.now().isoformat(timespec="seconds"), "purpose": purpose, "path": path,
           "cost_usd": round(cost, 3), "run_total_usd": round(_spent, 3), **extra}
    with USAGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[llm] {purpose} via {path}: ${cost:.2f} (run total ${_spent:.2f}) {extra}")


def _via_subscription(system, user, schema, research, purpose, max_budget_usd) -> dict | None:
    """Claude Code CLI 를 Max 구독 토큰으로 실행. 실패하면 None (→ API 로 넘어감)."""
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or not shutil.which("claude"):
        return None
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)  # 키가 있으면 CLI가 API 과금으로 실행되므로 제거
    # 터미널에서 복사할 때 끼어든 줄바꿈·공백 제거 (토큰에는 공백이 없음)
    env["CLAUDE_CODE_OAUTH_TOKEN"] = re.sub(r"\s+", "", env["CLAUDE_CODE_OAUTH_TOKEN"])
    cmd = ["claude", "-p", "--model", MODEL, "--output-format", "json",
           "--json-schema", json.dumps(schema, ensure_ascii=False),
           "--system-prompt", system, "--permission-mode", "dontAsk",
           "--max-turns", str(research * 2 + 4 if research else 3),
           "--max-budget-usd", str(max_budget_usd)]
    if research:
        cmd += ["--allowedTools", "WebSearch,WebFetch"]
    try:
        p = subprocess.run(cmd, input=user, capture_output=True, text=True, encoding="utf-8",
                           env=env, timeout=1500)
        out = json.loads(p.stdout or "{}")
    except Exception as e:
        print(f"[llm] subscription run failed: {e}")
        return None
    if p.returncode != 0 or out.get("is_error") or not out.get("structured_output"):
        reason = out.get("result") or out.get("subtype") or p.stderr[-300:]
        print(f"[llm] subscription unavailable, falling back to API: {str(reason)[:300]}")
        return None
    # 구독 경로는 실제 과금이 아니지만, 사용량 감을 잡기 위해 목록가 환산값을 기록
    _log(purpose, "subscription", 0.0, list_price_usd=out.get("total_cost_usd"), turns=out.get("num_turns"))
    return out["structured_output"]


def _via_api(system, user, schema, effort, research, purpose) -> dict:
    if _spent >= RUN_BUDGET_USD:
        raise RuntimeError(f"Run budget ${RUN_BUDGET_USD} reached; stopping to protect credits")
    kwargs = dict(
        model=MODEL,
        max_tokens=32000,
        betas=["server-side-fallback-2026-07-01"],  # 안전 필터 거절 시 서버가 다른 모델로 재시도
        fallbacks="default",
        cache_control={"type": "ephemeral"},        # 반복되는 앞부분(지시문·자료)은 캐시로 싸게
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        system=system,
    )
    if research:
        kwargs["tools"] = research_tools(research)
    # pause_turn 이 나와도 이어서 요청하지 않음: 이어 요청할 때마다 검색 상한이 초기화돼 비용이 폭증했던 원인
    with _client.beta.messages.stream(messages=[{"role": "user", "content": user}], **kwargs) as stream:
        r = stream.get_final_message()
    u = r.usage
    searches = sum(1 for b in r.content if b.type == "server_tool_use")
    cached = getattr(u, "cache_read_input_tokens", 0) or 0
    written = getattr(u, "cache_creation_input_tokens", 0) or 0
    cost = (u.input_tokens * PRICE_IN + cached * PRICE_CACHE_READ + written * PRICE_CACHE_WRITE
            + u.output_tokens * PRICE_OUT + searches * PRICE_SEARCH)
    _log(purpose, "api", cost, input=u.input_tokens, cache_read=cached, cache_write=written,
         output=u.output_tokens, tools=searches)
    if r.stop_reason == "refusal":
        raise RuntimeError(f"Claude refused: {r.stop_details}")
    if r.stop_reason in ("max_tokens", "pause_turn"):
        raise RuntimeError(f"Incomplete response ({r.stop_reason})")
    texts = [b.text for b in r.content if b.type == "text" and b.text.strip()]
    return json.loads(texts[-1])


def call_json(system: str, user: str, schema: dict, effort: str = "high", research: int = 0,
              purpose: str = "write", max_budget_usd: float = 1.5) -> dict:
    """research: 웹 검색 허용 횟수 (0이면 도구 없이 주어진 자료만으로 작성)."""
    if research:
        system += (f"\n\nTool budget: at most {research} web searches and {max(1, research // 2)} page fetches. "
                   "Then output the final JSON.")
    result = _via_subscription(system, user, schema, research, purpose, max_budget_usd)
    if result is not None:
        return result
    return _via_api(system, user, schema, effort, research, purpose)
