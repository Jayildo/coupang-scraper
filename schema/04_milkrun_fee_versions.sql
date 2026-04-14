-- Task 1: 밀크런 이용 요금 (참조 문서, 거의 변경 없음)
-- 패턴: content_hash 기반 버전 관리, 같은 내용이면 last_seen만 갱신

CREATE TABLE IF NOT EXISTS milkrun_fee_versions (
  id            BIGSERIAL   PRIMARY KEY,
  content       TEXT        NOT NULL,
  content_hash  TEXT        NOT NULL UNIQUE,
  char_count    INTEGER     NOT NULL,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  scrape_run_id UUID        NOT NULL,
  scraped_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_milkrun_versions_seen ON milkrun_fee_versions (first_seen_at DESC);

COMMENT ON TABLE milkrun_fee_versions IS '밀크런 요금 안내 문서 버전 (내용 변경 시에만 새 row INSERT)';
