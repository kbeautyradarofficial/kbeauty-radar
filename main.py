"""매일 실행: 수집 -> 생성 -> 발행 -> 보고.

PUBLISH_MODE
  dry-run : 아무것도 발행하지 않고 output/에 결과만 저장 (테스트용)
  draft   : 블로그에만 게시, Threads는 올리지 않음 (초기 품질 확인 기간)
  auto    : 블로그 게시 + Threads 게시 (완전 자동)
"""
import json
import os
from datetime import date
from pathlib import Path

from radar import config, publish
from radar.collect import collect
from radar.generate import generate


def _cta(template: str, env: str) -> str:
    url = os.environ.get(env)
    return template.format(url=url) if url else ""


def main() -> None:
    mode = os.environ.get("PUBLISH_MODE", "dry-run")
    print(f"[main] mode={mode}")

    items = collect()
    print(f"[main] collected {len(items)} articles")
    if len(items) < 5:
        publish.kakao_notify(f"[{config.BRAND}] 오늘은 새 기사가 {len(items)}개뿐이라 발행을 건너뜁니다.")
        return

    content = generate(items)
    record = {"date": str(date.today()), "mode": mode, "items": items, "content": content, "published": {}}

    if mode in ("draft", "auto"):
        record["published"]["site_ko"] = publish.site_post(
            "ko", content["title_ko"], content["body_ko_html"], content["excerpt_ko"],
            content["tags"], _cta(config.CTA_KO, "KIT_FORM_KO"))
        record["published"]["site_en"] = publish.site_post(
            "en", content["title_en"], content["body_en_html"], content["excerpt_en"],
            content["tags"], _cta(config.CTA_EN, "KIT_FORM_EN"))

    if mode == "auto" and os.environ.get("THREADS_ACCESS_TOKEN"):
        link = f"\n\n전문 👉 {record['published']['site_ko']}"
        text = content["threads_ko"][: config.THREADS_MAX_CHARS - len(link)] + link
        record["published"]["threads"] = publish.threads_post(text)

    out = Path(config.OUTPUT_DIR)
    out.mkdir(exist_ok=True)
    (out / f"{date.today()}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")

    msg = f"[{config.BRAND}] {mode} 완료\n{content['title_ko']}"
    days = publish.threads_token_days_left() if os.environ.get("THREADS_ACCESS_TOKEN") else None
    if days is not None and days < 10:
        msg += f"\n⚠️ Threads 토큰 {days}일 후 만료 - 갱신 필요"
    publish.kakao_notify(msg, record["published"].get("site_ko"))
    print(json.dumps(record["published"], ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            publish.kakao_notify(f"[{config.BRAND}] ❌ 실행 실패: {e}")
        except Exception:
            pass
        raise
