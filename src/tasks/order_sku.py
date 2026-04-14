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

    # 2. 날짜 범위: D+1 ~ D+30 (입고예정일 기준)
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

    # 1) 네이티브 <select> 탐색
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
                if "입고" in txt or "Receiving" in txt or "receiving" in val.lower():
                    sel.select_option(value=val)
                    log.info(f"[PO_SKU] 검색조건 선택 (native): {txt}")
                    return True
        except Exception:
            continue

    # 2) React/커스텀 드롭다운 탐색 (상단 검색 영역 내)
    #    드롭다운 트리거를 클릭 → 옵션 목록에서 입고예정일 선택
    dropdown_selectors = [
        '[class*="select"]',
        '[class*="dropdown"]',
        '[class*="combo"]',
        '[role="combobox"]',
        '[role="listbox"]',
    ]
    for sel in dropdown_selectors:
        els = page.query_selector_all(sel)
        for el in els:
            try:
                box = el.bounding_box()
                if not box or box["y"] > 300:
                    continue
                # 드롭다운 텍스트 확인 (현재 선택값)
                txt = (el.inner_text() or "").strip()
                # 이미 입고예정일이면 스킵
                if "입고" in txt or "Receiving" in txt:
                    log.info(f"[PO_SKU] 이미 입고예정일 선택됨: {txt}")
                    return True
                # 기간 관련 드롭다운이면 클릭해서 옵션 탐색
                if any(k in txt for k in ["발주", "Order", "기간", "Period", "날짜", "Date"]):
                    el.click()
                    short_delay(0.5, 1)
                    # 열린 옵션 목록에서 입고예정일 찾기
                    for kr_txt in ["입고예정일", "입고 예정일", "Receiving Scheduled", "Receiving"]:
                        opt = page.query_selector(
                            f'li:has-text("{kr_txt}"), div[role="option"]:has-text("{kr_txt}"), '
                            f'option:has-text("{kr_txt}"), [class*="option"]:has-text("{kr_txt}")'
                        )
                        if opt:
                            opt.click()
                            log.info(f"[PO_SKU] 검색조건 선택 (custom): {kr_txt}")
                            return True
                    # 옵션 못 찾으면 Escape로 닫기
                    page.keyboard.press("Escape")
                    short_delay(0.3, 0.5)
            except Exception:
                continue

    log.warning("[PO_SKU] 입고예정일 드롭다운 못 찾음 (기본값 사용)")
    return False


def _set_date_range(page, start_date, end_date):
    """날짜 입력 필드에 시작/종료 날짜 설정."""
    date_fields = []

    # 전략 1: input[type="date"] 직접 탐색
    for inp in page.query_selector_all('input[type="date"]'):
        try:
            box = inp.bounding_box()
            if box and box["y"] < 300 and box.get("width", 0) > 60:
                value = inp.get_attribute("value") or ""
                date_fields.append((box["x"], inp, value, "date-type"))
        except Exception:
            continue

    # 전략 2: text input 중 날짜 형식이거나 날짜 관련 속성이 있는 것
    if len(date_fields) < 2:
        for inp in page.query_selector_all('input[type="text"], input:not([type])'):
            try:
                box = inp.bounding_box()
                if not box or box["y"] > 300 or box.get("width", 0) < 60:
                    continue
                value = inp.get_attribute("value") or ""
                placeholder = inp.get_attribute("placeholder") or ""
                cls = inp.get_attribute("class") or ""
                name = inp.get_attribute("name") or ""
                # 날짜 필드 식별: 값이 날짜이거나, placeholder/class/name에 date 관련 힌트
                is_date = (
                    _looks_like_date(value)
                    or _looks_like_date(placeholder)
                    or any(k in cls.lower() for k in ["date", "calendar", "picker"])
                    or any(k in name.lower() for k in ["date", "from", "to", "start", "end"])
                    or any(k in placeholder.lower() for k in ["yyyy", "날짜", "date"])
                )
                if is_date:
                    # 기존 목록에 같은 요소가 없는 경우만 추가
                    if not any(f[1] == inp for f in date_fields):
                        date_fields.append((box["x"], inp, value, "text-hint"))
            except Exception:
                continue

    # 전략 3: 검색 영역(y < 200) 내 인접한 input 쌍 (구분자 ~ 사이)
    if len(date_fields) < 2:
        all_inputs = []
        for inp in page.query_selector_all('input[type="text"], input:not([type])'):
            try:
                box = inp.bounding_box()
                if box and box["y"] < 250 and 70 < box.get("width", 0) < 200:
                    value = inp.get_attribute("value") or ""
                    all_inputs.append((box["x"], box["y"], inp, value))
            except Exception:
                continue
        # y좌표가 비슷한 인접 쌍 찾기 (같은 행의 시작일~종료일)
        all_inputs.sort(key=lambda x: (round(x[1] / 30), x[0]))  # 행별 그룹, x순 정렬
        for i in range(len(all_inputs) - 1):
            ax, ay, a_inp, a_val = all_inputs[i]
            bx, by, b_inp, b_val = all_inputs[i + 1]
            if abs(ay - by) < 15 and 30 < (bx - ax) < 400:
                # 이미 수집한 것과 중복 체크
                existing = {id(f[1]) for f in date_fields}
                if id(a_inp) not in existing and id(b_inp) not in existing:
                    date_fields = [(ax, a_inp, a_val, "pair"), (bx, b_inp, b_val, "pair")]
                    log.info(f"[PO_SKU] 인접 input 쌍으로 날짜 필드 추론 (y≈{ay:.0f})")
                    break

    if len(date_fields) >= 2:
        date_fields.sort(key=lambda x: x[0])
        log.info(f"[PO_SKU] 날짜 필드 {len(date_fields)}개 발견 (방법: {date_fields[0][3]}, {date_fields[1][3]})")
        _fill_date(page, date_fields[0][1], start_date)
        short_delay(0.5, 1)
        _fill_date(page, date_fields[1][1], end_date)
        log.info(f"[PO_SKU] 날짜 설정 완료: {start_date} ~ {end_date}")
    else:
        log.warning(f"[PO_SKU] 날짜 필드 {len(date_fields)}개 발견 (2개 필요)")
        # 디버그: 상단 input 전체 덤프
        _dump_inputs(page)
        screenshot(page, "order_sku_date_fields_debug")


def _fill_date(page, input_el, date_str):
    """날짜 입력 필드에 값 설정. 키보드 입력 → JS 직접설정 → React setter 순 시도."""
    old_val = input_el.get_attribute("value") or ""

    # 시도 1: 키보드 입력 (가장 자연스러움)
    try:
        input_el.click()
        short_delay(0.3, 0.5)
        page.keyboard.press("Control+a")
        short_delay(0.1, 0.2)
        page.keyboard.type(date_str, delay=50)
        short_delay(0.3, 0.5)
        page.keyboard.press("Escape")
        short_delay(0.2, 0.3)
        page.keyboard.press("Tab")
        short_delay(0.3, 0.5)
        new_val = input_el.get_attribute("value") or ""
        if new_val != old_val:
            log.info(f"[PO_SKU] 날짜 입력 성공 (keyboard): {old_val} → {new_val}")
            return
    except Exception as e:
        log.warning(f"[PO_SKU] 키보드 입력 실패: {e}")

    # 시도 2: JS로 값 설정 + React input 이벤트 트리거
    try:
        input_el.evaluate(
            '''(el, val) => {
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, "value"
                ).set;
                nativeInputValueSetter.call(el, val);
                el.dispatchEvent(new Event("input", {bubbles: true}));
                el.dispatchEvent(new Event("change", {bubbles: true}));
            }''',
            date_str,
        )
        short_delay(0.3, 0.5)
        new_val = input_el.get_attribute("value") or ""
        log.info(f"[PO_SKU] 날짜 입력 (JS setter): {old_val} → {new_val}")
    except Exception as e:
        log.warning(f"[PO_SKU] JS 날짜 입력도 실패: {e}")


def _looks_like_date(value):
    """값이 날짜 형식인지 확인 (다양한 포맷 지원)."""
    if not value or len(value) < 6:
        return False
    v = value.strip()
    # YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD
    if any(sep in v for sep in ["-", "/", "."]) and sum(c.isdigit() for c in v) >= 6:
        return True
    # YYYYMMDD (구분자 없음)
    if v.isdigit() and len(v) == 8:
        return True
    # MM/DD/YYYY 등
    if sum(c.isdigit() for c in v) >= 6 and len(v) <= 12:
        return True
    return False


def _dump_inputs(page):
    """디버그: 상단 영역 input 요소 전체 덤프."""
    inputs = page.query_selector_all("input")
    for i, inp in enumerate(inputs):
        try:
            box = inp.bounding_box()
            if not box or box["y"] > 350:
                continue
            attrs = {
                "type": inp.get_attribute("type") or "",
                "name": inp.get_attribute("name") or "",
                "value": inp.get_attribute("value") or "",
                "placeholder": inp.get_attribute("placeholder") or "",
                "class": (inp.get_attribute("class") or "")[:60],
            }
            log.info(
                f"[DEBUG INPUT #{i}] x={box['x']:.0f} y={box['y']:.0f} "
                f"w={box.get('width', 0):.0f} | {attrs}"
            )
        except Exception:
            continue


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
