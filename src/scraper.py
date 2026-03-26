"""
메인 스크래퍼: 1회 로그인 → 4개 태스크 순차 실행.

사용법:
    cd src/
    python scraper.py

태스크:
    1. 밀크런 이용 요금 스크랩
    2. SKU 정보 관리 엑셀 다운로드
    3. 발주 SKU 리스트 다운로드 (D+1~D+30)
    4. 프리미엄 데이터 2.0 다운로드 (당월)
"""
import sys
import time
import json
import logging
from datetime import datetime

from scrapling.fetchers import StealthyFetcher

from config import (
    COUPANG_ID, COUPANG_PW, LOGIN_URL,
    COOKIE_FILE, DATA_DIR, MIN_DELAY, MAX_DELAY,
)
from tasks.helpers import human_delay, short_delay, screenshot, ensure_dirs
from tasks import milkrun, sku_info, order_sku, analytics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            DATA_DIR / f"scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger(__name__)


def _login(page):
    """로그인 수행. 이미 로그인 상태면 스킵."""
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    # 이미 대시보드로 리다이렉트됐으면 로그인 스킵
    if "dashboard" in page.url or "supplier.coupang.com" in page.url and "login" not in page.url:
        log.info(f"[LOGIN] 이미 로그인됨: {page.url}")
        return True

    try:
        page.wait_for_selector('input[name="username"]', timeout=15000)
    except Exception:
        # 페이지 로딩이 느린 경우 추가 대기
        time.sleep(5)

    id_input = page.query_selector('input[name="username"]')
    pw_input = page.query_selector('input[name="password"]')

    if not id_input or not pw_input:
        # 혹시 리다이렉트로 이미 로그인됐을 수 있음
        if "dashboard" in page.url:
            log.info(f"[LOGIN] 리다이렉트로 로그인 완료: {page.url}")
            return True
        log.error("[LOGIN] 로그인 폼 없음!")
        screenshot(page, "login_no_form")
        return False

    # 사람처럼 천천히 입력
    id_input.click()
    short_delay(0.3, 0.8)
    id_input.type(COUPANG_ID, delay=80)
    short_delay(0.5, 1.0)

    pw_input.click()
    short_delay(0.2, 0.5)
    pw_input.type(COUPANG_PW, delay=80)
    short_delay(0.5, 1.0)

    # 로그인 버튼 클릭
    submit = page.query_selector('button:has-text("로그인"), button[type="submit"]')
    if submit:
        submit.click()
    else:
        pw_input.press("Enter")

    time.sleep(5)
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    log.info(f"[LOGIN] 로그인 완료: {page.url}")
    return True


def _save_cookies(page):
    """브라우저 쿠키 저장 (HTTP 세션 재사용 대비)."""
    try:
        cookies = page.context.cookies()
        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        log.info(f"[COOKIES] {len(cookies)}개 쿠키 저장 → {COOKIE_FILE}")
    except Exception as e:
        log.warning(f"[COOKIES] 저장 실패: {e}")


def _switch_to_korean(page):
    """UI 언어를 한국어로 전환. 쿠키 + UI 클릭 이중 전략."""

    # 이미 한국어인지 확인
    if _is_korean(page):
        log.info("[LANG] 이미 한국어 UI")
        return True

    # 전략 1: locale 쿠키 직접 설정 (가장 안정적)
    cookie_set = _set_locale_cookie(page)

    # 전략 2: UI 드롭다운 클릭 (폴백)
    if not cookie_set:
        _click_language_ui(page)

    # 전략 3: URL 파라미터로 locale 강제
    _navigate_with_locale(page)

    # 검증
    if _is_korean(page):
        log.info("[LANG] 한국어 전환 성공")
        return True

    log.warning("[LANG] 한국어 전환 불확실 - 한/영 양쪽 텍스트로 폴백 동작")
    return False


def _is_korean(page):
    """현재 페이지가 한국어 UI인지 확인."""
    try:
        # 상단 네비게이션에서 한국어 텍스트 존재 확인
        body_text = page.inner_text("body")[:2000]
        kr_indicators = ["대시보드", "물류", "정산", "광고", "상품", "한국어"]
        en_indicators = ["Dashboard", "Logistics", "Settlement", "Marketing", "English"]
        kr_count = sum(1 for k in kr_indicators if k in body_text)
        en_count = sum(1 for k in en_indicators if k in body_text)
        return kr_count > en_count
    except Exception:
        return False


def _set_locale_cookie(page):
    """브라우저 쿠키로 locale을 ko-KR로 설정."""
    try:
        # 쿠팡 supplier hub에서 사용하는 locale 쿠키 후보
        locale_cookies = [
            {"name": "locale", "value": "ko_KR", "domain": ".coupang.com", "path": "/"},
            {"name": "lang", "value": "ko", "domain": ".coupang.com", "path": "/"},
            {"name": "LOCALE", "value": "ko_KR", "domain": ".coupang.com", "path": "/"},
            {"name": "locale", "value": "ko_KR", "domain": "supplier.coupang.com", "path": "/"},
            {"name": "lang", "value": "ko", "domain": "supplier.coupang.com", "path": "/"},
        ]
        page.context.add_cookies(locale_cookies)
        log.info("[LANG] locale 쿠키 설정: ko_KR")
        return True
    except Exception as e:
        log.warning(f"[LANG] 쿠키 설정 실패: {e}")
        return False


def _click_language_ui(page):
    """UI 드롭다운으로 언어 전환."""
    try:
        lang_selectors = [
            'button:has-text("English")',
            'a:has-text("English")',
            'span:has-text("English")',
            '[class*="lang"]',
            '[class*="locale"]',
        ]
        for sel in lang_selectors:
            els = page.query_selector_all(sel)
            for el in els:
                try:
                    box = el.bounding_box()
                    if box and box["y"] < 60:
                        el.click()
                        short_delay(1, 2)
                        for kr in ['한국어', 'Korean', 'ko-KR', 'ko']:
                            kr_el = page.query_selector(
                                f'a:has-text("{kr}"), li:has-text("{kr}"), '
                                f'div:has-text("{kr}"), option:has-text("{kr}")'
                            )
                            if kr_el:
                                kr_el.click()
                                log.info("[LANG] UI 클릭으로 한국어 전환")
                                time.sleep(3)
                                try:
                                    page.wait_for_load_state("networkidle", timeout=15000)
                                except Exception:
                                    pass
                                time.sleep(2)
                                return True
                except Exception:
                    continue
    except Exception as e:
        log.warning(f"[LANG] UI 전환 실패: {e}")
    return False


def _navigate_with_locale(page):
    """현재 페이지를 locale 파라미터 포함하여 새로고침."""
    try:
        current_url = page.url
        # /KR 경로가 있으면 유지, locale 쿠키가 설정된 상태에서 reload
        page.reload()
        time.sleep(3)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        time.sleep(2)
        log.info(f"[LANG] 페이지 리로드 완료: {page.url}")
    except Exception as e:
        log.warning(f"[LANG] 리로드 실패: {e}")


def _main_action(page):
    """메인 page_action: 로그인 → 한국어 전환 → 모든 태스크 실행."""
    # 로그인
    if not _login(page):
        return page

    # 한국어 UI로 전환
    _switch_to_korean(page)
    screenshot(page, "after_korean_switch")

    # 쿠키 저장 (HTTP 재사용 대비)
    _save_cookies(page)

    # 태스크 목록 (난이도순)
    tasks = [
        ("밀크런 요금 스크랩", milkrun.run),
        ("SKU 정보 관리", sku_info.run),
        ("발주 SKU 리스트", order_sku.run),
        ("프리미엄 데이터 2.0", analytics.run),
    ]

    results = {}
    for name, task_fn in tasks:
        log.info(f"\n{'='*60}")
        log.info(f"[SCRAPER] 태스크 시작: {name}")
        log.info(f"{'='*60}")

        # 태스크 간 충분한 대기 (차단 방지)
        human_delay(MIN_DELAY, MAX_DELAY)

        try:
            success = task_fn(page)
            results[name] = "성공" if success else "실패"
            log.info(f"[SCRAPER] {name}: {'성공' if success else '실패'}")
        except Exception as e:
            results[name] = f"에러: {e}"
            log.error(f"[SCRAPER] {name} 에러: {e}", exc_info=True)
            screenshot(page, f"error_{name.replace(' ', '_')}")

    # 결과 요약
    log.info(f"\n{'='*60}")
    log.info("[SCRAPER] 전체 결과:")
    for name, result in results.items():
        log.info(f"  {name}: {result}")
    log.info(f"{'='*60}")

    return page


def run():
    """스크래퍼 실행."""
    ensure_dirs()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    log.info("[SCRAPER] 스크래퍼 시작")
    log.info(f"[SCRAPER] 계정: {COUPANG_ID}")
    log.info(f"[SCRAPER] 다운로드 폴더: {DATA_DIR / 'downloads'}")

    page = StealthyFetcher.fetch(
        LOGIN_URL,
        headless=False,
        disable_resources=False,
        page_action=_main_action,
        wait_selector="body",
    )

    if page:
        log.info("[SCRAPER] 완료")
    else:
        log.error("[SCRAPER] 브라우저 실행 실패")


if __name__ == "__main__":
    run()
