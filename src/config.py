import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

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
