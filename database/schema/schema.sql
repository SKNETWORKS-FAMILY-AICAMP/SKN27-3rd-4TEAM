-- 전세/월세 실거래 테이블
CREATE TABLE IF NOT EXISTS jeonse_transactions (
    id BIGSERIAL PRIMARY KEY,
    source_file VARCHAR(255),
    source_row_no INTEGER,

    sido VARCHAR(50),
    sigungu VARCHAR(100),
    eup_myeon_dong VARCHAR(100),
    legal_dong_code VARCHAR(20),
    jibun VARCHAR(50),
    road_name VARCHAR(150),
    road_name_code VARCHAR(30),

    property_type VARCHAR(50),
    building_name VARCHAR(200),
    exclusive_area_m2 NUMERIC(10, 4),
    floor INTEGER,
    built_year INTEGER,

    contract_year INTEGER NOT NULL,
    contract_month INTEGER NOT NULL,
    contract_day INTEGER,
    contract_ym INTEGER GENERATED ALWAYS AS (contract_year * 100 + contract_month) STORED,

    deposit_amount_manwon BIGINT NOT NULL,
    monthly_rent_manwon BIGINT DEFAULT 0,
    contract_type VARCHAR(30),
    renewal_request_right_used BOOLEAN,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_jeonse_contract_month CHECK (contract_month BETWEEN 1 AND 12),
    CONSTRAINT chk_jeonse_contract_day CHECK (contract_day IS NULL OR contract_day BETWEEN 1 AND 31),
    CONSTRAINT chk_jeonse_deposit_non_negative CHECK (deposit_amount_manwon >= 0),
    CONSTRAINT chk_jeonse_monthly_rent_non_negative CHECK (monthly_rent_manwon IS NULL OR monthly_rent_manwon >= 0),
    CONSTRAINT uq_jeonse_source_row UNIQUE (source_file, source_row_no)
);

-- 부동산 매매 실거래 테이블
CREATE TABLE IF NOT EXISTS property_trade_transactions (
    id BIGSERIAL PRIMARY KEY,
    source_file VARCHAR(255),
    source_row_no INTEGER,

    sido VARCHAR(50),
    sigungu VARCHAR(100),
    eup_myeon_dong VARCHAR(100),
    legal_dong_code VARCHAR(20),
    jibun VARCHAR(50),
    road_name VARCHAR(150),
    road_name_code VARCHAR(30),

    property_type VARCHAR(50),
    building_name VARCHAR(200),
    exclusive_area_m2 NUMERIC(10, 4),
    floor INTEGER,
    built_year INTEGER,

    contract_year INTEGER NOT NULL,
    contract_month INTEGER NOT NULL,
    contract_day INTEGER,
    contract_ym INTEGER GENERATED ALWAYS AS (contract_year * 100 + contract_month) STORED,

    trade_amount_manwon BIGINT NOT NULL,
    buyer VARCHAR(100),
    seller VARCHAR(100),
    dealing_type VARCHAR(50),
    broker_location VARCHAR(200),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_property_trade_contract_month CHECK (contract_month BETWEEN 1 AND 12),
    CONSTRAINT chk_property_trade_contract_day CHECK (contract_day IS NULL OR contract_day BETWEEN 1 AND 31),
    CONSTRAINT chk_property_trade_amount_non_negative CHECK (trade_amount_manwon >= 0),
    CONSTRAINT uq_property_trade_source_row UNIQUE (source_file, source_row_no)
);

-- 전세 데이터 검색용 인덱스
CREATE INDEX IF NOT EXISTS idx_jeonse_region_contract_ym
    ON jeonse_transactions (sido, sigungu, eup_myeon_dong, contract_ym);

CREATE INDEX IF NOT EXISTS idx_jeonse_building_area
    ON jeonse_transactions (building_name, exclusive_area_m2);

CREATE INDEX IF NOT EXISTS idx_jeonse_deposit
    ON jeonse_transactions (deposit_amount_manwon);

-- 매매 데이터 검색용 인덱스
CREATE INDEX IF NOT EXISTS idx_property_trade_region_contract_ym
    ON property_trade_transactions (sido, sigungu, eup_myeon_dong, contract_ym);

CREATE INDEX IF NOT EXISTS idx_property_trade_building_area
    ON property_trade_transactions (building_name, exclusive_area_m2);

CREATE INDEX IF NOT EXISTS idx_property_trade_amount
    ON property_trade_transactions (trade_amount_manwon);

-- DB에 저장되는 테이블/컬럼 설명
COMMENT ON TABLE jeonse_transactions IS '전세/월세 실거래 데이터';
COMMENT ON COLUMN jeonse_transactions.deposit_amount_manwon IS '보증금. 원본 실거래 CSV 기준 만원 단위';
COMMENT ON COLUMN jeonse_transactions.monthly_rent_manwon IS '월세. 원본 실거래 CSV 기준 만원 단위';

COMMENT ON TABLE property_trade_transactions IS '부동산 매매 실거래 데이터';
COMMENT ON COLUMN property_trade_transactions.trade_amount_manwon IS '매매 거래금액. 원본 실거래 CSV 기준 만원 단위';

-- 전세 보증금과 최근 매매가를 비교하는 전세가율 분석 뷰
CREATE OR REPLACE VIEW jeonse_trade_risk_view AS
SELECT
    jt.id AS jeonse_id,
    pt.id AS latest_trade_id,
    jt.sido,
    jt.sigungu,
    jt.eup_myeon_dong,
    jt.building_name,
    jt.exclusive_area_m2,
    jt.contract_ym AS jeonse_contract_ym,
    jt.deposit_amount_manwon,
    pt.contract_ym AS latest_trade_contract_ym,
    pt.trade_amount_manwon,
    ROUND(
        jt.deposit_amount_manwon::NUMERIC / NULLIF(pt.trade_amount_manwon, 0),
        4
    ) AS jeonse_to_trade_ratio,
    CASE
        WHEN pt.trade_amount_manwon IS NULL THEN 'NO_TRADE_DATA'
        WHEN jt.deposit_amount_manwon::NUMERIC / NULLIF(pt.trade_amount_manwon, 0) >= 0.90 THEN 'HIGH'
        WHEN jt.deposit_amount_manwon::NUMERIC / NULLIF(pt.trade_amount_manwon, 0) >= 0.80 THEN 'WATCH'
        ELSE 'NORMAL'
    END AS risk_level
FROM jeonse_transactions jt
LEFT JOIN LATERAL (
    SELECT pt_inner.*
    FROM property_trade_transactions pt_inner
    WHERE pt_inner.sido IS NOT DISTINCT FROM jt.sido
      AND pt_inner.sigungu IS NOT DISTINCT FROM jt.sigungu
      AND pt_inner.eup_myeon_dong IS NOT DISTINCT FROM jt.eup_myeon_dong
      AND pt_inner.building_name IS NOT DISTINCT FROM jt.building_name
      AND pt_inner.exclusive_area_m2 IS NOT DISTINCT FROM jt.exclusive_area_m2
      AND pt_inner.contract_ym <= jt.contract_ym
    ORDER BY pt_inner.contract_ym DESC, pt_inner.contract_day DESC NULLS LAST, pt_inner.id DESC
    LIMIT 1
) pt ON TRUE;

COMMENT ON VIEW jeonse_trade_risk_view IS '전세 보증금과 최근 매매가를 비교한 전세가율 분석 뷰';
