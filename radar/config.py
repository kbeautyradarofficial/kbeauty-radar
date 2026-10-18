"""K-Beauty Radar 설정. 검색어·채널 설정은 여기서만 바꾸면 됩니다."""

BRAND = "K-Beauty Radar"

# Google News RSS 검색어 (최근 1일 기사만 수집)
QUERIES_KO = [
    "K뷰티 수출",
    "화장품 수출",
    "K-뷰티 아마존",
    "화장품 틱톡샵",
    "올리브영 글로벌",
    "K뷰티 인디브랜드",
]
QUERIES_EN = [
    "K-beauty",
    "Korean skincare Amazon",
    "K-beauty TikTok Shop",
    "Korean cosmetics export",
    "Korean beauty brand US retail",
]

MAX_ITEMS = 40          # Claude에게 넘길 최대 기사 수
SEEN_LOOKBACK_DAYS = 14  # 최근 N일 동안 다룬 기사 링크는 제외

# 블로그 글 하단 구독 유도 문구 ({url}에 Kit 폼 주소가 들어감, 환경변수 KIT_FORM_KO/EN)
CTA_KO = '<p><strong>📬 매주 월요일, 한 주의 K-뷰티 수출 트렌드를 메일로 받아보세요 → <a href="{url}">무료 구독</a></strong></p>'
CTA_EN = '<p><strong>📬 Get the weekly K-beauty export digest every Monday → <a href="{url}">Subscribe free</a></strong></p>'

THREADS_MAX_CHARS = 500
OUTPUT_DIR = "output"
