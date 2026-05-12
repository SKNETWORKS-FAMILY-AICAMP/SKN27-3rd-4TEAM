-- =============================================
-- [미사용 — 향후 참고용]
-- market_price_service.py 활성화 시 실행 필요한 마이그레이션입니다.
-- 현재 금액 기반 판단은 딥러닝 파트 담당이므로 실행하지 않아도 됩니다.
-- 실행 명령: docker exec -i jeonse_db psql -U postgres -d jeonse_risk < database/migration_market.sql
-- =============================================
-- 시세 비교 기능을 위한 스키마 확장
-- =============================================

-- 1. sale_transactions — dong_name 추가
ALTER TABLE sale_transactions
    ADD COLUMN IF NOT EXISTS dong_name    VARCHAR(50),
    ADD COLUMN IF NOT EXISTS property_name VARCHAR(100);

-- 기존 데이터 dong_name 채우기 (sigungu = "서울특별시 종로구 내수동" → "내수동")
UPDATE sale_transactions
SET dong_name = regexp_replace(
    regexp_replace(sigungu, '^.*[구군]\s+', ''),
    '\s+.*$', ''
)
WHERE dong_name IS NULL AND sigungu IS NOT NULL;

-- 2. sale_transactions 인덱스
CREATE INDEX IF NOT EXISTS idx_sale_dong         ON sale_transactions(dong_name);
CREATE INDEX IF NOT EXISTS idx_sale_housing_dong ON sale_transactions(housing_type, dong_name);
CREATE INDEX IF NOT EXISTS idx_sale_ym           ON sale_transactions(deal_year_month);
CREATE INDEX IF NOT EXISTS idx_sale_area         ON sale_transactions(exclusive_area);

-- 3. jeonse_transactions 인덱스 (이미 dong_name 컬럼 있음)
CREATE INDEX IF NOT EXISTS idx_jeonse_housing_dong ON jeonse_transactions(housing_type, dong_name);
CREATE INDEX IF NOT EXISTS idx_jeonse_area         ON jeonse_transactions(exclusive_area_m2);
CREATE INDEX IF NOT EXISTS idx_jeonse_deposit      ON jeonse_transactions(deposit_amount);
CREATE INDEX IF NOT EXISTS idx_jeonse_monthly_rent ON jeonse_transactions(monthly_rent);
