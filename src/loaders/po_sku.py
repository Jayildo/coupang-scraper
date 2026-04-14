"""po_sku_current + po_sku_history 업로드.

CSV (BOM UTF-8) → 현재 상태 미러 + append-only 변경 이력.

알고리즘:
  1. CSV 파싱 → 23컬럼 + raw_data + content_hash
  2. 새 PK 집합 계산
  3. 기존 active row를 SELECT → (po_id, sku_id, content_hash) 맵 구성
  4. 분류:
     - 신규: po_sku_current INSERT + history(CREATED)
     - 변경: po_sku_current UPDATE (last_changed_at=now) + history(UPDATED)
     - 동일: po_sku_current.last_seen_at만 갱신
     - 사라짐: po_sku_current.is_active=false + history(REMOVED)
  5. scrape_runs 통계 기록
"""
import csv
import json
import logging
from datetime import datetime
from pathlib import Path

from loaders.base import (
    chunked, finish_run, get_supabase_client, latest_download,
    now_iso, stable_hash, start_run,
)

log = logging.getLogger(__name__)

# CSV 한국어 헤더 → DB 컬럼명
COLUMN_MAP = {
    "발주번호": "po_id",
    "발주유형": "po_type",
    "발주현황": "status",
    "SKU ID": "sku_id",
    "SKU 이름": "sku_name",
    "SKU Barcode": "barcode",
    "물류센터": "warehouse",
    "입고예정일": "expected_at",
    "발주일": "ordered_at",
    "발주수량": "qty_ordered",
    "확정수량": "qty_confirmed",
    "입고수량": "qty_received",
    "매입유형": "purchase_type",
    "면세여부": "tax_free",
    "생산연도": "production_year",
    "제조일자": "manufacture_date",
    "유통(소비)기한": "expiry_date",
    "매입가": "purchase_price",
    "공급가": "supply_price",
    "부가세": "vat",
    "총발주 매입금": "total_amount",
    "입고금액": "received_amount",
    "Xdock": "xdock",
}

NUMERIC_COLS = {
    "qty_ordered", "qty_confirmed", "qty_received",
    "purchase_price", "supply_price", "vat",
    "total_amount", "received_amount",
}
DATE_COLS = {"expected_at", "ordered_at"}

# content_hash에 포함할 컬럼 (메타·변경 추적 컬럼 제외)
HASH_COLS = [
    "po_type", "status", "sku_name", "barcode", "warehouse",
    "expected_at", "ordered_at",
    "qty_ordered", "qty_confirmed", "qty_received",
    "purchase_type", "tax_free", "production_year",
    "manufacture_date", "expiry_date",
    "purchase_price", "supply_price", "vat",
    "total_amount", "received_amount", "xdock",
]

BATCH_SIZE = 500


def _parse_numeric(v):
    if v is None or v == "":
        return None
    try:
        s = str(v).replace(",", "").replace("%", "").strip()
        if s == "" or s == "-":
            return None
        return float(s)
    except (ValueError, AttributeError):
        return None


def _parse_date(v):
    if not v:
        return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _csv_to_rows(path: Path):
    """CSV 파싱 → row dict 리스트 (PK + 비즈니스 컬럼 + content_hash + raw_data)."""
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            row = {}
            raw_clean = {}
            for ko, en in COLUMN_MAP.items():
                v = raw.get(ko, "")
                raw_clean[ko] = v
                if en in DATE_COLS:
                    row[en] = _parse_date(v)
                elif en in NUMERIC_COLS:
                    row[en] = _parse_numeric(v)
                else:
                    row[en] = v.strip() if v else None

            if not (row.get("po_id") and row.get("sku_id")):
                log.warning(f"[PO_SKU_LOAD] PK 누락 row 스킵")
                continue

            row["raw_data"] = raw_clean
            row["content_hash"] = stable_hash({k: row.get(k) for k in HASH_COLS})
            rows.append(row)
    return rows


def _fetch_existing_active(client) -> dict:
    """기존 active row 전체 SELECT (po_id, sku_id) → content_hash 맵.

    REST는 페이지네이션 필요 (기본 1000). PostgREST의 range 헤더 사용 위해
    .range(start, end)로 청크 페치.
    """
    existing = {}
    page_size = 1000
    offset = 0
    while True:
        resp = client.table("po_sku_current") \
            .select("po_id,sku_id,content_hash") \
            .eq("is_active", True) \
            .range(offset, offset + page_size - 1) \
            .execute()
        data = resp.data or []
        for r in data:
            existing[(r["po_id"], r["sku_id"])] = r["content_hash"]
        if len(data) < page_size:
            break
        offset += page_size
    return existing


def load(file_path: Path | None = None) -> dict:
    if file_path is None:
        file_path = latest_download("order_sku_*.csv")
    if not file_path or not Path(file_path).exists():
        raise FileNotFoundError(f"po_sku CSV 파일 없음: {file_path}")

    file_path = Path(file_path)
    log.info(f"[PO_SKU_LOAD] 파일: {file_path}")

    client = get_supabase_client()
    run_id = start_run(client, "po_sku", file_path)

    try:
        new_rows = _csv_to_rows(file_path)
        log.info(f"[PO_SKU_LOAD] 파싱 완료: {len(new_rows)} rows")

        existing = _fetch_existing_active(client)
        log.info(f"[PO_SKU_LOAD] 기존 active: {len(existing)} rows")

        new_pks = {(r["po_id"], r["sku_id"]) for r in new_rows}

        # 분류
        to_insert = []   # 신규 (first_seen_at + last_changed_at)
        to_change = []   # hash 변경 (last_changed_at만)
        to_same_pks = [] # 동일 (last_seen_at만 touch)
        history_inserts = []  # CREATED + UPDATED + REMOVED
        n_new = n_changed = n_same = 0

        now = now_iso()
        for row in new_rows:
            pk = (row["po_id"], row["sku_id"])
            old_hash = existing.get(pk)
            payload = {
                **row,
                "scrape_run_id": run_id,
                "scraped_at": now,
                "last_seen_at": now,
                "is_active": True,
            }
            if old_hash is None:
                # 신규
                payload["first_seen_at"] = now
                payload["last_changed_at"] = now
                to_insert.append(payload)
                n_new += 1
                history_inserts.append({
                    **{k: row.get(k) for k in HASH_COLS},
                    "po_id": row["po_id"],
                    "sku_id": row["sku_id"],
                    "raw_data": row["raw_data"],
                    "content_hash": row["content_hash"],
                    "change_type": "CREATED",
                    "observed_at": now,
                    "scrape_run_id": run_id,
                })
            elif old_hash != row["content_hash"]:
                # 변경
                payload["last_changed_at"] = now
                to_change.append(payload)
                n_changed += 1
                history_inserts.append({
                    **{k: row.get(k) for k in HASH_COLS},
                    "po_id": row["po_id"],
                    "sku_id": row["sku_id"],
                    "raw_data": row["raw_data"],
                    "content_hash": row["content_hash"],
                    "change_type": "UPDATED",
                    "observed_at": now,
                    "scrape_run_id": run_id,
                })
            else:
                # 동일 - last_seen_at만 touch (별도 UPDATE)
                to_same_pks.append(pk)
                n_same += 1

        # 사라진 PK 처리 (소프트 삭제)
        removed_pks = set(existing.keys()) - new_pks
        n_removed = len(removed_pks)
        if removed_pks:
            log.info(f"[PO_SKU_LOAD] 사라진 row {n_removed}건 → is_active=false")
            # is_active=false로 일괄 update
            # PostgREST는 in.() 필터를 PK 단일 컬럼에만 효율적 적용 가능
            # 복합 PK는 반복 호출 또는 RPC 필요. 여기선 청크별 OR 조건 사용.
            for chunk in chunked(list(removed_pks), 200):
                # composite PK update: SELECT → UPDATE 1건씩 비효율
                # 대안: 전체 row를 다시 가져와 upsert (last_seen_at 미갱신, is_active=false)
                # 단순화: 각 PK당 1회 update
                for po_id, sku_id in chunk:
                    client.table("po_sku_current") \
                        .update({"is_active": False, "last_changed_at": now}) \
                        .eq("po_id", po_id).eq("sku_id", sku_id) \
                        .execute()
                    history_inserts.append({
                        "po_id": po_id,
                        "sku_id": sku_id,
                        "change_type": "REMOVED",
                        "content_hash": "",
                        "observed_at": now,
                        "scrape_run_id": run_id,
                    })

        # current upsert: new/changed는 별도 배치 (컬럼 shape 달라서 NULL 오염 방지)
        for label, payloads in (("new", to_insert), ("changed", to_change)):
            upserted = 0
            for batch in chunked(payloads, BATCH_SIZE):
                client.table("po_sku_current").upsert(
                    batch,
                    on_conflict="po_id,sku_id",
                ).execute()
                upserted += len(batch)
                log.info(f"[PO_SKU_LOAD] {label} upserted {upserted}/{len(payloads)}")

        # 동일 row: last_seen_at만 touch (composite PK → 개별 UPDATE)
        for po_id, sku_id in to_same_pks:
            client.table("po_sku_current") \
                .update({"last_seen_at": now, "scrape_run_id": run_id}) \
                .eq("po_id", po_id).eq("sku_id", sku_id) \
                .execute()
        if to_same_pks:
            log.info(f"[PO_SKU_LOAD] same touched {len(to_same_pks)}")

        # history append (변경/신규/삭제 모두)
        hist_inserted = 0
        for batch in chunked(history_inserts, BATCH_SIZE):
            client.table("po_sku_history").insert(batch).execute()
            hist_inserted += len(batch)
            log.info(f"[PO_SKU_LOAD] history inserted {hist_inserted}/{len(history_inserts)}")

        finish_run(
            client, run_id,
            status="success",
            rows_processed=len(new_rows),
            rows_inserted=n_new,
            rows_updated=n_changed,
            rows_unchanged=n_same,
            rows_removed=n_removed,
            metadata={"file": str(file_path), "history_inserted": hist_inserted},
        )
        return {
            "run_id": run_id,
            "rows": len(new_rows),
            "new": n_new,
            "changed": n_changed,
            "unchanged": n_same,
            "removed": n_removed,
            "history": hist_inserted,
        }

    except Exception as e:
        log.error(f"[PO_SKU_LOAD] 실패: {e}", exc_info=True)
        finish_run(client, run_id, status="failed", error_message=str(e))
        raise
