-- 대시보드용 집계 VIEW (클라이언트가 수만 row 대신 집계 결과만 받음)

-- 1. analytics 일자별 집계
CREATE OR REPLACE VIEW v_analytics_daily_summary AS
SELECT
  date,
  COUNT(*)              AS row_count,
  SUM(gmv)              AS total_gmv,
  SUM(units_sold)       AS total_units_sold,
  SUM(return_units)     AS total_return_units,
  SUM(order_count)      AS total_order_count,
  SUM(cogs)             AS total_cogs,
  COUNT(DISTINCT sku_id) AS unique_skus,
  COUNT(DISTINCT brand)  AS unique_brands
FROM analytics_daily
GROUP BY date
ORDER BY date;

-- 2. po_sku 상태 분포
CREATE OR REPLACE VIEW v_po_sku_status_summary AS
SELECT
  status,
  COUNT(*)                  AS count,
  SUM(qty_ordered)          AS total_qty_ordered,
  SUM(qty_received)         AS total_qty_received,
  SUM(total_amount)         AS total_amount
FROM po_sku_current
WHERE is_active = true
GROUP BY status
ORDER BY count DESC;

-- 3. po_sku_history change_type 분포
CREATE OR REPLACE VIEW v_po_sku_history_summary AS
SELECT
  change_type,
  COUNT(*)                  AS count,
  MAX(observed_at)          AS latest_observed
FROM po_sku_history
GROUP BY change_type
ORDER BY count DESC;

-- VIEW는 base table의 RLS를 따르므로 별도 정책 불필요
