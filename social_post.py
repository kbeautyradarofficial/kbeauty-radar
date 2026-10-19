"""매일 브리프의 인스타그램·스레드 게시 단계.

main.py 가 만든 output/<날짜>.json 을 읽어, 사이트 배포(카드 이미지 공개)가 끝난 뒤 게시합니다.
PUBLISH_MODE=auto 일 때만 실제로 게시합니다.
"""
import json
import os
import sys
from pathlib import Path

from radar import config, publish
from radar.social import failed_channels, post_social, retry_failed


def main(path: str) -> None:
    record_file = Path(path)
    if not record_file.exists():
        print(f"[social_post] no record {path} (brief skipped today)")
        return
    record = json.loads(record_file.read_text(encoding="utf-8"))
    if os.environ.get("PUBLISH_MODE") != "auto" or (record.get("social") and not failed_channels(record["social"])):
        print("[social_post] skipped (not auto mode or already posted)")
        return
    site = os.environ.get("SITE_URL", "").rstrip("/")
    card_urls = [f"{site}/{p.removeprefix('docs/')}" for p in record["published"].get("cards_ko", [])]
    if record.get("social"):  # 이전에 실패한 채널만 다시 시도
        retry_failed(record, card_urls, record["published"].get("site_ko", ""))
    else:
        record["social"] = post_social(record["content"], card_urls, record["published"].get("site_ko", ""))
    record_file.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    errors = {k: v for k, v in record["social"].items() if k.endswith("_error")}
    if errors:
        publish.kakao_notify(f"[{config.BRAND}] ⚠️ SNS 게시 일부 실패: {list(errors)}")


if __name__ == "__main__":
    main(sys.argv[1])
