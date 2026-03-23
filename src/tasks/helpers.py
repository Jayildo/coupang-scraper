"""공통 헬퍼: 지연, 네비게이션, 다운로드 처리."""
import time
import random
import logging
from datetime import datetime
from pathlib import Path

from config import DATA_DIR

log = logging.getLogger(__name__)

DOWNLOAD_DIR = DATA_DIR / "downloads"


def ensure_dirs():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def human_delay(min_sec=8, max_sec=15):
    """사람처럼 랜덤 대기."""
    delay = random.uniform(min_sec, max_sec)
    log.info(f"[DELAY] {delay:.1f}s 대기...")
    time.sleep(delay)


def short_delay(min_sec=1, max_sec=3):
    """짧은 대기 (UI 조작 사이)."""
    time.sleep(random.uniform(min_sec, max_sec))


def wait_and_click(page, selector, timeout=10000, description=""):
    """셀렉터 대기 후 클릭."""
    try:
        el = page.wait_for_selector(selector, timeout=timeout)
        if el:
            short_delay(0.3, 0.8)
            el.click()
            log.info(f"[CLICK] {description or selector}")
            return True
    except Exception as e:
        log.warning(f"[CLICK FAIL] {description or selector}: {e}")
    return False


def click_text(page, text, tag="button,a", y_min=None, y_max=None, timeout=10000):
    """텍스트로 요소 찾아 클릭. y 범위로 필터링 가능."""
    try:
        page.wait_for_selector(f'{tag}:has-text("{text}")', timeout=timeout)
    except Exception:
        pass

    elements = page.query_selector_all(f'{tag}:has-text("{text}")')
    for el in elements:
        try:
            inner = (el.inner_text() or "").strip()
            if text not in inner:
                continue
            if y_min is not None or y_max is not None:
                box = el.bounding_box()
                if not box:
                    continue
                if y_min and box["y"] < y_min:
                    continue
                if y_max and box["y"] > y_max:
                    continue
            short_delay(0.3, 0.8)
            el.click()
            log.info(f"[CLICK] '{text}'")
            return True
        except Exception:
            continue
    log.warning(f"[NOT FOUND] '{text}'")
    return False


def navigate_menu(page, main_menu, sub_menu=None):
    """메인 메뉴 → 서브 메뉴 네비게이션."""
    kr_main = {
        "물류": "Logistics",
        "애널리틱스": "Analytics",
        "정산": "Settlement",
        "광고 관리": "Marketing",
    }
    en_name = kr_main.get(main_menu, main_menu)

    # 메인 메뉴 클릭 (한글/영문 모두 시도)
    for name in [main_menu, en_name]:
        links = page.query_selector_all(f'li > a:has-text("{name}")')
        if not links:
            links = page.query_selector_all(f'a:has-text("{name}")')
        for link in links:
            try:
                box = link.bounding_box()
                if box and box["y"] < 80:
                    link.click()
                    log.info(f"[NAV] 메인: {name}")
                    time.sleep(3)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    time.sleep(2)

                    if sub_menu:
                        return _click_submenu(page, sub_menu)
                    return True
            except Exception:
                continue

    log.warning(f"[NAV FAIL] 메인 메뉴 '{main_menu}' 못 찾음")
    return False


def _click_submenu(page, text):
    """서브 메뉴 클릭 (y 30~150 범위)."""
    # 한글 우선 + 영문 폴백 (한국어 전환 후 사용)
    sub_aliases = {
        "밀크런": ["밀크런", "Milkrun"],
        "상품 공급상태 관리": ["상품 공급상태 관리", "상품공급상태", "Product and supply management"],
        "발주 SKU 리스트": ["발주SKU리스트", "발주 SKU 리스트", "PO SKU List"],
        "프리미엄 데이터 2.0": ["프리미엄 데이터 2.0", "Premium data 2.0"],
        "SKU 정보 관리": ["SKU 정보 관리", "SKU Information"],
        "입고 이력": ["입고 이력", "Inbound history"],
        "요약": ["요약", "Summary"],
        "발주 일정": ["발주 일정", "Purchase Order Scheduling"],
    }
    candidates = [text]
    if text in sub_aliases:
        candidates.extend(sub_aliases[text])

    for name in candidates:
        links = page.query_selector_all(f'a:has-text("{name}")')
        for link in links:
            try:
                box = link.bounding_box()
                if box and 30 < box["y"] < 200:
                    short_delay(0.5, 1.5)
                    link.click()
                    log.info(f"[NAV] 서브: {name}")
                    time.sleep(3)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    time.sleep(2)
                    return True
            except Exception:
                continue

    log.warning(f"[NAV FAIL] 서브 메뉴 '{text}' 못 찾음")
    return False


def download_file(page, click_action, filename_prefix="download"):
    """다운로드 이벤트 캡처하여 파일 저장.
    click_action: 다운로드를 트리거하는 callable (lambda page: ...)
    """
    ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        with page.expect_download(timeout=60000) as download_info:
            click_action(page)
        dl = download_info.value
        suggested = dl.suggested_filename or f"{filename_prefix}.xlsx"
        save_path = DOWNLOAD_DIR / f"{filename_prefix}_{timestamp}_{suggested}"
        dl.save_as(str(save_path))
        log.info(f"[DOWNLOAD] 저장: {save_path}")
        return save_path
    except Exception as e:
        log.error(f"[DOWNLOAD FAIL] {e}")
        return None


def save_text(content, filename):
    """텍스트 내용을 파일로 저장."""
    ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DOWNLOAD_DIR / f"{filename}_{timestamp}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    log.info(f"[SAVE] {path}")
    return path


def screenshot(page, name):
    """디버그용 스크린샷."""
    try:
        path = DATA_DIR / f"debug_{name}.png"
        page.screenshot(path=str(path), full_page=False, timeout=10000)
        log.info(f"[SCREENSHOT] {path}")
    except Exception as e:
        log.warning(f"[SCREENSHOT FAIL] {e}")
