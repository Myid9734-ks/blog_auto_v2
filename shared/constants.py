from pathlib import Path

# writing_guidelines.txt의 규칙 수치를 코드로 관리하는 단일 진실 공급원.
# validate.py 및 향후 추가되는 스크립트는 모두 여기서 값을 가져온다.

# ── 경로 ──────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).resolve().parent.parent
OUTPUT_DIR      = BASE_DIR / "output"
CONTENT_JSON    = OUTPUT_DIR / "content.json"
NAVER_DIR       = OUTPUT_DIR / "naver"
TISTORY_DIR     = OUTPUT_DIR / "tistory"
LOGS_DIR         = BASE_DIR / "logs"
USED_TITLES_JSON = LOGS_DIR / "used_titles.json"
IMAGES_DIR       = BASE_DIR / "images"
IMAGE_PATHS_JSON = OUTPUT_DIR / "image_paths.json"
CONFIG_DIR         = BASE_DIR / "config"
NAVER_PROFILE      = CONFIG_DIR / "naver_profile"
TISTORY_PROFILE    = CONFIG_DIR / "tistory_profile"
TISTORY_COOKIES    = CONFIG_DIR / "tistory_cookies.json"

# 업로드 재시도 횟수
UPLOAD_MAX_RETRIES = 3

# ── 카테고리 매핑 (content.json category → 플랫폼별 카테고리) ────────────────
CATEGORY_MAP: dict[str, dict[str, str]] = {
    "생활정보":    {"naver": "생활정보",    "tistory": "노하우_팁"},
    "경제 정책":   {"naver": "경제 정책",   "tistory": "재테크_투자"},
    "금융정보":    {"naver": "금융정보",    "tistory": "재테크_투자"},
    "ETF 산업":    {"naver": "ETF 산업",    "tistory": "재테크_투자"},
    "저축,투자":   {"naver": "저축,투자",   "tistory": "재테크_투자"},
    "주식 투자":   {"naver": "주식 투자",   "tistory": "주식 브리핑"},
    "부동산 투자": {"naver": "부동산 투자", "tistory": "재테크_투자"},
    "비트코인":    {"naver": "비트코인",    "tistory": "재테크_투자"},
    "스포츠":      {"naver": "스포츠",      "tistory": "일상"},
    "건강":        {"naver": "건강",        "tistory": "노하우_팁"},
    "여행":        {"naver": "여행",        "tistory": "방문_체험"},
    "IT":          {"naver": "생활정보",    "tistory": "IT_테크"},
    "리뷰":        {"naver": "생활정보",    "tistory": "리뷰"},
}

# 최상위 필수 필드
REQUIRED_FIELDS = ["title", "category", "risk_level", "hashtags", "segments"]

# 허용 segment 타입
ALLOWED_TYPES = {"intro", "heading", "text", "image", "outro"}

# 위험도 등급
RISK_GENERAL = "general"
RISK_SENSITIVE = "sensitive"
ALLOWED_RISK_LEVELS = {RISK_GENERAL, RISK_SENSITIVE}

# 제목 최대 글자수 (guidelines 7단계)
TITLE_MAX_LEN = 30

# 본문 전체 글자수 범위 (guidelines 2단계)
CHAR_MIN = 1_800
CHAR_MAX = 2_500

# heading 허용 개수 (guidelines 7단계)
HEADING_MIN = 3
HEADING_MAX = 4

# image 허용 개수 (guidelines 6단계)
IMAGE_MIN = 2
IMAGE_MAX = 3

# hashtag 허용 개수 (guidelines 7단계)
HASHTAG_MIN = 5
HASHTAG_MAX = 8

# 민감 등급: 면책 문구 키워드 — outro에 하나라도 있으면 통과 (guidelines 5단계)
DISCLAIMER_KEYWORDS = [
    "정부24", "복지로", "지자체",       # 정책/지원금
    "전문의", "상담",                   # 건강정보
    "투자 판단", "투자자 본인",         # 투자/증시
    "공식 홈페이지", "공식 기관",       # 그 외 민감 주제 공통
]

# 이미지 생성 모델
IMAGE_MODEL = "gpt-image-1"
IMAGE_SIZE  = "1024x1024"

# 이미지 스타일 접미사 — generate_image.py가 각 프롬프트 뒤에 자동으로 붙임 (guidelines 6단계)
IMAGE_STYLE_SUFFIX = (
    ", flat illustration style, minimal, soft pastel colors, "
    "clean composition, no text, no watermark, blog header style"
)

# 민감 등급: 금지 단정·선동 표현 (guidelines 5단계)
SENSITIVE_BANNED_PHRASES = [
    "100% 받을 수 있다", "100%받을수있다",
    "무조건 신청", "무조건 받",
    "지금 사야", "무조건 사",
    "확실히 효과", "반드시 낫",
]
