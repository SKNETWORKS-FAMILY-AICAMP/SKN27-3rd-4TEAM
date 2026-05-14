-- =============================================
-- diagnosis_logs columns for structured diagnosis results.
-- Run:
--   Get-Content database/migration_diagnosis_logs.sql | docker exec -i jeonse_db psql -U postgres -d jeonse_risk
-- =============================================

ALTER TABLE diagnosis_logs
    ADD COLUMN IF NOT EXISTS estimated_sale_price INTEGER,
    ADD COLUMN IF NOT EXISTS jeonse_ratio NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS contract_info JSONB;

-- Older local DBs may already have jeonse_ratio as NUMERIC(4,2).
-- That can reject normal ratios such as 78.80 or values above 100.
ALTER TABLE diagnosis_logs
    ALTER COLUMN jeonse_ratio TYPE NUMERIC(6,2)
    USING jeonse_ratio::NUMERIC(6,2);

-- Risk scores can be exactly 100.00, which does not fit in NUMERIC(4,2).
ALTER TABLE diagnosis_logs
    ALTER COLUMN risk_score TYPE NUMERIC(6,2)
    USING risk_score::NUMERIC(6,2);

CREATE INDEX IF NOT EXISTS idx_diag_session ON diagnosis_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_diag_created ON diagnosis_logs(created_at DESC);
