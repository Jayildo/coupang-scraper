# Coupang Scraper (쿠팡 Supplier Hub 자동화)

## Quick Reference
- **스택**: Python, Scrapling 0.4.1, curl_cffi
- **Python**: Anaconda `C:/Users/JWG/anaconda3/python.exe` (system python 안 됨)
- **실행**: `cd src && C:/Users/JWG/anaconda3/python.exe scraper.py`

## 구조
```
src/
  scraper.py        # 메인 진입점
  config.py         # 설정
  auth.py           # 인증 (쿠키 기반)
  session.py        # 세션 관리
  explorer.py       # 브라우저 탐색
  http_explorer.py  # HTTP 요청
  scrapers/         # 스크래퍼 모듈
  tasks/            # 태스크 구현
    milkrun.py      # 밀크런 이용 요금
    sku_info.py     # SKU 정보 관리 엑셀
    order_sku.py    # 발주 SKU 리스트
    analytics.py    # 프리미엄 데이터 2.0
    helpers.py      # 공용 헬퍼
```

## 동작 방식
브라우저 로그인 1회 → `.cookies.json` 저장 → 4개 태스크 순차 실행

## 태스크 현황 (2026-03-09)
| # | 태스크 | 상태 | 비고 |
|---|--------|------|------|
| 1 | 밀크런 이용 요금 | OK | 텍스트 7.7KB |
| 2 | SKU 정보 관리 엑셀 | OK | curl_cffi HTTP 다운로드 |
| 3 | 발주 SKU 리스트 | OK | CSV, 날짜설정 미해결 |
| 4 | 프리미엄 데이터 2.0 | OK | CSV 2.4MB |

## 미해결
- `_switch_to_korean()` 불안정 (영문 폴백 보완)
- Order SKU: 입고예정일 드롭다운 날짜필드 미감지
- 스케줄러: 미구현 (Mac Mini 도착 후)
