-- =============================================
-- Market-price support migration.
-- Run:
--   Get-Content database/migration_market.sql | docker exec -i jeonse_db psql -U postgres -d jeonse_risk
-- =============================================

ALTER TABLE sale_transactions
    ADD COLUMN IF NOT EXISTS dong_name VARCHAR(50),
    ADD COLUMN IF NOT EXISTS property_name VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_sale_dong ON sale_transactions(dong_name);
CREATE INDEX IF NOT EXISTS idx_sale_housing_dong ON sale_transactions(housing_type, dong_name);
CREATE INDEX IF NOT EXISTS idx_sale_ym ON sale_transactions(deal_year_month);
CREATE INDEX IF NOT EXISTS idx_sale_area ON sale_transactions(exclusive_area);

CREATE INDEX IF NOT EXISTS idx_jeonse_housing_dong ON jeonse_transactions(housing_type, dong_name);
CREATE INDEX IF NOT EXISTS idx_jeonse_area ON jeonse_transactions(exclusive_area_m2);
CREATE INDEX IF NOT EXISTS idx_jeonse_deposit ON jeonse_transactions(deposit_amount);
CREATE INDEX IF NOT EXISTS idx_jeonse_monthly_rent ON jeonse_transactions(monthly_rent);
