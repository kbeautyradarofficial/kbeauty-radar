"""Claude API 호출 헬퍼: JSON 스키마에 맞는 결과만 돌려받습니다."""
import json

import anthropic

MODEL = "claude-opus-5-5"

_client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 사용


def call_json(system: str, user: str, schema: dict, effort: str = "medium") -> dict:
    response = _client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        # 안전 필터가 거절하면 서버가 다른 모델로 자동 재시도
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude refused: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Output hit max_tokens; increase max_tokens")
    text = next(b.text for b in response.content if b.type == "text")
    usage = response.usage
    print(f"[llm] {response.model} in={usage.input_tokens} out={usage.output_tokens}")
    return json.loads(text)
