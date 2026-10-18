"""Claude 호출 헬퍼: JSON 스키마에 맞는 결과만 돌려받습니다.

1순위: Claude Code CLI + Max 구독 토큰 (CLAUDE_CODE_OAUTH_TOKEN) → 추가 비용 없이 구독 사용량으로 처리
2순위: Anthropic API (ANTHROPIC_API_KEY) → 구독 한도 초과·오류 시 자동으로 넘어감 (크레딧 차감)

research > 0 이면 Claude가 웹 검색·웹 페이지 읽기로 기사 원문과 공식 통계를 직접 확인한 뒤 씁니다.
"""
import json
import os
import shutil
import subprocess

import anthropic

MODEL = "claude-opus-5-5"

# ANTHROPIC_API_KEY 환경변수 사용. 워크스페이스에 묶이지 않은 키라면
# ANTHROPIC_WORKSPACE_ID 를 함께 설정해야 합니다.
_workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")
_client = anthropic.Anthropic(default_headers={"anthropic-workspace-id": _workspace} if _workspace else None)


def research_tools(uses: int) -> list[dict]:
    # 페이지 1개당 읽는 분량 상한: 기사 본문은 충분히 읽되 광고·메뉴 등 불필요한 토큰 비용은 막음
    return [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": uses},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": uses, "max_content_tokens": 6000},
    ]


RESEARCH_NOTE = """

Research step (do this before writing): use web search / web fetch to open the most important source articles
and official data (관세청·식약처·KITA·회사 공시/IR·Amazon/Olive Young 공지 등). Verify every number, date and
claim you plan to use against the full text, add the reference period, and prefer primary sources. Drop anything
you cannot verify. Search in Korean and English. Use at most {n} searches and {n} page fetches.
Then output only the final JSON."""


def _via_subscription(system: str, user: str, schema: dict, research: int) -> dict | None:
    """Claude Code CLI 를 Max 구독 토큰으로 실행. 실패하면 None (→ API 로 넘어감)."""
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or not shutil.which("claude"):
        return None
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)  # 키가 있으면 CLI가 API 과금으로 실행되므로 제거
    cmd = ["claude", "-p", "--model", MODEL, "--output-format", "json",
           "--json-schema", json.dumps(schema, ensure_ascii=False),
           "--system-prompt", system, "--max-turns", "40", "--permission-mode", "dontAsk"]  # 허용 목록 밖 도구는 묻지 않고 거부
    if research:
        cmd += ["--allowedTools", "WebSearch,WebFetch"]
    try:
        p = subprocess.run(cmd, input=user, capture_output=True, text=True, encoding="utf-8",
                           env=env, timeout=1800)
        out = json.loads(p.stdout or "{}")
    except Exception as e:
        print(f"[llm] subscription run failed: {e}")
        return None
    if p.returncode != 0 or out.get("is_error") or not out.get("structured_output"):
        reason = out.get("result") or p.stderr[-300:]
        print(f"[llm] subscription unavailable, falling back to API: {str(reason)[:300]}")
        return None
    print(f"[llm] via Max subscription (list-price equivalent ${out.get('total_cost_usd', 0):.2f}, "
          f"turns={out.get('num_turns')})")
    return out["structured_output"]


def _via_api(system: str, user: str, schema: dict, effort: str, research: int) -> dict:
    messages = [{"role": "user", "content": user}]
    kwargs = dict(
        model=MODEL,
        max_tokens=48000,
        # 안전 필터가 거절하면 서버가 다른 모델로 자동 재시도
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        system=system,
    )
    if research:
        kwargs["tools"] = research_tools(research)
    blocks = []
    # 서버 도구가 길어지면 pause_turn 으로 끊기므로 이어서 요청. 단, 이어서 요청할 때마다
    # 검색 횟수 상한이 다시 생기므로 1번만 이어서 요청해 비용이 폭증하지 않게 함
    for _ in range(2):
        with _client.beta.messages.stream(messages=messages, **kwargs) as stream:
            response = stream.get_final_message()
        blocks += list(response.content)
        if response.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": blocks}]
        if research:
            kwargs["tools"] = research_tools(1)  # 이어서 쓸 때는 검색 최소화

    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude refused: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Output hit max_tokens; increase max_tokens")
    texts = [b.text for b in response.content if b.type == "text" and b.text.strip()]
    usage = response.usage
    searches = sum(1 for b in response.content if b.type == "server_tool_use")
    print(f"[llm] via API {response.model} in={usage.input_tokens} out={usage.output_tokens} tools={searches}")
    return json.loads(texts[-1])


def call_json(system: str, user: str, schema: dict, effort: str = "high", research: int = 0) -> dict:
    """research: 웹 검색·페이지 열람 허용 횟수 (0이면 사용 안 함)."""
    if research:
        system = system + RESEARCH_NOTE.replace("{n}", str(research))
    result = _via_subscription(system, user, schema, research)
    if result is not None:
        return result
    return _via_api(system, user, schema, effort, research)
