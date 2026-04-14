-- Task 2: SKU 정보 관리 (마스터 데이터)
-- 패턴: PK = sku_id, content_hash로 변경 감지, 사라진 SKU는 is_active=false
-- 주의: 실제 컬럼은 첫 업로드 시 xlsx 분석 후 추가/조정 (현재는 골격만)

CREATE TABLE IF NOT EXISTS sku_info (
  sku_id            TEXT        PRIMARY KEY,
  product_id        TEXT,
  sku_name          TEXT,
  brand             TEXT,
  status            TEXT,
  -- 기타 마스터 속성 (xlsx 분석 후 추가)
  raw_data          JSONB,                    -- 모든 컬럼을 jsonb로도 보존 (스키마 진화 대비)
  -- 변경 추적
  content_hash      TEXT        NOT NULL,
  first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_changed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_active         BOOLEAN     NOT NULL DEFAULT true,
  -- 메타
  scrape_run_id     UUID        NOT NULL,
  scraped_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sku_info_active ON sku_info (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_sku_info_brand  ON sku_info (brand);
CREATE INDEX IF NOT EXISTS idx_sku_info_changed ON sku_info (last_changed_at DESC);

COMMENT ON TABLE sku_info IS 'SKU 마스터 (UPSERT + content_hash 변경 감지 + 소프트 삭제)';
