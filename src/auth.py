"""
Coupang Supplier Portal - Login & Session Management
Uses StealthyFetcher (Camoufox) for anti-bot bypass
"""
import json
import time
import random
import logging
from pathlib import Path

from scrapling.fetchers import StealthyFetcher

from config import (
    COUPANG_ID, COUPANG_PW, LOGIN_URL, BASE_URL,
    COOKIE_FILE, MIN_DELAY, MAX_DELAY, PAGE_LOAD_WAIT
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def human_delay(min_s=MIN_DELAY, max_s=MAX_DELAY):
    """Random delay to mimic human behavior."""
    delay = random.uniform(min_s, max_s)
    log.info(f"Waiting {delay:.1f}s...")
    time.sleep(delay)


def login_and_explore():
    """
    Login to supplier.coupang.com and explore the page structure.
    This is the prototype - we'll inspect what's available after login.
    """
    log.info("Starting StealthyFetcher login attempt...")

    # Step 1: Navigate to login page
    page = StealthyFetcher.fetch(
        LOGIN_URL,
        headless=False,  # Visible browser for debugging
        disable_resources=False,  # Load all resources (JS needed for login)
        page_action=_login_action,
        wait_selector="body",
    )

    if page is None:
        log.error("Failed to fetch login page")
        return None

    log.info(f"Page title: {page.css('title::text').get()}")
    log.info(f"Current URL after login: check browser")

    # Step 2: Print page structure to understand layout
    # Look for navigation links, menu items, etc.
    nav_links = page.css("a[href]")
    log.info(f"Found {len(nav_links)} links on page")

    for link in nav_links[:30]:  # First 30 links
        href = link.attrib.get("href", "")
        text = link.css("::text").get() or ""
        if text.strip():
            log.info(f"  Link: {text.strip()} -> {href}")

    return page


def _login_action(page):
    """
    Playwright page action: fill login form and submit.
    This runs inside the browser context.
    """
    import time as _time

    # Wait for page to fully load
    page.wait_for_load_state("networkidle")
    _time.sleep(3)

    # Try to find and fill the login form
    # We'll need to inspect the actual form structure
    try:
        # Common patterns for login forms
        # Attempt 1: input[name] or input[type]
        id_input = page.query_selector(
            'input[name="username"], input[name="id"], '
            'input[type="email"], input[name="email"], '
            'input[id="username"], input[id="id"]'
        )
        pw_input = page.query_selector(
            'input[name="password"], input[type="password"], '
            'input[id="password"]'
        )

        if not id_input or not pw_input:
            # Attempt 2: broader search
            inputs = page.query_selector_all('input[type="text"], input[type="email"]')
            pw_inputs = page.query_selector_all('input[type="password"]')
            if inputs and pw_inputs:
                id_input = inputs[0]
                pw_input = pw_inputs[0]

        if id_input and pw_input:
            # Type slowly like a human
            id_input.click()
            _time.sleep(0.5)
            id_input.fill("")
            id_input.type(COUPANG_ID, delay=80)
            _time.sleep(0.8)

            pw_input.click()
            _time.sleep(0.3)
            pw_input.fill("")
            pw_input.type(COUPANG_PW, delay=80)
            _time.sleep(1)

            # Find and click submit button
            submit_btn = page.query_selector(
                'button[type="submit"], input[type="submit"], '
                'button:has-text("로그인"), button:has-text("Login")'
            )
            if submit_btn:
                submit_btn.click()
                _time.sleep(5)  # Wait for login to complete
                page.wait_for_load_state("networkidle")
            else:
                # Try pressing Enter
                pw_input.press("Enter")
                _time.sleep(5)
                page.wait_for_load_state("networkidle")
        else:
            print("[AUTH] Could not find login form inputs!")
            # Take screenshot for debugging
            page.screenshot(path="debug_login_page.png")

    except Exception as e:
        print(f"[AUTH] Login error: {e}")
        page.screenshot(path="debug_login_error.png")

    return page


if __name__ == "__main__":
    login_and_explore()
