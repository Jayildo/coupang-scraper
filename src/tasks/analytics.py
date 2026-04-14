"""Task 4: 프리미엄 데이터 2.0 > 일간 종합 성과 지표 > 당월 데이터 다운로드.

쿠팡이 /rpd/web-v2/ SPA를 Akamai Bot Manager로 보호하므로 Playwright로 SPA를
mount할 수 없음. 대신 빌드된 main bundle JS를 분석해 식별한 비동기 다운로드
API를 curl_cffi로 직접 호출.

API 흐름:
    1. GET  /rpd/v2/asyncdownload/requests?reportId=DAILY_PERF  → vendorId 추출
    2. POST /rpd/v2/asyncdownload/request                       → 비동기 job 생성
    3. GET  /rpd/v2/asyncdownload/requests (polling)            → status COMPLETED 대기
    4. GET  /rpd/v2/asyncdownload/request/{reqId}/file/{fileId}/download → CSV bytes
"""
import json
import time
import logging
from datetime import date, datetime, timedelta

from tasks.helpers import DOWNLOAD_DIR, ensure_dirs

log = logging.getLogger(__name__)

API_BASE = "https://supplier.coupang.com/rpd/v2/asyncdownload"
REPORT_ID = "DAILY_PERF"
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Referer": "https://supplier.coupang.com/rpd/web-v2/",
}


def run(page):
    """프리미엄 데이터 2.0 일간 종합 성과 지표 다운로드 (API 직접 호출)."""
    log.info("=" * 50)
    log.info("[TASK] 프리미엄 데이터 2.0 다운로드 시작 (API 모드)")

    # 브라우저 쿠키를 .cookies.json에 갱신 (Akamai BM 토큰 포함)
    _refresh_cookies(page)

    from session import get_http_session
    session = get_http_session()
    if not session:
        log.error("[ANALYTICS] HTTP 세션 생성 실패 — 쿠키 없음")
        return False

    # 1. vendorId 추출 (기존 history에서)
    vendor_id = _fetch_vendor_id(session)
    if not vendor_id:
        log.error("[ANALYTICS] vendorId 추출 실패")
        return False
    log.info(f"[ANALYTICS] vendorId: {vendor_id}")

    # 2. 당월 1일 ~ 어제 (D-1) 기간으로 다운로드 요청
    today = date.today()
    from_date = today.replace(day=1).strftime("%Y%m%d")
    to_date = (today - timedelta(days=1)).strftime("%Y%m%d")
    log.info(f"[ANALYTICS] 기간: {from_date} ~ {to_date}")

    request_id = _create_download_request(session, vendor_id, from_date, to_date)
    if not request_id:
        log.error("[ANALYTICS] 다운로드 요청 생성 실패")
        return False
    log.info(f"[ANALYTICS] 요청 생성됨: requestId={request_id}")

    # 3. polling
    file_info = _poll_until_complete(session, request_id, max_wait=180)
    if not file_info:
        log.error("[ANALYTICS] 파일 생성 대기 시간 초과")
        return False

    # 4. 다운로드
    saved = _download_file(session, request_id, file_info)
    if saved:
        log.info(f"[ANALYTICS] 다운로드 완료: {saved}")
        return True
    else:
        log.error("[ANALYTICS] 파일 다운로드 실패")
        return False


def _refresh_cookies(page):
    """브라우저 컨텍스트의 최신 쿠키를 .cookies.json에 저장 (Akamai BM 토큰 갱신)."""
    try:
        from config import COOKIE_FILE
        cookies = page.context.cookies()
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        log.info(f"[ANALYTICS] 쿠키 {len(cookies)}개 갱신")
    except Exception as e:
        log.warning(f"[ANALYTICS] 쿠키 갱신 실패: {e}")


def _fetch_vendor_id(session):
    """기존 history 첫 항목의 predicate에서 vendorId 추출."""
    try:
        r = session.get(
            f"{API_BASE}/requests",
            params={"reportId": REPORT_ID, "page": 1, "rowCountPerPage": 10},
            headers=DEFAULT_HEADERS,
            timeout=30,
        )
        if r.status_code != 200:
            log.error(f"[ANALYTICS] history GET 실패: status={r.status_code}")
            return None
        data = r.json()
        if not data.get("success"):
            log.error(f"[ANALYTICS] history 응답 success=false: {data.get('message')}")
            return None
        contents = data.get("value", {}).get("contents", [])
        for item in contents:
            pred_str = item.get("predicate")
            if not pred_str:
                continue
            try:
                pred = json.loads(pred_str)
                vid = pred.get("vendorId")
                if vid:
                    return vid
            except json.JSONDecodeError:
                continue
        log.error("[ANALYTICS] history 비어있음 - vendorId 추출 불가")
        return None
    except Exception as e:
        log.error(f"[ANALYTICS] vendorId fetch 에러: {e}")
        return None


def _create_download_request(session, vendor_id, from_date, to_date):
    """비동기 다운로드 요청 생성. requestId 반환."""
    filename = f"daily_performance_{from_date}{to_date}"
    body = {
        "reportId": REPORT_ID,
        "filename": filename,
        "comment": "일간 종합 성과 지표",
        "parameter": {
            "timeType": "DATE",
            "from": from_date,
            "to": to_date,
            "vendorId": vendor_id,
        },
    }
    try:
        r = session.post(
            f"{API_BASE}/request",
            json=body,
            headers={**DEFAULT_HEADERS, "Content-Type": "application/json"},
            timeout=30,
        )
        if r.status_code != 200:
            log.error(f"[ANALYTICS] POST 실패: status={r.status_code}, body={r.text[:300]}")
            return None
        data = r.json()
        if not data.get("success"):
            log.error(f"[ANALYTICS] 요청 거부: {data.get('message')}")
            return None
        return data.get("value")
    except Exception as e:
        log.error(f"[ANALYTICS] POST 에러: {e}")
        return None


def _poll_until_complete(session, request_id, max_wait=180, interval=5):
    """history GET을 polling해서 해당 requestId의 파일 정보 반환 (status COMPLETED).

    응답 contents[i].downloadExcelRequestFileDtos[0]가 채워지면 완료로 판단.
    """
    start = time.time()
    while time.time() - start < max_wait:
        try:
            r = session.get(
                f"{API_BASE}/requests",
                params={"reportId": REPORT_ID, "page": 1, "rowCountPerPage": 10},
                headers=DEFAULT_HEADERS,
                timeout=30,
            )
            if r.status_code != 200:
                log.warning(f"[ANALYTICS] polling status={r.status_code}")
                time.sleep(interval)
                continue
            contents = r.json().get("value", {}).get("contents", [])
            item = next(
                (c for c in contents if c.get("downloadExcelRequestId") == request_id),
                None,
            )
            if item:
                files = item.get("downloadExcelRequestFileDtos") or []
                status = item.get("status", "")
                if files and status.upper() in ("COMPLETED", "DONE", "SUCCESS"):
                    log.info(f"[ANALYTICS] 파일 생성 완료 (status={status})")
                    return files[0]
                elapsed = int(time.time() - start)
                log.info(f"[ANALYTICS] 생성 중... status={status} ({elapsed}s)")
            else:
                log.info(f"[ANALYTICS] requestId {request_id} 아직 history 미반영")
        except Exception as e:
            log.warning(f"[ANALYTICS] polling 에러: {e}")
        time.sleep(interval)
    return None


def _download_file(session, request_id, file_info):
    """파일 다운로드 후 로컬 저장. 저장 경로 반환."""
    file_id = file_info.get("downloadExcelRequestFileId")
    base_filename = file_info.get("downloadFileName") or f"daily_performance_{request_id}"
    if not file_id:
        log.error("[ANALYTICS] downloadExcelRequestFileId 없음")
        return None

    url = f"{API_BASE}/request/{request_id}/file/{file_id}/download"
    log.info(f"[ANALYTICS] 다운로드 URL: {url}")
    try:
        r = session.get(url, headers=DEFAULT_HEADERS, timeout=120)
    except Exception as e:
        log.error(f"[ANALYTICS] 다운로드 요청 실패: {e}")
        return None

    if r.status_code != 200 or len(r.content) < 100:
        log.error(f"[ANALYTICS] 다운로드 실패: status={r.status_code}, size={len(r.content)}")
        return None

    ensure_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = DOWNLOAD_DIR / f"analytics_premium_{ts}_{base_filename}.csv"
    with open(save_path, "wb") as f:
        f.write(r.content)
    log.info(f"[ANALYTICS] 저장 완료: {save_path} ({len(r.content)} bytes)")
    return save_path
