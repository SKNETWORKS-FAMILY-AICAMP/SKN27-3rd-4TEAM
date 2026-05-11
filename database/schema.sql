-- =============================================
-- 전세계약 위험 진단 에이전트 - PostgreSQL 스키마
-- =============================================

-- pgvector 익스텐션 활성화 (벡터 유사도 검색용)
-- ChromaDB 없이 PostgreSQL 하나로 벡터 DB 역할까지 담당
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. 전세 실거래가 (RAG 검색 + 전세가율 계산용)
CREATE TABLE jeonse_transactions (
    id                  SERIAL PRIMARY KEY,
    housing_type        VARCHAR(20),            -- 연립다세대 / 오피스텔
    property_name       VARCHAR(100),           -- 단지명
    dong_name           VARCHAR(50),            -- 동 이름
    jibun               VARCHAR(50),            -- 지번
    exclusive_area_m2   NUMERIC(8,2),           -- 전용면적(㎡)
    deposit_amount      INTEGER,                -- 보증금(만원)
    monthly_rent        INTEGER DEFAULT 0,      -- 월세(만원), 순전세=0
    floor               INTEGER,                -- 층
    build_year          INTEGER,                -- 건축년도
    contract_type       VARCHAR(20),            -- 신규 / 갱신
    contract_term       VARCHAR(30),            -- 계약기간 (예: 25.03~27.03)
    contract_date       DATE,                   -- 계약일
    created_at          TIMESTAMP DEFAULT NOW(),
    -- 중복 방지: 동일 계약 식별 기준
    UNIQUE (housing_type, dong_name, jibun, exclusive_area_m2, deposit_amount, contract_date, floor)
);

-- 2. 매매 실거래가 (전세가율 계산용)
CREATE TABLE sale_transactions (
    id                  SERIAL PRIMARY KEY,
    housing_type        VARCHAR(20),            -- 연립다세대 / 오피스텔
    sigungu             VARCHAR(50),
    bldg_nm             VARCHAR(100),
    exclusive_area      NUMERIC(8,2),
    deal_amount         INTEGER,                -- 매매가(만원)
    floor               INTEGER,
    build_year          INTEGER,
    deal_year_month     INTEGER,                -- YYYYMM
    deal_type           VARCHAR(20),            -- 중개거래 / 직거래
    created_at          TIMESTAMP DEFAULT NOW(),
    -- 중복 방지
    UNIQUE (housing_type, bldg_nm, exclusive_area, deal_amount, deal_year_month, floor)
);

-- 3. 전세가율 (매매가 대비 전세보증금 비율)
-- 위험 기준: 80% 초과 = 위험, 70~80% = 주의
CREATE TABLE price_ratio (
    id                  SERIAL PRIMARY KEY,
    dong_name           VARCHAR(50),
    housing_type        VARCHAR(20),
    area_range          VARCHAR(20),            -- 면적 구간 (예: 40~60㎡)
    avg_deposit         INTEGER,                -- 평균 전세보증금(만원)
    avg_sale_price      INTEGER,                -- 평균 매매가(만원)
    jeonse_ratio        NUMERIC(5,2),           -- 전세가율(%) = avg_deposit/avg_sale_price*100
    risk_level          VARCHAR(10),            -- 안전/주의/위험
    base_year_month     INTEGER,                -- 기준월 (YYYYMM)
    created_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE (dong_name, housing_type, area_range, base_year_month)
);

-- 4. RAG용 문서 메타데이터
CREATE TABLE rag_documents (
    id                  SERIAL PRIMARY KEY,
    doc_type            VARCHAR(30),            -- 법령/판례/사례집/서식
    title               VARCHAR(200),
    file_name           VARCHAR(200),
    chunk_index         INTEGER,                -- 청크 번호
    chunk_text          TEXT,                   -- 청크 텍스트 (검색용)
    vector_id           VARCHAR(100),           -- 임베딩 완료 여부 추적 (chunk_{id} or NULL)
    source_law          VARCHAR(100),           -- 관련 법령명
    created_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE (file_name, chunk_index)
);
-- 벡터는 langchain_postgres가 langchain_pg_embedding 테이블에 자동 저장

-- 5. 진단 요청/결과 로그
CREATE TABLE diagnosis_logs (
    id                  SERIAL PRIMARY KEY,
    session_id          VARCHAR(50),
    input_text          TEXT,                   -- 사용자 입력 (계약서 내용 등)
    risk_score          NUMERIC(4,2),           -- 위험 점수 0~100
    risk_level          VARCHAR(10),            -- 안전/주의/위험
    risk_factors        JSONB,                  -- 위험 요인 목록
    rag_references      JSONB,                  -- 참조된 법령/판례
    result_summary      TEXT,                   -- 진단 결과 요약
    created_at          TIMESTAMP DEFAULT NOW()
);

-- =============================================
-- 인덱스
-- =============================================
CREATE INDEX idx_jeonse_dong ON jeonse_transactions(dong_name);
CREATE INDEX idx_jeonse_housing_type ON jeonse_transactions(housing_type);
CREATE INDEX idx_jeonse_contract_date ON jeonse_transactions(contract_date);
CREATE INDEX idx_sale_sigungu ON sale_transactions(sigungu);
CREATE INDEX idx_price_ratio_dong ON price_ratio(dong_name);
CREATE INDEX idx_rag_doc_type ON rag_documents(doc_type);
CREATE INDEX idx_rag_vector_id ON rag_documents(vector_id);
CREATE INDEX idx_diagnosis_session ON diagnosis_logs(session_id);
CREATE INDEX idx_diagnosis_risk ON diagnosis_logs(risk_level);
