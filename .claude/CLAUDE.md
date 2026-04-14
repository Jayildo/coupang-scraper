# Coupang Scraper (쿠팡 Supplier Hub 자동화)

## 목표
1회 로그인 → `.cookies.json` 저장 → 4개 태스크 순차 실행.
**최종 운영 환경은 Mac Mini + OpenClaw 스케줄 실행 (무인 자동화)**. Windows는 개발 전용.

## Quick Reference
- **스택**: Python 3.10+, Scrapling 0.4.1, curl_cffi
- **개발 (Windows)**: `cd src && C:/Users/JWG/anaconda3/python.exe scraper.py`
- **운영 (Mac Mini)**: `cd src && SCRAPER_HEADLESS=true SCRAPER_UNATTENDED=true python3 scraper.py`
- **의존성**: `pip install -r requirements.txt` (playwright 브라우저: `playwright install chromium`)

## 구조
```
src/
  scraper.py        # 스크래퍼 진입점 (exit code + JSON 상태 출력)
  upload.py         # Supabase 업로드 진입점 (NEW)
  config.py         # 설정 + 환경변수 플래그 + Supabase 자격증명
  session.py        # curl_cffi 세션 (sku_info.py + analytics.py 사용)
  tasks/            # 다운로드 태스크
    milkrun.py      # 밀크런 이용 요금
    sku_info.py     # SKU 정보 관리 엑셀
    order_sku.py    # 발주 SKU 리스트 (D+1~D+30)
    analytics.py    # 프리미엄 데이터 2.0 (API 직접 호출)
    helpers.py      # 공용 헬퍼
  loaders/          # Supabase 적재 (NEW)
    base.py         # client + scrape_runs 추적 + hash/chunk 헬퍼
    analytics.py    # CSV → analytics_daily UPSERT (파일럿 완료)
    # sku_info.py, po_sku.py, milkrun.py — 다음 라운드
schema/             # Supabase 스키마 SQL (NEW)
  01_analytics_daily.sql
  02_sku_info.sql
  03_po_sku.sql           # current + history 분리
  04_milkrun_fee_versions.sql
  05_scrape_runs.sql
  06_rls_policies.sql
```

## 환경변수 (운영 플래그)
| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SCRAPER_HEADLESS` | `true` | 브라우저 GUI 숨김. 스케줄 실행 시 `true` 필수 |
| `SCRAPER_UNATTENDED` | `false` | 무인 모드. 2FA 감지 시 즉시 종료 (code 1) |
| `SCRAPER_TASKS` | (없음) | 콤마로 일부만 실행. 예: `po_sku` 또는 `1,4` |
| `COUPANG_ID` / `COUPANG_PW` | 없음 (필수) | `.env`에서 로드 |
| `SUPABASE_URL` | 없음 (upload 시 필수) | 프로젝트 URL |
| `SUPABASE_SERVICE_ROLE_KEY` | 없음 (upload 시 필수) | service_role 키 (RLS 우회) |

## 종료 코드 & 상태 출력
- **exit 0**: 모든 태스크 성공
- **exit 1**: 1개 이상 실패 또는 치명적 에러 (자격증명 누락, 브라우저 실행 실패, 2FA 무인 차단)
- **stdout 마지막 라인**: `SCRAPER_STATUS={"exit_code":0,"tasks":{...},...}` — OpenClaw가 파싱

## Supabase 자동 적재 (ETL)

스크래핑(다운로드)과 업로드(적재)를 분리:
```
[scraper.py]  →  data/downloads/*.csv,xlsx,txt  →  [upload.py]  →  Supabase
```

### 데이터별 적재 패턴 (이유는 schema/*.sql 참조)
| 태스크 | 패턴 | 키 | 비고 |
|---|---|---|---|
| analytics | **시계열 UPSERT** | (date, sku_id, vendor_item_id) | D-1 확정 후 불변 |
| sku_info | **마스터 + content_hash** | sku_id | hash 변경 시 last_changed_at, 사라지면 is_active=false |
| po_sku | **현재 + 이력 분리** | (po_id, sku_id) | po_sku_current(미러) + po_sku_history(append-only) |
| milkrun | **버전 관리** | content_hash UNIQUE | 내용 동일하면 last_seen만 갱신 |

### 핵심 원칙
- **idempotent**: 같은 파일을 두 번 업로드해도 같은 결과 (UPSERT 기반)
- **소프트 삭제**: 쿠팡 화면에서 사라진 row는 `is_active=false` + history에 'REMOVED' marker
- **scrape_runs**: 모든 실행을 메타 테이블에 추적 (감사 로그 + 롤백 가능)
- **RLS**: default deny, 스크래퍼는 service_role_key로 우회. 클라이언트는 SELECT만

### 사용법
```bash
# 가장 최근 다운로드 자동 사용
cd src && python upload.py analytics
cd src && python upload.py po_sku
cd src && python upload.py sku_info
cd src && python upload.py milkrun
cd src && python upload.py all                # 4개 일괄 (milkrun → sku_info → po_sku → analytics)

# 특정 파일 지정
cd src && python upload.py analytics ../data/downloads/analytics_premium_20260410_*.csv
```
- 마지막 라인에 `UPLOAD_STATUS={...}` JSON 출력 (OpenClaw 파싱용)
- 로그: `logs/upload.log` (RotatingFileHandler 5MB×5)
- 모든 적재는 **idempotent** — 같은 파일 재실행해도 row 수 변화 없음

### 스케줄 분리 (OpenClaw)
| 데이터 | 권장 빈도 | 명령 |
|---|---|---|
| po_sku | **하루 4–6회** | `SCRAPER_TASKS=order_sku python scraper.py && python upload.py po_sku` |
| analytics, sku_info | 새벽 1회 | `SCRAPER_TASKS=sku_info,analytics python scraper.py && python upload.py analytics` |
| milkrun | 주 1회 | `SCRAPER_TASKS=milkrun python scraper.py && python upload.py milkrun` |

### 스키마 적용 (최초 1회)
1. Supabase Studio → SQL Editor
2. `schema/01_~06_*.sql` 순서대로 실행
3. Settings → API → service_role 키 복사 → `.env`의 `SUPABASE_SERVICE_ROLE_KEY`

### 현재 구현 상태 (2026-04-10 검증 완료)
- ✅ schema 6개 적용 (Supabase project: `cyjhuqsyzatrktpguurj`)
- ✅ loaders/base.py — client + scrape_runs + content_hash 헬퍼
- ✅ loaders/analytics.py — 35컬럼, 7,182 rows 적재 + 멱등성 검증
- ✅ loaders/po_sku.py — 23컬럼, 3,321 rows current+history 적재 + 멱등성 검증 (변경 없으면 history INSERT 0)
- ✅ loaders/sku_info.py — 17컬럼, 3,653 rows 적재 + 멱등성 검증 (raw_data jsonb 보존)
- ✅ loaders/milkrun.py — content_hash UNIQUE, 1 row 적재 + 동일 내용 재실행 시 last_seen만 갱신
- ✅ upload.py — CLI + `all` 옵션 + JSON 상태 출력

### 용량 주의
analytics_daily 한 달 기준 ≈ 25만 row × 700B = 175MB. 1년이면 2GB → **Supabase 무료 티어(500MB) 초과**.
운영 시점에 결정 필요: (a) Pro 플랜 ($25/월), (b) 6개월 retention, (c) 외부 storage(R2/S3)에 raw 보존 + DB는 집계만.

## Mac Mini + OpenClaw 운영 절차
1. **최초 쿠키 시드 (1회, 수동)**
   ```bash
   cd src
   SCRAPER_HEADLESS=false SCRAPER_UNATTENDED=false python3 scraper.py
   ```
   - 브라우저가 뜸 → 로그인 (2FA 필요 시 수동 완료)
   - `.cookies.json` 저장 확인
2. **OpenClaw 스케줄 등록** (cron 표현식)
   ```bash
   cd /path/to/coupang-scraper/src
   SCRAPER_HEADLESS=true SCRAPER_UNATTENDED=true python3 scraper.py
   ```
   - OpenClaw는 exit code 확인 + 마지막 `SCRAPER_STATUS=` JSON 라인 파싱
   - exit 1 시 알림 발송
3. **쿠키 만료 대응**: 무인 실행 중 쿠키 만료 시 2FA 트리거 가능성 있음 → 주기적(예: 주 1회) 수동 재시드 권장

## 동작 방식
브라우저 로그인 1회 → `.cookies.json` 저장 → 4개 태스크 순차 실행 → JSON 상태 출력 → exit code 종료

## 태스크 현황 (2026-04-10)
| # | 태스크 | 상태 | 비고 |
|---|--------|------|------|
| 1 | 밀크런 이용 요금 | OK | 직접 URL 폴백 포함 |
| 2 | SKU 정보 관리 엑셀 | OK | 브라우저 클릭 → curl_cffi 직접 다운로드 |
| 3 | 발주 SKU 리스트 | OK | D+1~D+30 동적, Playwright `expect_download` |
| 4 | 프리미엄 데이터 2.0 | OK | **API 직접 호출 모드** — 아래 참조 |

## Task 4 (analytics) 특이사항
쿠팡이 `/rpd/web-v2/` SPA를 **Akamai Bot Manager**로 보호하므로 Playwright가 SPA를 mount할 수 없음 (headless/headful 모두 차단). 대신 main bundle JS(`/rpd/web-v2/assets/main-*.js`)에서 비동기 다운로드 API를 식별해 curl_cffi로 직접 호출.

API 흐름 (`src/tasks/analytics.py`):
```
1. GET  /rpd/v2/asyncdownload/requests?reportId=DAILY_PERF  → vendorId 추출
2. POST /rpd/v2/asyncdownload/request                       → 비동기 job 생성 (당월 1일 ~ D-1)
3. GET  /rpd/v2/asyncdownload/requests (polling)            → status COMPLETED 대기
4. GET  /rpd/v2/asyncdownload/request/{reqId}/file/{fileId}/download  → CSV
```
- 페이지 객체(`page`)는 최신 쿠키(Akamai BM 토큰 포함)를 `.cookies.json`에 갱신하는 용도로만 사용
- 실제 다운로드는 모두 `session.get_http_session()` (curl_cffi `impersonate=chrome`)
- 쿠팡이 SPA 또는 API를 변경하면 main bundle JS를 다시 분석해야 함

## 로그
- 파일: `logs/scraper.log` (RotatingFileHandler: 5MB × 5 backup)
- stdout 동시 출력

## 미해결 / 개선 영역
- `_switch_to_korean()` 불안정 → 한/영 양쪽 텍스트 폴백으로 대응 중
- analytics API endpoint hash(`main-*.js` 파일명)가 쿠팡 빌드마다 변경됨 → bundle JS 분석은 코드 안에 hash가 hardcoded되어 있지 않으므로 영향 없음 (JSON API endpoint는 안정적)
- 쿠키 만료 자동 알림 (현재는 fatal 시 exit 1 뿐 → OpenClaw 쪽에서 감지)
- 실패 시 알림(Slack/이메일) — OpenClaw 측에서 구현
