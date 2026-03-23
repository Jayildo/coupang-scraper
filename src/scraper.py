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
    """UI 언어를 한국어로 전환 (우측 상단 언어 드롭다운)."""
    try:
        # "English" 또는 언어 드롭다운 찾기
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
                    if box and box["y"] < 50:  # 상단 네비게이션 영역
                        el.click()
                        short_delay(1, 2)
                        # 한국어 옵션 클릭
                        kr_options = ['한국어', 'Korean', 'ko-KR', 'ko']
                        for kr in kr_options:
                            kr_el = page.query_selector(f'a:has-text("{kr}"), li:has-text("{kr}"), div:has-text("{kr}"), option:has-text("{kr}")')
                            if kr_el:
                                kr_el.click()
                                log.info("[LANG] 한국어로 전환")
                                time.sleep(3)
                                try:
                                    page.wait_for_load_state("networkidle", timeout=15000)
                                except Exception:
                                    pass
                                time.sleep(3)
                                return True
                except Exception:
                    continue

        log.info("[LANG] 이미 한국어이거나 언어 버튼 못 찾음")
    except Exception as e:
        log.warning(f"[LANG] 언어 전환 실패: {e}")
    return False


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
