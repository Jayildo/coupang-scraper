"""
Targeted exploration: login → click main menu → click each submenu → screenshot.
Focus on key data pages only.
"""
import time
import random
import logging
from scrapling.fetchers import StealthyFetcher
from config import COUPANG_ID, COUPANG_PW, LOGIN_URL, BASE_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Target pages: (main_menu_text, submenu_text_to_click, safe_filename)
# submenu_text=None means just click main menu and screenshot the first submenu page
TARGETS = [
    # Analytics
    ("Analytics", "Premium data 2.0", "analytics_premium_data"),
    # Settlement (submenus discovered: B2B, 일반매입, 공제금액, 특수매입)
    ("Settlement", "B2B", "settlement_b2b"),
    ("Settlement", "일반매입계정", "settlement_general"),
    ("Settlement", "공제금액계정", "settlement_deductible"),
    ("Settlement", "특수매입계정", "settlement_consignment"),
    # Logistics
    ("Logistics", "Summary", "logistics_summary"),
    ("Logistics", "Purchase Order Scheduling", "logistics_po_scheduling"),
    ("Logistics", "PO List", "logistics_po_list"),
    ("Logistics", "PO SKU List", "logistics_po_sku_list"),
    ("Logistics", "Shipments", "logistics_shipments"),
    ("Logistics", "Inbound history", "logistics_inbound"),
    # Marketing (clicks redirect to dashboard — may need real account)
    ("Marketing", None, "marketing_main"),
]


def _login_and_explore(page):
    import time as _time

    # === LOGIN ===
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
        print("[AUTH] Login form not found!")
        page.screenshot(path="../data/debug_no_form.png")
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
    print(f"[AUTH] OK → {page.url}")

    # === DEBUG: Dump nav structure ===
    _dump_nav_structure(page)

    # === TARGETED EXPLORATION ===
    last_main_menu = None

    for idx, (main_menu, sub_menu, safe_name) in enumerate(TARGETS, 1):
        print(f"\n--- [{idx}/{len(TARGETS)}] {main_menu} > {sub_menu or '(main)'} ---")

        delay = random.uniform(8, 15)
        print(f"[WAIT] {delay:.1f}s...")
        _time.sleep(delay)

        # Click main menu (only if different from last one)
        if main_menu != last_main_menu:
            main_link = _find_nav_link(page, main_menu)
            if not main_link:
                print(f"[SKIP] Cannot find '{main_menu}' in nav")
                continue

            url_before = page.url

            # Playwright native click (works with position:fixed nav at y=0)
            main_link.click()
            _time.sleep(3)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            _time.sleep(3)

            print(f"[NAV] '{main_menu}': {url_before} -> {page.url}")
            last_main_menu = main_menu

            # If no submenu specified, dump submenu links and click the first one
            if sub_menu is None:
                print(f"[NAV] Dumping submenu items for '{main_menu}'...")
                _time.sleep(2)
                _dump_all_links(page, main_menu)
                # Try clicking first submenu link that appeared
                first_sub = _find_first_submenu(page)
                if first_sub:
                    txt = (first_sub.inner_text() or "").strip()
                    print(f"[NAV] Clicking first submenu: '{txt}'")
                    page.evaluate('el => el.click()', first_sub)
                    _time.sleep(3)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    _time.sleep(2)
                _save_page(page, safe_name, idx)
                continue

        # Click submenu in the second nav bar
        if sub_menu:
            # Try exact text match first
            sub_link = _find_submenu_link(page, sub_menu)
            if not sub_link:
                print(f"[SKIP] Cannot find submenu '{sub_menu}'")
                # List available submenu items for debugging
                _list_submenu_items(page)
                continue

            sub_link.click()
            _time.sleep(2)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            _time.sleep(3)

            title = page.title() or ""
            if "Access Denied" in title:
                print(f"[BLOCKED!]")
                page.screenshot(path=f"../data/{safe_name}_DENIED.png")
                page.go_back()
                _time.sleep(3)
                continue

            _save_page(page, safe_name, idx)

    print(f"\n{'='*60}")
    print("[DONE] Exploration complete!")
    return page


def _dump_nav_structure(page):
    """Dump all top-area links for debugging nav structure."""
    print("\n[NAV DEBUG] All links in top 80px:")
    links = page.query_selector_all('a')
    for link in links:
        try:
            box = link.bounding_box()
            if box and box["y"] < 80:
                txt = (link.inner_text() or "").strip()
                href = link.get_attribute("href") or ""
                classes = link.get_attribute("class") or ""
                parent = link.evaluate('el => el.parentElement ? el.parentElement.tagName + "." + (el.parentElement.className || "") : ""')
                if txt and len(txt) < 50:
                    print(f"  y={box['y']:.0f} '{txt}' -> {href}  [class={classes}] [parent={parent}]")
        except Exception:
            pass
    print("[NAV DEBUG] End\n")


def _find_nav_link(page, text):
    """Find a main navigation link by text, scoped to top nav bar only."""
    kr_map = {
        "Analytics": "애널리틱스",
        "Settlement": "정산",
        "Logistics": "물류",
        "Marketing": "광고 관리",
        "Products": "상품",
    }
    candidates = [text]
    if text in kr_map:
        candidates.append(kr_map[text])

    # Find nav link by text - return (element, href) tuple
    for name in candidates:
        links = page.query_selector_all(f'li > a:has-text("{name}")')
        for link in links:
            href = link.get_attribute("href") or ""
            if href:
                return link
    for name in candidates:
        links = page.query_selector_all(f'a:has-text("{name}")')
        for link in links:
            href = link.get_attribute("href") or ""
            if href:
                return link
    return None


def _find_submenu_link(page, text):
    """Find a submenu link by text (second nav bar, y < 120)."""
    kr_sub = {
        "Premium data 2.0": "프리미엄 데이터 2.0",
        "Summary": "요약",
        "Purchase Order Scheduling": "발주 일정",
        "PO List": "발주서 리스트",
        "PO SKU List": "발주 SKU 리스트",
        "Shipments": "출고",
        "Inbound history": "입고 이력",
        "Milkrun": "밀크런",
        "B2B": "B2B 청구",
        "일반매입계정": "일반매입계정",
        "공제금액계정": "공제금액계정",
        "특수매입계정": "특수매입계정",
    }
    candidates = [text]
    if text in kr_sub:
        candidates.append(kr_sub[text])

    for name in candidates:
        links = page.query_selector_all(f'a:has-text("{name}")')
        for link in links:
            try:
                box = link.bounding_box()
                # Second nav bar: below main nav (~40) but above page content (~150)
                if box and 30 < box["y"] < 150:
                    return link
            except Exception:
                pass
    return None


def _dump_all_links(page, context=""):
    """Dump ALL links on page with y-coordinates for debugging."""
    links = page.query_selector_all('a')
    print(f"  [LINKS] Total: {len(links)} links on page (context: {context})")
    for link in links:
        try:
            box = link.bounding_box()
            if box and box["y"] < 200:
                txt = (link.inner_text() or "").strip()
                href = link.get_attribute("href") or ""
                if txt and len(txt) < 60:
                    print(f"    y={box['y']:.0f} '{txt}' -> {href}")
        except Exception:
            pass


def _find_first_submenu(page):
    """Find the first submenu link (y between 40-120, not a main nav item)."""
    main_nav_texts = {"Home", "Products", "Contracts", "Logistics", "Settlement",
                      "Analytics", "MyShop", "Marketing", "Live & Shorts",
                      "Promotion", "Coupang Experience Group",
                      "Online Inquiry", "My Inquiry History", "Help"}
    links = page.query_selector_all('a')
    for link in links:
        try:
            box = link.bounding_box()
            if box and 35 < box["y"] < 130:
                txt = (link.inner_text() or "").strip()
                if txt and txt not in main_nav_texts and len(txt) < 60:
                    return link
        except Exception:
            pass
    return None


def _list_submenu_items(page):
    """List all visible links in top area for debugging."""
    links = page.query_selector_all('a')
    print("  [DEBUG] Visible links in top area:")
    for link in links:
        try:
            box = link.bounding_box()
            if box and box["y"] < 80:
                txt = (link.inner_text() or "").strip()
                href = link.get_attribute("href") or ""
                if txt and len(txt) < 40:
                    print(f"    '{txt}' → {href} (y={box['y']:.0f})")
        except Exception:
            pass


def _save_page(page, safe_name, idx):
    """Screenshot + save HTML + log key elements."""
    url = page.url
    title = page.title() or ""
    print(f"[OK] URL: {url}")
    print(f"[OK] Title: {title}")

    try:
        page.screenshot(path=f"../data/{safe_name}.png", full_page=False, timeout=15000)
    except Exception:
        try:
            page.screenshot(path=f"../data/{safe_name}.png", full_page=False, timeout=10000)
        except Exception as e:
            print(f"[WARN] Screenshot failed: {e}")

    try:
        with open(f"../data/{safe_name}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        pass

    print(f"[OK] Saved: {safe_name}")

    # Check for download/export elements
    for sel_text in ["다운로드", "Download", "내보내기", "Export", "엑셀", "Excel", "CSV"]:
        try:
            els = page.query_selector_all(f'button:has-text("{sel_text}"), a:has-text("{sel_text}")')
            for el in els:
                txt = (el.inner_text() or "").strip()[:50]
                print(f"  [DOWNLOAD] '{txt}'")
        except Exception:
            pass

    # Tables
    tables = page.query_selector_all("table")
    if tables:
        print(f"  [TABLE] {len(tables)} table(s)")

    # iframes
    iframes = page.query_selector_all("iframe")
    for iframe in iframes:
        src = iframe.get_attribute("src") or ""
        print(f"  [IFRAME] {src[:80]}")


def run():
    log.info("Starting targeted exploration...")
    page = StealthyFetcher.fetch(
        LOGIN_URL, headless=False, disable_resources=False,
        page_action=_login_and_explore, wait_selector="body",
    )
    if page:
        log.info("Done.")


if __name__ == "__main__":
    run()
