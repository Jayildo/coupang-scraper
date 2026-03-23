"""Task 3: 애널리틱스 > 프리미엄 데이터 2.0 > 일간 종합 성과 지표 > 당월 데이터 다운로드."""
import time
import logging
from datetime import datetime

from tasks.helpers import (
    navigate_menu, human_delay, short_delay,
    download_file, screenshot, click_text, wait_and_click,
)

log = logging.getLogger(__name__)

# SPA 페이지 - 직접 URL 이동
ANALYTICS_URL = "https://supplier.coupang.com/rpd/web-v2/"


def run(page):
    """프리미엄 데이터 2.0 일간 종합 성과 지표 다운로드."""
    log.info("=" * 50)
    log.info("[TASK] 프리미엄 데이터 2.0 다운로드 시작")

    # 페이지 이동
    page.goto(ANALYTICS_URL)
    time.sleep(5)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    time.sleep(5)  # SPA 렌더링 대기

    log.info(f"[ANALYTICS] 현재 URL: {page.url}")
    screenshot(page, "analytics_loaded")

    if "login" in page.url.lower():
        log.error("[ANALYTICS] 세션 만료")
        return False

    # 1. 왼쪽 사이드바에서 "일간 종합 성과 지표" 클릭
    short_delay(2, 3)
    if not _click_sidebar_menu(page, "일간 종합 성과 지표"):
        log.error("[ANALYTICS] '일간 종합 성과 지표' 사이드바 메뉴 못 찾음")
        screenshot(page, "analytics_sidebar_fail")
        return False

    time.sleep(4)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    time.sleep(5)

    screenshot(page, "analytics_daily_metrics")

    # 2. Date: 월별 보기 → 당월 선택
    _select_current_month(page)
    short_delay(2, 3)

    # 3. 검색 버튼
    for text in ["검색", "Search", "조회"]:
        if click_text(page, text, tag="button"):
            break

    time.sleep(4)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    time.sleep(5)

    screenshot(page, "analytics_search_result")

    # 4. 전체 데이터 다운로드 → 요청 → 다운로드
    downloaded = _request_and_download(page)
    if downloaded:
        log.info(f"[ANALYTICS] 다운로드 완료: {downloaded}")
    else:
        log.error("[ANALYTICS] 다운로드 실패")
        screenshot(page, "analytics_download_fail")

    return bool(downloaded)


def _click_sidebar_menu(page, menu_text):
    """왼쪽 사이드바에서 메뉴 클릭 (x < 300 영역)."""
    # 사이드바 내 링크 찾기
    for tag in ["a", "li", "div", "span", "button"]:
        elements = page.query_selector_all(f'{tag}:has-text("{menu_text}")')
        for el in elements:
            try:
                box = el.bounding_box()
                if not box:
                    continue
                # 사이드바는 왼쪽에 위치 (x < 300)
                if box["x"] < 300:
                    inner = (el.inner_text() or "").strip()
                    # 정확한 텍스트 매칭 (너무 긴 텍스트 제외)
                    if menu_text in inner and len(inner) < 50:
                        el.scroll_into_view_if_needed()
                        short_delay(0.3, 0.8)
                        el.click()
                        log.info(f"[ANALYTICS] 사이드바 클릭: '{menu_text}'")
                        return True
            except Exception:
                continue

    # 폴백: 사이드바 영역 내 모든 링크 덤프
    _dump_sidebar(page)
    return False


def _dump_sidebar(page):
    """디버그: 사이드바 링크 목록."""
    links = page.query_selector_all("a, li, span")
    log.info("[DEBUG] 사이드바 영역 (x < 300) 요소:")
    for el in links:
        try:
            box = el.bounding_box()
            if box and box["x"] < 300 and 50 < box["y"] < 800:
                txt = (el.inner_text() or "").strip()
                if txt and len(txt) < 50 and "\n" not in txt:
                    tag = el.evaluate("el => el.tagName")
                    log.info(f"  [{tag}] x={box['x']:.0f} y={box['y']:.0f} '{txt}'")
        except Exception:
            pass


def _select_current_month(page):
    """월별 보기 선택 → 당월(최상단) 선택."""
    # 월별 보기 버튼/탭 클릭
    for text in ["월별", "월별 보기", "Monthly", "월간"]:
        if click_text(page, text, tag="button,a,li,span,div,label", timeout=3000):
            log.info(f"[ANALYTICS] '{text}' 선택")
            short_delay(1, 2)
            break

    # 날짜/기간 셀렉터 찾기
    now = datetime.now()
    current_month_texts = [
        now.strftime("%Y-%m"),
        now.strftime("%Y.%m"),
        now.strftime("%Y년 %m월"),
        f"{now.year}년 {now.month}월",
    ]

    # 드롭다운/셀렉트 열기
    date_selectors = [
        'select', '[class*="date"]', '[class*="calendar"]',
        '[class*="picker"]', '[class*="period"]',
    ]

    for sel in date_selectors:
        elements = page.query_selector_all(sel)
        for el in elements:
            try:
                if not el.is_visible():
                    continue
                box = el.bounding_box()
                if not box or box["y"] > 500 or box["x"] < 300:
                    continue  # 사이드바 제외, 메인 콘텐츠 영역만

                tag = el.evaluate("el => el.tagName")
                if tag == "SELECT":
                    options = el.query_selector_all("option")
                    if options:
                        # 첫 번째 옵션 = 당월 (최상단)
                        val = options[0].get_attribute("value")
                        el.select_option(value=val)
                        txt = (options[0].inner_text() or "").strip()
                        log.info(f"[ANALYTICS] 월 선택 (select): {txt}")
                        return True
                else:
                    el.click()
                    short_delay(1, 2)

                    # 당월 텍스트 찾기
                    for month_text in current_month_texts:
                        if click_text(page, month_text, tag="li,div,span,a,button,option", timeout=2000):
                            log.info(f"[ANALYTICS] 월 선택: {month_text}")
                            return True

                    # 첫 번째 옵션 (최상단 = 당월)
                    items = page.query_selector_all('[class*="option"], [class*="item"], [class*="menu"] li')
                    for item in items:
                        try:
                            ibox = item.bounding_box()
                            if ibox and item.is_visible():
                                txt = (item.inner_text() or "").strip()
                                if txt and len(txt) < 30:
                                    item.click()
                                    log.info(f"[ANALYTICS] 첫 옵션 선택: {txt}")
                                    return True
                        except Exception:
                            continue
            except Exception:
                continue

    log.warning("[ANALYTICS] 월 선택 실패")
    screenshot(page, "analytics_month_select_fail")
    return False


def _request_and_download(page):
    """전체 데이터 다운로드 → 요청 → 다운로드 목록 → 다운로드."""
    # Step 1: 전체 데이터 다운로드 버튼
    download_texts = [
        "전체 데이터 다운로드", "전체 다운로드",
        "데이터 다운로드", "다운로드", "Download",
    ]
    clicked = False
    for text in download_texts:
        if click_text(page, text, tag="button,a", timeout=3000):
            clicked = True
            break

    if not clicked:
        log.error("[ANALYTICS] '전체 데이터 다운로드' 버튼 못 찾음")
        return None

    short_delay(2, 3)
    screenshot(page, "analytics_download_popup")

    # Step 2: 팝업에서 '요청' 버튼
    for text in ["요청", "Request"]:
        if click_text(page, text, tag="button", timeout=5000):
            break

    short_delay(3, 5)
    screenshot(page, "analytics_after_request")

    # Step 3: 다운로드 목록 보기
    for text in ["다운로드 목록 보기", "다운로드 목록", "목록 보기", "Download List"]:
        if click_text(page, text, tag="button,a", timeout=5000):
            break

    short_delay(3, 5)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(3)

    screenshot(page, "analytics_download_list")

    # Step 4: 최상단 다운로드 버튼
    return _click_first_download(page)


def _click_first_download(page):
    """다운로드 목록에서 최상단 항목 다운로드."""
    # 테이블 행에서 다운로드 버튼
    rows = page.query_selector_all("tr, [class*='row'], [class*='list-item']")
    for row in rows:
        try:
            for text in ["다운로드", "Download"]:
                dl_btn = row.query_selector(f'button:has-text("{text}"), a:has-text("{text}")')
                if dl_btn and dl_btn.is_visible():
                    result = download_file(
                        page,
                        lambda p, btn=dl_btn: btn.click(),
                        "analytics_premium"
                    )
                    return result
        except Exception:
            continue

    # 전체에서 다운로드 버튼 (짧은 텍스트만)
    for text in ["다운로드", "Download"]:
        btns = page.query_selector_all(f'button:has-text("{text}"), a:has-text("{text}")')
        for btn in btns:
            try:
                if btn.is_visible():
                    inner = (btn.inner_text() or "").strip()
                    if len(inner) < 15:
                        result = download_file(
                            page,
                            lambda p, b=btn: b.click(),
                            "analytics_premium"
                        )
                        return result
            except Exception:
                continue

    log.warning("[ANALYTICS] 다운로드 목록에서 버튼 못 찾음")
    return None
