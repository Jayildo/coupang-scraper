import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def _env_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# Credentials (실전)
COUPANG_ID = os.getenv("COUPANG_ID")
COUPANG_PW = os.getenv("COUPANG_PW")
# Credentials (테스트)
COUPANG_ID_TEST = os.getenv("COUPANG_ID_TEST")
COUPANG_PW_TEST = os.getenv("COUPANG_PW_TEST")

# URLs
LOGIN_URL = "https://supplier.coupang.com/login"
BASE_URL = "https://supplier.coupang.com"

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
COOKIE_FILE = PROJECT_ROOT / ".cookies.json"

# Scraping behavior
MIN_DELAY = 10  # seconds between requests
MAX_DELAY = 25
PAGE_LOAD_WAIT = 5  # seconds to wait after page load

# Runtime mode (Mac Mini + OpenClaw 자동화 대응)
#   HEADLESS: 브라우저 GUI 표시 여부 (스케줄 실행 시 true 필수)
#   UNATTENDED: 무인 실행 모드 — 2FA 발생 시 즉시 실패, 사용자 입력 없음
HEADLESS = _env_bool("SCRAPER_HEADLESS", True)
UNATTENDED = _env_bool("SCRAPER_UNATTENDED", False)

# Supabase (자동 업로드용)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
