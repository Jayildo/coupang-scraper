"""Task 2: 물류 > 발주SKU리스트 > 기간 설정(입고예정일 D+1~D+30) > 다운로드."""
import time
import logging
from datetime import datetime, timedelta

from tasks.helpers import (
    navigate_menu, human_delay, short_delay,
    download_file, screenshot, click_text, wait_and_click,
)

log = logging.getLogger(__name__)

# 알려진 URL (이전 탐색에서 확인)
PO_SKU_URL = "https://supplier.coupang.com/scm/purchase/order/sku/list"


def run(page):
    """발주 SKU 리스트 기간 검색 후 다운로드."""
    log.info("=" * 50)
    log.info("[TASK] 발주 SKU 리스트 다운로드 시작")

    # 직접 URL 이동
    page.goto(PO_SKU_URL)
    time.sleep(4)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(3)

    log.info(f"[PO_SKU] 현재 URL: {page.url}")
    screenshot(page, "order_sku_loaded")

    if "login" in page.url.lower():
        log.error("[PO_SKU] 세션 만료")
        return False

    # 1. 기간 검색 조건: 입고예정일 (Receiving Scheduled) 선택
    _set_search_type(page)
    short_delay(1, 2)

    # 2. 날짜 범위: D+1 ~ D+30
    today = datetime.now()
    start_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = (today + timedelta(days=30)).strftime("%Y-%m-%d")
    log.info(f"[PO_SKU] 기간: {start_date} ~ {end_date}")

    _set_date_range(page, start_date, end_date)
    short_delay(1, 2)

    # 3. 검색 버튼 클릭 (한글/영문 모두 시도)
    screenshot(page, "order_sku_before_search")
    search_clicked = False
    for text in ["검색", "Search"]:
        btns = page.query_selector_all(f'button:has-text("{text}")')
        for btn in btns:
            try:
                if btn.is_visible():
                    btn.click()
                    search_clicked = True
                    log.info(f"[PO_SKU] 검색 클릭: '{text}'")
                    break
            except Exception:
                continue
        if search_clicked:
            break

    if not search_clicked:
        log.warning("[PO_SKU] 검색 버튼 못 찾음")

    time.sleep(4)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    time.sleep(3)

    screenshot(page, "order_sku_search_result")

    # 4. 다운로드 (Download Product List / 상품 목록 다운로드 → 팝업 → Download All)
    downloaded = _do_download(page)
    if downloaded:
        log.info(f"[PO_SKU] 다운로드 완료: {downloaded}")
    else:
        log.error("[PO_SKU] 다운로드 실패")
        screenshot(page, "order_sku_download_fail")

    return bool(downloaded)


def _set_search_type(page):
    """Period Search 드롭다운에서 '입고예정일' 또는 'Receiving Scheduled' 선택."""
    # select 요소 찾기 (Period Search 옆의 드롭다운)
    selects = page.query_selector_all("select")
    for sel in selects:
        try:
            box = sel.bounding_box()
            if not box or box["y"] > 300:
                continue
            options = sel.query_selector_all("option")
            for opt in options:
                txt = (opt.inner_text() or "").strip()
                val = opt.get_attribute("value") or ""
                if "입고" in txt or "Receiving" in txt:
                    sel.select_option(value=val)
                    log.info(f"[PO_SKU] 검색조건 선택: {txt}")
                    return True
        except Exception:
            continue

    log.warning("[PO_SKU] 입고예정일 드롭다운 못 찾음 (기본값 사용)")
    return False


def _set_date_range(page, start_date, end_date):
    """날짜 입력 필드에 시작/종료 날짜 설정."""
    # 스크린샷에서 확인: 2개의 input 필드 (시작일 ~ 종료일)
    date_inputs = page.query_selector_all('input[type="text"]')
    date_fields = []

    for inp in date_inputs:
        try:
            box = inp.bounding_box()
            if not box or box["y"] > 300:
                continue
            value = inp.get_attribute("value") or ""
            # 날짜 형식(YYYY-MM-DD)인 필드 식별
            if _looks_like_date(value) or box["y"] < 200:
                # 날짜 필드인지 추가 확인 (캘린더 아이콘 옆)
                width = box.get("width", 0)
                if width > 80:  # 너무 좁은 필드 제외
                    date_fields.append((box["x"], inp, value))
        except Exception:
            continue

    # 날짜 형식인 것만 필터
    date_fields = [(x, inp, v) for x, inp, v in date_fields if _looks_like_date(v)]

    if len(date_fields) >= 2:
        date_fields.sort(key=lambda x: x[0])
        _fill_date(page, date_fields[0][1], start_date)
        short_delay(0.5, 1)
        _fill_date(page, date_fields[1][1], end_date)
        log.info(f"[PO_SKU] 날짜 설정 완료: {start_date} ~ {end_date}")
    else:
        log.warning(f"[PO_SKU] 날짜 필드 {len(date_fields)}개 발견 (2개 필요)")
        screenshot(page, "order_sku_date_fields_debug")


def _fill_date(page, input_el, date_str):
    """날짜 입력 필드에 값 설정."""
    try:
        input_el.click()
        short_delay(0.3, 0.5)
        # 전체 선택 후 덮어쓰기
        page.keyboard.press("Control+a")
        short_delay(0.1, 0.2)
        page.keyboard.type(date_str, delay=50)
        short_delay(0.3, 0.5)
        # datepicker 닫기
        page.keyboard.press("Escape")
        short_delay(0.2, 0.3)
        page.keyboard.press("Tab")
    except Exception as e:
        log.warning(f"[PO_SKU] 날짜 입력 실패: {e}")
        try:
            input_el.evaluate(
                f'el => {{ el.value = "{date_str}"; '
                f'el.dispatchEvent(new Event("change", {{bubbles: true}})); }}'
            )
        except Exception:
            pass


def _looks_like_date(value):
    """값이 날짜 형식인지 확인."""
    if not value or len(value) < 8:
        return False
    return "-" in value and any(c.isdigit() for c in value)


def _do_download(page):
    """상품 목록 다운로드 → 팝업에서 Download All 클릭."""
    # 다운로드 버튼 찾기 (한글/영문)
    download_texts = [
        "상품 목록 다운로드", "Download Product List",
        "목록 다운로드", "다운로드", "Download",
    ]

    for text in download_texts:
        elements = page.query_selector_all(f'button:has-text("{text}"), a:has-text("{text}")')
        for el in elements:
            try:
                if el.is_visible():
                    log.info(f"[PO_SKU] 다운로드 버튼: '{text}'")
                    el.click()
                    short_delay(2, 4)

                    # 팝업이 열림 → Download All 클릭
                    screenshot(page, "order_sku_download_popup")
                    return _click_download_all(page)
            except Exception:
                continue

    log.warning("[PO_SKU] 다운로드 버튼 못 찾음")
    return None


def _click_download_all(page):
    """팝업에서 'Download All' / '전체 다운로드' 클릭하여 파일 다운로드."""
    short_delay(1, 2)

    # Download All 버튼 찾기 (한글/영문)
    for text in ["Download All", "전체 다운로드", "모두 다운로드"]:
        btns = page.query_selector_all(f'button:has-text("{text}"), a:has-text("{text}")')
        for btn in btns:
            try:
                if btn.is_visible():
                    log.info(f"[PO_SKU] '{text}' 클릭")
                    result = download_file(
                        page,
                        lambda p, b=btn: b.click(),
                        "order_sku"
                    )
                    return result
            except Exception:
                continue

    # 폴백: 팝업 내 일반 'Download' / '다운로드' 버튼
    for text in ["Download", "다운로드"]:
        btns = page.query_selector_all(f'button:has-text("{text}")')
        for btn in btns:
            try:
                inner = (btn.inner_text() or "").strip()
                # "Download Product List" 등 상위 버튼 제외 - 짧은 텍스트만
                if inner in [text, f"📥 {text}", f"⬇ {text}"]:
                    result = download_file(
                        page,
                        lambda p, b=btn: b.click(),
                        "order_sku"
                    )
                    return result
            except Exception:
                continue

    log.warning("[PO_SKU] 팝업에서 다운로드 버튼 못 찾음")
    return None
