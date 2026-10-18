"""Claude API 호출 헬퍼: JSON 스키마에 맞는 결과만 돌려받습니다.

research=True 면 Claude가 웹 검색·웹 페이지 읽기(서버 도구)로 기사 원문과 공식 통계를 직접 확인한 뒤 씁니다.
"""
import json
import os

import anthropic

MODEL = "claude-opus-5-5"

# ANTHROPIC_API_KEY 환경변수 사용. 워크스페이스에 묶이지 않은 키라면
# ANTHROPIC_WORKSPACE_ID 를 함께 설정해야 합니다.
_workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")
_client = anthropic.Anthropic(default_headers={"anthropic-workspace-id": _workspace} if _workspace else None)

RESEARCH_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8},
]
RESEARCH_NOTE = """

Research step (do this before writing): use web_search / web_fetch to open the most important source articles
and official data (관세청·식약처·KITA·회사 공시/IR·Amazon/Olive Young 공지 등). Verify every number, date and
claim you plan to use against the full text, add the reference period, and prefer primary sources. Drop anything
you cannot verify. Search in Korean and English. Then output only the final JSON."""


def call_json(system: str, user: str, schema: dict, effort: str = "high", research: bool = False) -> dict:
    messages = [{"role": "user", "content": user}]
    kwargs = dict(
        model=MODEL,
        max_tokens=48000,
        # 안전 필터가 거절하면 서버가 다른 모델로 자동 재시도
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        system=system + (RESEARCH_NOTE if research else ""),
    )
    if research:
        kwargs["tools"] = RESEARCH_TOOLS

    for _ in range(6):  # 서버 도구가 길어지면 pause_turn 으로 끊기므로 이어서 요청
        with _client.beta.messages.stream(messages=messages, **kwargs) as stream:
            response = stream.get_final_message()
        if response.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": response.content}]

    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude refused: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Output hit max_tokens; increase max_tokens")
    texts = [b.text for b in response.content if b.type == "text" and b.text.strip()]
    usage = response.usage
    searches = sum(1 for b in response.content if b.type == "server_tool_use")
    print(f"[llm] {response.model} in={usage.input_tokens} out={usage.output_tokens} tools={searches}")
    return json.loads(texts[-1])
