-- Row Level Security: default deny, service_role만 쓰기 가능
-- 스크래퍼는 service_role_key 사용 → RLS 자동 우회
-- 클라이언트(anon key)는 읽기만 허용 (대시보드용)

ALTER TABLE analytics_daily       ENABLE ROW LEVEL SECURITY;
ALTER TABLE sku_info              ENABLE ROW LEVEL SECURITY;
ALTER TABLE po_sku_current        ENABLE ROW LEVEL SECURITY;
ALTER TABLE po_sku_history        ENABLE ROW LEVEL SECURITY;
ALTER TABLE milkrun_fee_versions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_runs           ENABLE ROW LEVEL SECURITY;

-- 각 테이블에 SELECT 정책 (anon + authenticated)
-- DROP IF EXISTS → CREATE 패턴 (CREATE POLICY IF NOT EXISTS는 미지원)
DO $$
DECLARE
  t TEXT;
  tables TEXT[] := ARRAY[
    'analytics_daily',
    'sku_info',
    'po_sku_current',
    'po_sku_history',
    'milkrun_fee_versions',
    'scrape_runs'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_read_anon ON %I;', t, t);
    EXECUTE format('DROP POLICY IF EXISTS %I_read_auth ON %I;', t, t);
    EXECUTE format(
      'CREATE POLICY %I_read_anon ON %I FOR SELECT TO anon USING (true);',
      t, t
    );
    EXECUTE format(
      'CREATE POLICY %I_read_auth ON %I FOR SELECT TO authenticated USING (true);',
      t, t
    );
  END LOOP;
END $$;

-- service_role 은 RLS 자동 우회 (별도 정책 불필요)
