-- Task 4: 프리미엄 데이터 2.0 (일간 종합 성과 지표)
-- 패턴: 시계열 팩트 테이블, UPSERT (D-1 확정 후 불변)
-- 자연 키: (date, sku_id, vendor_item_id) — 같은 SKU여도 vendor_item이 다를 수 있음

CREATE TABLE IF NOT EXISTS analytics_daily (
  date              DATE        NOT NULL,
  sku_id            TEXT        NOT NULL,
  vendor_item_id    TEXT        NOT NULL,
  -- 식별자
  product_id        TEXT,
  barcode           TEXT,
  sku_name          TEXT,
  vendor_item_name  TEXT,
  is_rocket_fresh   BOOLEAN,
  -- 카테고리/브랜드
  category          TEXT,
  sub_category      TEXT,
  detail_category   TEXT,
  brand             TEXT,
  -- 매출/판매
  gmv               NUMERIC,                  -- 매출액(GMV)
  units_sold        NUMERIC,                  -- 판매수량
  return_units      NUMERIC,                  -- 반품수량
  cogs              NUMERIC,                  -- 매입원가
  amv               NUMERIC,
  -- 할인
  coupon_discount   NUMERIC,                  -- 쿠폰 할인가
  coupang_discount  NUMERIC,                  -- 쿠팡 추가 할인가
  instant_discount  NUMERIC,                  -- 즉시 할인가
  -- 프로모션
  promo_gmv         NUMERIC,
  promo_units_sold  NUMERIC,
  -- 가격/주문
  asp               NUMERIC,                  -- 평균판매금액
  order_count       NUMERIC,
  unique_customers  NUMERIC,
  customer_unit_price NUMERIC,                -- 객단가
  conversion_rate   NUMERIC,                  -- 구매전환율
  pv                NUMERIC,
  -- 정기배송 (SnS)
  sns_gmv           NUMERIC,
  sns_cogs          NUMERIC,
  sns_ratio         NUMERIC,
  sns_units_sold    NUMERIC,
  sns_return_units  NUMERIC,
  -- 리뷰
  review_count      NUMERIC,
  review_rating     NUMERIC,
  -- 메타
  scrape_run_id     UUID        NOT NULL,
  scraped_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (date, sku_id, vendor_item_id)
);

CREATE INDEX IF NOT EXISTS idx_analytics_daily_date ON analytics_daily (date DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_daily_sku  ON analytics_daily (sku_id);
CREATE INDEX IF NOT EXISTS idx_analytics_daily_brand ON analytics_daily (brand);

COMMENT ON TABLE analytics_daily IS '일간 종합 성과 지표 (D-1 확정 후 불변, UPSERT)';
