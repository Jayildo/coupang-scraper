"""
메인 스크래퍼: 1회 로그인 → 4개 태스크 순차 실행.

사용법:
    cd src/
    python scraper.py

환경변수:
    SCRAPER_HEADLESS    브라우저 GUI 숨김 (default: true) — Mac Mini 스케줄 실행 시 필수
    SCRAPER_UNATTENDED  무인 모드 (default: false) — 2FA·로그인 실패 시 즉시 종료

종료 코드:
    0 = 모든 태스크 성공
    1 = 1개 이상 태스크 실패 또는 치명적 에러

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
from logging.handlers import RotatingFileHandler

from scrapling.fetchers import StealthyFetcher

from config import (
    COUPANG_ID, COUPANG_PW, LOGIN_URL,
    COOKIE_FILE, DATA_DIR, LOGS_DIR, MIN_DELAY, MAX_DELAY,
    HEADLESS, UNATTENDED,
)
from tasks.helpers import human_delay, short_delay, screenshot, ensure_dirs
from tasks import milkrun, sku_info, order_sku, analytics

# 로그 디렉터리 보장 + 회전 파일 핸들러 (스케줄 실행 시 무한 누적 방지)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = LOGS_DIR / "scraper.log"
_file_handler = RotatingFileHandler(
    _LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_stream_handler, _file_handler])
log = logging.getLogger(__name__)

# 태스크 결과를 모듈 레벨에서 추적 (page_action 콜백에서 채워짐 → run()에서 exit code 결정)
_TASK_RESULTS: dict = {}
_FATAL_ERROR: str | None = None


def _login(page):
    """로그인 수행. 이미 로그인 상태면 스킵."""
    # xauth.coupang.com은 로딩이 느릴 수 있음 - 충분히 대기
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception as e:
        log.debug(f"[LOGIN] 초기 networkidle 대기 타임아웃: {e}")
    time.sleep(5)

    # 이미 대시보드로 리다이렉트됐으면 로그인 스킵
    if "dashboard" in page.url or ("supplier.coupang.com" in page.url and "login" not in page.url):
        log.info(f"[LOGIN] 이미 로그인됨: {page.url}")
        return True

    # 로그인 폼 대기 (최대 2회 재시도, 총 45초)
    id_input = None
    pw_input = None
    for attempt in range(3):
        try:
            page.wait_for_selector('input[name="username"]', timeout=15000)
        except Exception:
            log.info(f"[LOGIN] 로그인 폼 대기 중... (시도 {attempt + 1}/3)")
            time.sleep(5)
            continue
        id_input = page.query_selector('input[name="username"]')
        pw_input = page.query_selector('input[name="password"]')
        if id_input and pw_input:
            break

    if not id_input or not pw_input:
        # 혹시 리다이렉트로 이미 로그인됐을 수 있음
        if "dashboard" in page.url:
            log.info(f"[LOGIN] 리다이렉트로 로그인 완료: {page.url}")
            return True
        log.error(f"[LOGIN] 로그인 폼 없음! URL: {page.url}")
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
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception as e:
        log.debug(f"[LOGIN] 로그인 후 networkidle 대기 타임아웃: {e}")
    time.sleep(3)

    # 2단계 인증(2FA) 감지 및 대기
    if _handle_2fa(page):
        log.info(f"[LOGIN] 2FA 완료 후 로그인 성공: {page.url}")
    else:
        log.info(f"[LOGIN] 로그인 완료: {page.url}")
    return True


def _handle_2fa(page, max_wait=180):
    """2단계 인증 페이지 감지 → 사용자가 브라우저에서 직접 인증 완료할 때까지 대기.

    UNATTENDED 모드에서는 즉시 fatal로 처리 (스케줄 실행 시 사용자 부재).
    """
    global _FATAL_ERROR
    try:
        body_text = page.inner_text("body")[:3000]
    except Exception:
        return False

    # 2FA 페이지 감지 키워드
    if not any(k in body_text for k in ["2단계 인증", "인증번호를 전송할", "Two-Factor", "Verify your identity"]):
        return False

    if UNATTENDED:
        _FATAL_ERROR = "2FA required but UNATTENDED mode is on — manual intervention needed"
        log.error(f"[2FA] {_FATAL_ERROR}")
        screenshot(page, "2fa_unattended_blocked")
        return False

    log.info("[2FA] 2단계 인증 감지! 브라우저에서 직접 인증해주세요.")
    log.info(f"[2FA] 최대 {max_wait}초 대기합니다...")
    screenshot(page, "2fa_detected")

    start = time.time()
    while time.time() - start < max_wait:
        time.sleep(5)
        current_url = page.url
        # 대시보드 또는 supplier 메인으로 리다이렉트되면 인증 완료
        if "dashboard" in current_url or ("supplier.coupang.com" in current_url and "login" not in current_url and "xauth" not in current_url):
            log.info(f"[2FA] 인증 완료 감지: {current_url}")
            time.sleep(3)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception as e:
                log.debug(f"[2FA] 완료 후 networkidle 대기 타임아웃: {e}")
            return True
        elapsed = int(time.time() - start)
        if elapsed % 30 == 0 and elapsed > 0:
            log.info(f"[2FA] 대기 중... ({elapsed}s/{max_wait}s)")

    log.warning(f"[2FA] {max_wait}초 초과 - 인증 미완료")
    return False


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

    # 태스크 목록 (SCRAPER_TASKS 환경변수로 일부만 실행 가능, 예: "1,4" 또는 "milkrun,analytics")
    all_tasks = [
        ("밀크런 이용 요금", "milkrun", milkrun.run),
        ("SKU 정보 관리", "sku_info", sku_info.run),
        ("발주 SKU 리스트", "order_sku", order_sku.run),
        ("프리미엄 데이터 2.0", "analytics", analytics.run),
    ]
    import os as _os
    filt = _os.getenv("SCRAPER_TASKS", "").strip()
    if filt:
        keys = [k.strip().lower() for k in filt.split(",") if k.strip()]
        tasks = [
            (n, fn) for i, (n, k, fn) in enumerate(all_tasks, start=1)
            if k in keys or str(i) in keys
        ]
        log.info(f"[SCRAPER] 필터 적용: {filt} → {len(tasks)}개 태스크")
    else:
        tasks = [(n, fn) for n, _, fn in all_tasks]

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

    # 모듈 레벨에 결과 저장 → run()에서 exit code 결정에 사용
    _TASK_RESULTS.update(results)
    return page


def _validate_credentials() -> bool:
    """자격증명 누락 시 즉시 실패 (silent None 로그인 방지)."""
    global _FATAL_ERROR
    if not COUPANG_ID or not COUPANG_PW:
        _FATAL_ERROR = "COUPANG_ID/COUPANG_PW not set in .env"
        log.error(f"[SCRAPER] {_FATAL_ERROR}")
        return False
    return True


def _emit_status(exit_code: int):
    """OpenClaw가 stdout에서 파싱할 수 있는 최종 JSON 상태 라인."""
    status = {
        "timestamp": datetime.now().isoformat(),
        "exit_code": exit_code,
        "fatal_error": _FATAL_ERROR,
        "tasks": _TASK_RESULTS,
        "headless": HEADLESS,
        "unattended": UNATTENDED,
    }
    # 마지막 라인에 단일 JSON으로 출력 (로그 핸들러 우회 → 파싱 친화적)
    print("SCRAPER_STATUS=" + json.dumps(status, ensure_ascii=False))


def run() -> int:
    """스크래퍼 실행. 종료 코드 반환 (0=성공, 1=실패)."""
    global _FATAL_ERROR
    ensure_dirs()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    log.info("[SCRAPER] 스크래퍼 시작")
    log.info(f"[SCRAPER] 모드: headless={HEADLESS}, unattended={UNATTENDED}")

    if not _validate_credentials():
        return 1

    log.info(f"[SCRAPER] 계정: {COUPANG_ID}")
    log.info(f"[SCRAPER] 다운로드 폴더: {DATA_DIR / 'downloads'}")

    try:
        page = StealthyFetcher.fetch(
            LOGIN_URL,
            headless=HEADLESS,
            disable_resources=False,
            page_action=_main_action,
            wait_selector="body",
        )
    except Exception as e:
        _FATAL_ERROR = f"Browser launch failed: {e}"
        log.error(f"[SCRAPER] {_FATAL_ERROR}", exc_info=True)
        return 1

    if not page:
        _FATAL_ERROR = _FATAL_ERROR or "Browser fetch returned None"
        log.error(f"[SCRAPER] {_FATAL_ERROR}")
        return 1

    if _FATAL_ERROR:
        log.error(f"[SCRAPER] 치명적 에러 발생: {_FATAL_ERROR}")
        return 1

    # 한 개라도 실패면 exit 1
    failed = [n for n, r in _TASK_RESULTS.items() if r != "성공"]
    if failed:
        log.error(f"[SCRAPER] 실패 태스크: {failed}")
        return 1

    log.info("[SCRAPER] 완료 — 모든 태스크 성공")
    return 0


if __name__ == "__main__":
    code = run()
    _emit_status(code)
    sys.exit(code)
