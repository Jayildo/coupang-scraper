-- 모든 스크래핑 실행을 추적하는 메타 테이블
-- 모든 데이터 테이블이 scrape_run_id로 이 테이블을 참조 (FK는 강제하지 않음 — 빠른 INSERT)

CREATE TABLE IF NOT EXISTS scrape_runs (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  task_name        TEXT        NOT NULL,    -- 'analytics' | 'sku_info' | 'po_sku' | 'milkrun'
  source_file      TEXT,                    -- 다운로드 파일 경로
  started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at      TIMESTAMPTZ,
  status           TEXT        NOT NULL,    -- 'running' | 'success' | 'failed'
  rows_processed   INTEGER,
  rows_inserted    INTEGER,
  rows_updated     INTEGER,
  rows_unchanged   INTEGER,
  rows_removed     INTEGER,
  error_message    TEXT,
  metadata         JSONB
);

CREATE INDEX IF NOT EXISTS idx_scrape_runs_task_time ON scrape_runs (task_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_status    ON scrape_runs (status);

COMMENT ON TABLE scrape_runs IS '모든 스크래핑/업로드 실행 추적 (감사 로그)';
