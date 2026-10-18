"""매주 월요일 실행: 지난 7일 브리프를 묶어 한국어/영어 뉴스레터를 발송합니다.

PUBLISH_MODE 가 auto 일 때만 실제 이메일 발송 예약, draft 면 Kit에 초안으로 저장.
"""
import json
import os
from datetime import date, timedelta
from pathlib import Path

from radar import config, publish
from radar.llm import call_json

SYSTEM = f"""You write the weekly newsletter of "{config.BRAND}" (K-beauty export intelligence).
Input: the past week's daily briefs. Output two editions (Korean for Korean brands/sellers,
English for global buyers). Use only facts in the input, keep source links, paraphrase.
Structure: 1-line opening, "This week's top 3" with why-it-matters, "Trend to watch",
"One action for this week". HTML only (<h2>, <p>, <ul>, <li>, <a href>), no inline styles.
End with (KO) "이 뉴스레터는 AI의 도움을 받아 작성되었습니다." / (EN) "Prepared with AI assistance." """

SCHEMA = {
    "type": "object",
    "properties": {
        "subject_ko": {"type": "string"}, "excerpt_ko": {"type": "string"}, "html_ko": {"type": "string"},
        "subject_en": {"type": "string"}, "excerpt_en": {"type": "string"}, "html_en": {"type": "string"},
    },
    "required": ["subject_ko", "excerpt_ko", "html_ko", "subject_en", "excerpt_en", "html_en"],
    "additionalProperties": False,
}


def main() -> None:
    mode = os.environ.get("PUBLISH_MODE", "dry-run")
    briefs = []
    for i in range(1, 8):
        f = Path(config.OUTPUT_DIR) / f"{date.today() - timedelta(days=i)}.json"
        if f.exists():
            c = json.loads(f.read_text(encoding="utf-8"))["content"]
            briefs.append({"date": f.stem, "ko": c["body_ko_html"], "en": c["body_en_html"]})
    if len(briefs) < 3:
        publish.kakao_notify(f"[{config.BRAND}] 주간 뉴스레터: 브리프가 {len(briefs)}개뿐이라 건너뜁니다.")
        return

    nl = call_json(SYSTEM, json.dumps(briefs, ensure_ascii=False), SCHEMA)
    ids = {}
    if mode in ("draft", "auto"):
        send = mode == "auto"
        ids["ko"] = publish.kit_broadcast(nl["subject_ko"], nl["html_ko"], nl["excerpt_ko"],
                                          os.environ.get("KIT_TAG_KO"), send)
        ids["en"] = publish.kit_broadcast(nl["subject_en"], nl["html_en"], nl["excerpt_en"],
                                          os.environ.get("KIT_TAG_EN"), send)
    out = Path(config.OUTPUT_DIR) / f"weekly-{date.today()}.json"
    out.write_text(json.dumps({"mode": mode, "newsletter": nl, "kit_ids": ids}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    status = "발송 예약" if mode == "auto" else "초안 저장(Kit에서 확인 후 발송)"
    publish.kakao_notify(f"[{config.BRAND}] 주간 뉴스레터 {status}\n{nl['subject_ko']}", "https://app.kit.com/campaigns")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            publish.kakao_notify(f"[{config.BRAND}] ❌ 주간 뉴스레터 실패: {e}")
        except Exception:
            pass
        raise
