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

from radar import cards, config, publish
from radar.collect import collect
from radar.generate import generate


def main() -> None:
    mode = os.environ.get("PUBLISH_MODE", "dry-run")
    print(f"[main] mode={mode}")

    items = collect()
    print(f"[main] collected {len(items)} articles")
    if len(items) < 5:
        publish.kakao_notify(f"[{config.BRAND}] 오늘은 새 기사가 {len(items)}개뿐이라 발행을 건너뜁니다.")
        return

    content = generate(items)
    today = date.today()
    record = {"date": str(today), "mode": mode, "items": items, "content": content, "published": {}}

    # 카드뉴스 이미지: draft/auto 는 사이트(docs/)에 올려 공개 URL을 만들고, dry-run 은 output/ 에만 저장
    site = os.environ.get("SITE_URL", "").rstrip("/")
    card_root = Path("docs/cards" if mode in ("draft", "auto") else f"{config.OUTPUT_DIR}/cards") / str(today)
    for lang, label in (("ko", f"{today:%Y.%m.%d}"), ("en", f"{today:%b %d, %Y}")):
        paths = cards.render(content[f"cards_{lang}"], lang, label, card_root, site.replace("https://", ""))
        record["published"][f"cards_{lang}"] = [p.as_posix() for p in paths]
    print(f"[main] rendered cards -> {card_root}")

    if mode in ("draft", "auto"):
        record["published"].update(publish.site_posts(content, f"{site}/cards/{today}", "brief"))

    # 인스타그램·스레드 게시는 사이트 배포 후 social_post.py 단계에서 진행
    out = Path(config.OUTPUT_DIR)
    out.mkdir(exist_ok=True)
    (out / f"{date.today()}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")

    msg = f"[{config.BRAND}] {mode} 완료\n{content['title_ko']}"
    for name, refresh in (("Instagram", publish.instagram_refresh_token), ("Threads", publish.threads_refresh_token)):
        if os.environ.get(f"{name.upper()}_ACCESS_TOKEN"):
            days = refresh()  # 매일 연장해 두므로 정상이라면 항상 약 60일
            if days is not None and days < 10:
                msg += f"\n⚠️ {name} 토큰 {days}일 후 만료 - 재발급 필요"
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
