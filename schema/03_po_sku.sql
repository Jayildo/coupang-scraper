-- Task 3: 발주 SKU 리스트 (트랜잭션 + 상태 변화)
-- 패턴: 현재 상태 미러 + append-only 이력
-- 자연 키: (po_id, sku_id) — 한 발주에 여러 SKU 가능

-- ────────────────────────────────────────────────────────────
-- 현재 상태 (쿠팡 화면과 미러링)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS po_sku_current (
  po_id              TEXT NOT NULL,        -- 발주번호
  sku_id             TEXT NOT NULL,        -- SKU ID
  -- 발주 정보
  po_type            TEXT,                 -- 발주유형
  status             TEXT,                 -- 발주현황
  sku_name           TEXT,                 -- SKU 이름
  barcode            TEXT,                 -- SKU Barcode
  warehouse          TEXT,                 -- 물류센터
  expected_at        DATE,                 -- 입고예정일
  ordered_at         DATE,                 -- 발주일
  -- 수량
  qty_ordered        NUMERIC,              -- 발주수량
  qty_confirmed      NUMERIC,              -- 확정수량
  qty_received       NUMERIC,              -- 입고수량
  -- 매입/면세
  purchase_type      TEXT,                 -- 매입유형
  tax_free           TEXT,                 -- 면세여부
  production_year    TEXT,                 -- 생산연도
  manufacture_date   TEXT,                 -- 제조일자
  expiry_date        TEXT,                 -- 유통(소비)기한
  -- 금액
  purchase_price     NUMERIC,              -- 매입가
  supply_price       NUMERIC,              -- 공급가
  vat                NUMERIC,              -- 부가세
  total_amount       NUMERIC,              -- 총발주 매입금
  received_amount    NUMERIC,              -- 입고금액
  xdock              TEXT,                 -- Xdock
  -- 스키마 진화 대비
  raw_data           JSONB,
  -- 변경 추적
  content_hash       TEXT NOT NULL,
  first_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_changed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_active          BOOLEAN     NOT NULL DEFAULT true,
  -- 메타
  scrape_run_id      UUID NOT NULL,
  scraped_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (po_id, sku_id)
);

CREATE INDEX IF NOT EXISTS idx_po_sku_current_active   ON po_sku_current (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_po_sku_current_status   ON po_sku_current (status);
CREATE INDEX IF NOT EXISTS idx_po_sku_current_expected ON po_sku_current (expected_at);
CREATE INDEX IF NOT EXISTS idx_po_sku_current_changed  ON po_sku_current (last_changed_at DESC);

COMMENT ON TABLE po_sku_current IS '발주 SKU 현재 상태 (쿠팡 화면 미러링, hash 변경 시에만 last_changed_at 갱신)';

-- ────────────────────────────────────────────────────────────
-- 변경 이력 (append-only, hash가 바뀐 시점만 INSERT)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS po_sku_history (
  id                 BIGSERIAL PRIMARY KEY,
  po_id              TEXT NOT NULL,
  sku_id             TEXT NOT NULL,
  -- 동일한 비즈니스 컬럼 (스냅샷)
  po_type            TEXT,
  status             TEXT,
  sku_name           TEXT,
  barcode            TEXT,
  warehouse          TEXT,
  expected_at        DATE,
  ordered_at         DATE,
  qty_ordered        NUMERIC,
  qty_confirmed      NUMERIC,
  qty_received       NUMERIC,
  purchase_type      TEXT,
  tax_free           TEXT,
  production_year    TEXT,
  manufacture_date   TEXT,
  expiry_date        TEXT,
  purchase_price     NUMERIC,
  supply_price       NUMERIC,
  vat                NUMERIC,
  total_amount       NUMERIC,
  received_amount    NUMERIC,
  xdock              TEXT,
  raw_data           JSONB,
  -- 이력 메타
  change_type        TEXT NOT NULL,        -- 'CREATED' | 'UPDATED' | 'REMOVED'
  content_hash       TEXT NOT NULL,
  observed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  scrape_run_id      UUID NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_po_sku_history_pk_time ON po_sku_history (po_id, sku_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_po_sku_history_run     ON po_sku_history (scrape_run_id);
CREATE INDEX IF NOT EXISTS idx_po_sku_history_change  ON po_sku_history (change_type, observed_at DESC);

COMMENT ON TABLE po_sku_history IS '발주 SKU 변경 이력 (append-only, content_hash가 변할 때 또는 REMOVED 시 INSERT)';
