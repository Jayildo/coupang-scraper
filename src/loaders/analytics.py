"""analytics_daily 업로드.

CSV (BOM UTF-8) → analytics_daily 테이블로 UPSERT.
키: (date, sku_id, vendor_item_id)
"""
import csv
import logging
from datetime import datetime
from pathlib import Path

from loaders.base import (
    chunked, finish_run, get_supabase_client, latest_download, start_run,
)

log = logging.getLogger(__name__)

# CSV 한국어 헤더 → DB 컬럼명 매핑
COLUMN_MAP = {
    "날짜": "date",
    "Product ID": "product_id",
    "바코드": "barcode",
    "SKU ID": "sku_id",
    "SKU 명": "sku_name",
    "벤더아이템 ID": "vendor_item_id",
    "벤더아이템명": "vendor_item_name",
    "로켓프레시": "is_rocket_fresh",
    "상품카테고리": "category",
    "하위카테고리": "sub_category",
    "세부카테고리": "detail_category",
    "브랜드": "brand",
    "매출액(GMV)": "gmv",
    "판매수량(Units Sold)": "units_sold",
    "반품수량(Return Units)": "return_units",
    "매입원가(COGS)": "cogs",
    "AMV": "amv",
    "쿠폰 할인가(쿠팡 추가 할인가 제외)": "coupon_discount",
    "쿠팡 추가 할인가": "coupang_discount",
    "즉시 할인가": "instant_discount",
    "프로모션발생매출액(GMV)": "promo_gmv",
    "프로모션발생판매수량(Units Sold)": "promo_units_sold",
    "평균판매금액(ASP)": "asp",
    "주문건수": "order_count",
    "주문 고객 수": "unique_customers",
    "객단가": "customer_unit_price",
    "구매전환율": "conversion_rate",
    "PV": "pv",
    "정기배송 매출액(SnS GMV)": "sns_gmv",
    "정기배송 매입원가(SnS COGS)": "sns_cogs",
    "정기배송 비중(SnS %)": "sns_ratio",
    "정기배송 판매수량(SnS Units Sold)": "sns_units_sold",
    "정기배송 반품수량(Return Units)": "sns_return_units",
    "상품평 수": "review_count",
    "평균 상품 평점": "review_rating",
}

NUMERIC_COLS = {
    "gmv", "units_sold", "return_units", "cogs", "amv",
    "coupon_discount", "coupang_discount", "instant_discount",
    "promo_gmv", "promo_units_sold", "asp", "order_count",
    "unique_customers", "customer_unit_price", "conversion_rate", "pv",
    "sns_gmv", "sns_cogs", "sns_ratio", "sns_units_sold", "sns_return_units",
    "review_count", "review_rating",
}

BATCH_SIZE = 500  # supabase REST limit 우회용


def _parse_numeric(v: str):
    if v is None or v == "":
        return None
    try:
        # 쿠팡 CSV는 콤마 천단위 구분자 / 퍼센트 기호 포함 가능
        s = v.replace(",", "").replace("%", "").strip()
        if s == "" or s == "-":
            return None
        return float(s)
    except (ValueError, AttributeError):
        return None


def _parse_date(v: str) -> str | None:
    """YYYYMMDD → YYYY-MM-DD."""
    if not v or len(v) != 8:
        return None
    try:
        return datetime.strptime(v, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _parse_bool(v: str) -> bool | None:
    if v is None or v == "":
        return None
    return v.strip().upper() in ("YES", "Y", "TRUE", "1", "O", "예")


def _csv_to_rows(path: Path, run_id: str):
    """CSV 파싱 → analytics_daily row dict 리스트."""
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            row = {"scrape_run_id": run_id}
            for ko, en in COLUMN_MAP.items():
                v = raw.get(ko, "")
                if en == "date":
                    row[en] = _parse_date(v)
                elif en == "is_rocket_fresh":
                    row[en] = _parse_bool(v)
                elif en in NUMERIC_COLS:
                    row[en] = _parse_numeric(v)
                else:
                    row[en] = v.strip() if v else None

            # PK 검증 (date, sku_id, vendor_item_id 모두 있어야 UPSERT 가능)
            if not (row.get("date") and row.get("sku_id") and row.get("vendor_item_id")):
                log.warning(f"[ANALYTICS_LOAD] PK 누락 row 스킵: {raw.get('날짜')}/{raw.get('SKU ID')}")
                continue
            rows.append(row)
    return rows


def load(file_path: Path | None = None) -> dict:
    """analytics_daily 적재 진입점.

    file_path 없으면 가장 최근 analytics_premium_*.csv 자동 발견.
    반환: 통계 dict
    """
    if file_path is None:
        file_path = latest_download("analytics_premium_*.csv")
    if not file_path or not Path(file_path).exists():
        raise FileNotFoundError(f"analytics CSV 파일 없음: {file_path}")

    file_path = Path(file_path)
    log.info(f"[ANALYTICS_LOAD] 파일: {file_path}")

    client = get_supabase_client()
    run_id = start_run(client, "analytics", file_path)

    try:
        rows = _csv_to_rows(file_path, run_id)
        log.info(f"[ANALYTICS_LOAD] 파싱 완료: {len(rows)} rows")

        # UPSERT (배치)
        # supabase-py: table().upsert(rows, on_conflict='date,sku_id,vendor_item_id')
        upserted = 0
        for batch in chunked(rows, BATCH_SIZE):
            client.table("analytics_daily").upsert(
                batch,
                on_conflict="date,sku_id,vendor_item_id",
            ).execute()
            upserted += len(batch)
            log.info(f"[ANALYTICS_LOAD] upserted {upserted}/{len(rows)}")

        finish_run(
            client, run_id,
            status="success",
            rows_processed=len(rows),
            rows_inserted=upserted,  # UPSERT는 ins/upd 구분 불가 — 합쳐서 카운트
            metadata={"file": str(file_path), "batch_size": BATCH_SIZE},
        )
        return {"run_id": run_id, "rows": len(rows), "upserted": upserted}

    except Exception as e:
        log.error(f"[ANALYTICS_LOAD] 실패: {e}", exc_info=True)
        finish_run(client, run_id, status="failed", error_message=str(e))
        raise
