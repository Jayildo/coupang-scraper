"""
Session management: browser login -> save cookies -> reuse via curl_cffi.
Avoids repeated browser launches that trigger Akamai detection.
"""
import json
import time
import logging
from pathlib import Path

from scrapling.fetchers import StealthyFetcher
from curl_cffi.requests import Session

from config import (
    COUPANG_ID, COUPANG_PW, LOGIN_URL, BASE_URL,
    COOKIE_FILE, DATA_DIR, HEADLESS,
)

log = logging.getLogger(__name__)


def _browser_login(page):
    """Playwright page_action: login and extract cookies."""
    import time as _time

    page.wait_for_load_state("networkidle")
    _time.sleep(3)
    try:
        page.wait_for_selector('input[name="username"]', timeout=10000)
    except Exception:
        pass
    _time.sleep(1)

    id_input = page.query_selector('input[name="username"]')
    pw_input = page.query_selector('input[name="password"]')

    if not id_input or not pw_input:
        print("[SESSION] Login form not found!")
        page.screenshot(path=str(DATA_DIR / "debug_no_form.png"))
        return page

    id_input.click()
    _time.sleep(0.5)
    id_input.type(COUPANG_ID, delay=80)
    _time.sleep(0.8)
    pw_input.click()
    _time.sleep(0.3)
    pw_input.type(COUPANG_PW, delay=80)
    _time.sleep(1)

    submit = page.query_selector('button:has-text("로그인"), button[type="submit"]')
    if submit:
        submit.click()
    else:
        pw_input.press("Enter")

    _time.sleep(5)
    page.wait_for_load_state("networkidle")
    _time.sleep(2)

    print(f"[SESSION] Logged in: {page.url}")

    # Extract cookies from browser context
    cookies = page.context.cookies()
    _save_cookies(cookies)
    print(f"[SESSION] Saved {len(cookies)} cookies to {COOKIE_FILE}")

    return page


def _save_cookies(cookies):
    """Save browser cookies to JSON file."""
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)


def _load_cookies():
    """Load cookies from JSON file."""
    if not COOKIE_FILE.exists():
        return None
    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def cookies_exist():
    """Check if saved cookies exist."""
    return COOKIE_FILE.exists()


def login_fresh():
    """Launch browser, login, save cookies. Use sparingly."""
    log.info("Browser login to save session cookies...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    page = StealthyFetcher.fetch(
        LOGIN_URL,
        headless=HEADLESS,
        disable_resources=False,
        page_action=_browser_login,
        wait_selector="body",
    )

    if page:
        log.info("Browser login complete, cookies saved.")
    else:
        log.error("Browser login failed!")
    return page


def get_http_session():
    """
    Create a curl_cffi Session with saved cookies.
    Impersonates Chrome TLS fingerprint to bypass Akamai.
    Returns None if no cookies available.
    """
    cookies = _load_cookies()
    if not cookies:
        log.warning("No saved cookies. Run login_fresh() first.")
        return None

    session = Session(impersonate="chrome")

    # Load cookies into session
    for c in cookies:
        session.cookies.set(
            c["name"],
            c["value"],
            domain=c.get("domain", ""),
            path=c.get("path", "/"),
        )

    return session


def fetch_page(url, session=None):
    """
    Fetch a page using curl_cffi with saved cookies.
    Returns (status_code, html_text) or (None, None) on failure.
    """
    if session is None:
        session = get_http_session()
    if session is None:
        return None, None

    # Use full URL if relative
    if url.startswith("/"):
        url = BASE_URL + url

    try:
        resp = session.get(url, timeout=30)
        return resp.status_code, resp.text
    except Exception as e:
        log.error(f"HTTP fetch failed: {e}")
        return None, None


def test_session():
    """Test if saved cookies are still valid."""
    session = get_http_session()
    if not session:
        print("[SESSION] No cookies found. Need login_fresh().")
        return False

    status, html = fetch_page("/dashboard/KR", session)
    if status == 200 and html and "dashboard" in html.lower():
        print(f"[SESSION] Cookies valid! (status={status}, len={len(html)})")
        return True
    else:
        print(f"[SESSION] Cookies expired or invalid. (status={status})")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if not cookies_exist():
        print("[SESSION] No cookies. Logging in with browser...")
        login_fresh()
    else:
        print("[SESSION] Cookies found. Testing...")
        if not test_session():
            print("[SESSION] Re-logging in...")
            login_fresh()

    # Test fetching a page via HTTP
    print("\n[TEST] Fetching Settlement B2B page via HTTP...")
    status, html = fetch_page("/scm/settlement/b2b")
    if status and html:
        print(f"[TEST] Status: {status}, HTML length: {len(html)}")
        # Check if it has real content or just a shell
        has_table = "<table" in html.lower()
        has_login = "login" in html.lower() and "password" in html.lower()
        print(f"[TEST] Has tables: {has_table}, Redirected to login: {has_login}")
    else:
        print("[TEST] Failed!")
