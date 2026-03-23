"""
HTTP-based explorer: fetch pages using saved cookies (no browser).
Much faster and doesn't trigger Akamai bot detection.
"""
import time
import random
import logging
from pathlib import Path

from session import get_http_session, fetch_page, login_fresh, cookies_exist, test_session
from config import BASE_URL, DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# All discovered pages with their URLs
PAGES = {
    # Analytics
    "analytics_premium_data": "/rpd/web-v2/",
    # Settlement
    "settlement_b2b": "/scm/settlement/b2b",
    "settlement_general": "/scm/settlement/general/purchase/account",
    "settlement_deductible": "/scm/settlement/deductible/amount/account",
    "settlement_consignment": "/scm/settlement/consignment/settlement",
    # Logistics
    "logistics_summary": "/plan/dashboard/landing_page",
    "logistics_po_scheduling": "/plan/purchase/order/schedule",
    "logistics_po_list": "/scm/purchase/order/list",
    "logistics_po_sku_list": "/scm/purchase/order/sku/list",
    "logistics_shipments": "/ibs/asn/active",
    "logistics_inbound": "/scm/receive/detail",
    # Marketing
    "marketing_main": "/marketing/ads-center/home",
}


def explore_all():
    """Fetch all target pages via HTTP and save HTML."""
    # Ensure cookies are valid
    if not cookies_exist():
        log.info("No cookies. Starting browser login...")
        login_fresh()
        time.sleep(3)

    if not test_session():
        log.info("Cookies invalid. Re-logging in...")
        login_fresh()
        time.sleep(3)

    session = get_http_session()
    if not session:
        log.error("Cannot create HTTP session!")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    for name, path in PAGES.items():
        delay = random.uniform(2, 5)
        log.info(f"[{name}] Waiting {delay:.1f}s...")
        time.sleep(delay)

        url = BASE_URL + path
        log.info(f"[{name}] Fetching {url}")

        status, html = fetch_page(path, session)
        if not status or not html:
            log.warning(f"[{name}] FAILED (no response)")
            results[name] = {"status": "error", "detail": "no response"}
            continue

        # Check for redirect to login
        if "login" in html.lower() and "password" in html.lower() and len(html) < 5000:
            log.warning(f"[{name}] Redirected to login (cookies expired?)")
            results[name] = {"status": "login_redirect"}
            continue

        # Check for access denied
        if "access denied" in html.lower() or "403" in html[:500]:
            log.warning(f"[{name}] Access Denied!")
            results[name] = {"status": "denied"}
            continue

        # Save HTML
        html_path = DATA_DIR / f"{name}_http.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Analyze content
        has_table = html.lower().count("<table")
        has_download = any(kw in html for kw in ["Download", "다운로드", "Export", "내보내기", "Excel", "CSV"])
        is_spa_shell = len(html) < 3000 and "<div id=" in html

        log.info(f"[{name}] OK: status={status}, len={len(html)}, tables={has_table}, downloads={has_download}, spa_shell={is_spa_shell}")

        results[name] = {
            "status": "ok",
            "http_status": status,
            "html_len": len(html),
            "tables": has_table,
            "has_download": has_download,
            "is_spa_shell": is_spa_shell,
        }

    # Summary
    print(f"\n{'='*60}")
    print("EXPLORATION SUMMARY")
    print(f"{'='*60}")
    for name, info in results.items():
        status = info.get("status", "?")
        if status == "ok":
            tables = info.get("tables", 0)
            dl = "YES" if info.get("has_download") else "no"
            spa = " [SPA SHELL]" if info.get("is_spa_shell") else ""
            print(f"  {name:35s} OK  tables={tables}  download={dl}{spa}")
        else:
            print(f"  {name:35s} {status.upper()}")
    print(f"{'='*60}")

    return results


if __name__ == "__main__":
    explore_all()
