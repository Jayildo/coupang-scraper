"""Task 4: 물류 > 밀크런 > 팝업 닫기 > 이용 요금 안내 스크랩."""
import time
import logging

from tasks.helpers import (
    navigate_menu, human_delay, short_delay,
    save_text, screenshot, click_text,
)

log = logging.getLogger(__name__)


def run(page):
    """밀크런 이용 요금 안내 스크랩."""
    log.info("=" * 50)
    log.info("[TASK] 밀크런 이용 요금 안내 스크랩 시작")

    # 물류 > Milkrun 메뉴 클릭 (영문 UI)
    if not navigate_menu(page, "물류", "밀크런"):
        log.warning("[MILKRUN] 메뉴 네비게이션 실패, 대시보드에서 재시도")
        page.goto("https://supplier.coupang.com/dashboard/KR")
        time.sleep(4)
        if not navigate_menu(page, "물류", "밀크런"):
            log.error("[MILKRUN] 밀크런 접근 실패")
            screenshot(page, "milkrun_nav_fail")
            return False

    time.sleep(4)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(3)

    log.info(f"[MILKRUN] 현재 URL: {page.url}")

    # 404 체크
    body_text = page.inner_text("body") or ""
    if "Whitelabel Error" in body_text or "404" in body_text:
        log.error("[MILKRUN] 404 에러 - URL이 잘못됨")
        screenshot(page, "milkrun_404")
        return False

    screenshot(page, "milkrun_before_popup")

    # 팝업 닫기 (여러 패턴 시도)
    short_delay(1, 2)
    popup_closed = False
    popup_selectors = [
        'button:has-text("닫기")',
        'button:has-text("Close")',
        'button:has-text("확인")',
        'button:has-text("OK")',
        'button.close',
        '[class*="close"]',
        '[class*="modal"] button',
        '[role="dialog"] button',
        '.popup-close',
        '[aria-label="Close"]',
        '[aria-label="닫기"]',
    ]
    for sel in popup_selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                log.info(f"[MILKRUN] 팝업 닫기: {sel}")
                popup_closed = True
                short_delay(1, 2)
                break
        except Exception:
            continue

    if not popup_closed:
        page.keyboard.press("Escape")
        short_delay(1, 2)
        log.info("[MILKRUN] ESC로 팝업 닫기 시도")

    screenshot(page, "milkrun_after_popup")

    # 이용 요금 안내 섹션 찾기
    short_delay(1, 2)
    fee_content = _scrape_fee_info(page)

    if fee_content:
        save_text(fee_content, "milkrun_fee_info")
        log.info(f"[MILKRUN] 요금 정보 스크랩 완료 ({len(fee_content)}자)")
    else:
        # 전체 페이지 텍스트 저장 (폴백)
        full_text = page.inner_text("body") or ""
        if len(full_text) > 100:
            save_text(full_text, "milkrun_full_page")
            log.warning("[MILKRUN] 요금 섹션 못 찾음, 전체 페이지 저장")
        else:
            log.error("[MILKRUN] 페이지 내용 없음")
            return False

    return True


def _scrape_fee_info(page):
    """이용 요금 안내 섹션 텍스트 추출."""
    # 다양한 셀렉터로 요금 섹션 탐색
    selectors = [
        '//*[contains(text(), "이용 요금")]/..',
        '//*[contains(text(), "요금 안내")]/..',
        '//*[contains(text(), "이용요금")]/..',
        '//*[contains(text(), "Fee")]/..',
        '//*[contains(text(), "Pricing")]/..',
        '[class*="fee"]',
        '[class*="price"]',
        '[class*="charge"]',
        '[class*="rate"]',
    ]

    for sel in selectors:
        try:
            if sel.startswith("/"):
                els = page.query_selector_all(f'xpath={sel}')
            else:
                els = page.query_selector_all(sel)
            for el in els:
                text = (el.inner_text() or "").strip()
                if len(text) > 50 and ("요금" in text or "원" in text or "%" in text or "fee" in text.lower()):
                    return text
        except Exception:
            continue

    # 테이블에서 요금 정보 추출
    tables = page.query_selector_all("table")
    for table in tables:
        text = (table.inner_text() or "").strip()
        if "요금" in text or "원" in text or "비용" in text or "fee" in text.lower():
            return text

    return None
