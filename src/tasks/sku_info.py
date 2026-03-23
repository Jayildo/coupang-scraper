"""Task 1: 물류 > 상품 공급상태 관리 > Download Excel > History 팝업에서 다운로드."""
import time
import logging

from tasks.helpers import (
    navigate_menu, human_delay, short_delay,
    download_file, screenshot, click_text, wait_and_click,
)

log = logging.getLogger(__name__)


def run(page):
    """SKU 정보 관리 엑셀 다운로드 (비동기: 요청 → 생성 대기 → 다운로드)."""
    log.info("=" * 50)
    log.info("[TASK] SKU 정보 관리 엑셀 다운로드 시작")

    # 대시보드 복귀 후 메뉴 진입
    page.goto("https://supplier.coupang.com/dashboard/KR")
    time.sleep(4)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(2)

    # 직접 URL로 SKU 공급 리스트 페이지 이동 (이전 탐색에서 확인)
    page.goto("https://supplier.coupang.com/plan/ticket/supplySkuList")
    time.sleep(4)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(5)

    screenshot(page, "sku_supply_status")
    log.info(f"[SKU] 현재 URL: {page.url}")

    if "login" in page.url.lower():
        log.error("[SKU] 세션 만료")
        return False
    # "Download Excel" / "엑셀 다운로드" 버튼 클릭 → 비동기 요청 생성
    download_texts = [
        "Download Excel", "엑셀 다운로드", "엑셀다운로드",
        "Excel Download", "Excel",
    ]
    clicked = False
    for text in download_texts:
        btns = page.query_selector_all(f'button:has-text("{text}"), a:has-text("{text}")')
        for btn in btns:
            try:
                if btn.is_visible():
                    btn.click()
                    log.info(f"[SKU] '{text}' 클릭 → 비동기 생성 요청")
                    clicked = True
                    break
            except Exception:
                continue
        if clicked:
            break

    if not clicked:
        log.error("[SKU] 다운로드 버튼 못 찾음")
        screenshot(page, "sku_no_download_btn")
        return False

    short_delay(2, 3)

    # History 팝업이 자동으로 열림
    screenshot(page, "sku_history_popup")

    # History 팝업에서 생성 완료(DONE) 대기 → 파일 다운로드
    downloaded = _wait_and_download_from_history(page)
    if downloaded:
        log.info(f"[SKU] 다운로드 완료: {downloaded}")
    else:
        log.error("[SKU] 다운로드 실패")
        screenshot(page, "sku_download_fail")

    # History 팝업 닫기
    _close_popup(page)

    return bool(downloaded)


def _wait_and_download_from_history(page, max_wait=120):
    """History 팝업에서 최상단 항목이 DONE이 될 때까지 대기 후 다운로드.
    팝업에 Auto Refresh 2s가 있으므로 자동 갱신됨.
    """
    start = time.time()
    poll_interval = 5  # 5초마다 확인

    while time.time() - start < max_wait:
        # 최상단 행의 상태 확인
        rows = page.query_selector_all("tr")
        for row in rows:
            try:
                text = (row.inner_text() or "").strip()
                if "sku_download" not in text:
                    continue

                # DONE 상태인 경우 → href 추출 후 다운로드
                if "DONE" in text:
                    log.info("[SKU] 파일 생성 완료 (DONE), 다운로드 시작")
                    return _download_done_file(page)

                # Generating 상태 → 대기
                if "Generating" in text or "생성" in text:
                    elapsed = int(time.time() - start)
                    log.info(f"[SKU] 파일 생성 중... ({elapsed}s 경과)")
                    break

            except Exception:
                continue

        time.sleep(poll_interval)

    log.warning(f"[SKU] {max_wait}초 대기 후에도 DONE 안 됨")
    return None


def _download_done_file(page):
    """DONE 상태의 최상단 파일 href 추출 → HTTP(curl_cffi)로 다운로드."""
    from tasks.helpers import DOWNLOAD_DIR, ensure_dirs
    from session import get_http_session
    from datetime import datetime
    ensure_dirs()

    rows = page.query_selector_all("tr")
    for row in rows:
        try:
            text = (row.inner_text() or "").strip()
            if "sku_download" not in text or "DONE" not in text:
                continue

            link = row.query_selector("a")
            if not link:
                continue

            href = link.get_attribute("href") or ""
            if not href:
                continue

            if href.startswith("/"):
                href = "https://supplier.coupang.com" + href

            log.info(f"[SKU] 다운로드 URL: {href[:80]}...")

            # 브라우저 쿠키를 먼저 저장 (최신 상태)
            import json
            from config import COOKIE_FILE
            try:
                cookies = page.context.cookies()
                with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

            # HTTP 세션으로 직접 다운로드
            session = get_http_session()
            if not session:
                log.error("[SKU] HTTP 세션 생성 실패")
                continue

            resp = session.get(href, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 100:
                # 파일명 추출
                cd = resp.headers.get("content-disposition", "")
                if "filename" in cd:
                    import re
                    match = re.search(r'filename[*]?=(?:UTF-8\'\'|"?)([^";]+)', cd)
                    filename = match.group(1) if match else "sku_info.xlsx"
                else:
                    filename = "sku_info.xlsx"

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = DOWNLOAD_DIR / f"sku_info_{ts}_{filename}"
                with open(save_path, "wb") as f:
                    f.write(resp.content)
                log.info(f"[SKU] HTTP 다운로드 완료: {save_path} ({len(resp.content)} bytes)")
                return save_path
            else:
                log.warning(f"[SKU] HTTP 다운로드 실패: status={resp.status_code}, size={len(resp.content)}")

        except Exception as e:
            log.warning(f"[SKU] 다운로드 실패: {e}")
            continue

    log.warning("[SKU] DONE 파일 링크 못 찾음")
    return None


def _close_popup(page):
    """History 팝업 닫기."""
    for sel in ['button:has-text("Close")', 'button:has-text("닫기")',
                '[class*="modal"] button.close', '[aria-label="Close"]',
                'button:has-text("×")', '.close']:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                short_delay(0.5, 1)
                return
        except Exception:
            continue
    page.keyboard.press("Escape")
