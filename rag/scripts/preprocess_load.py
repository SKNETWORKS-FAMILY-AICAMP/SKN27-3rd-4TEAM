"""
전세계약 위험 진단 에이전트
데이터 전처리 + PostgreSQL 적재 스크립트

담당: 데이터 엔지니어
"""

import os
import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "db"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "jeonse_risk"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}

# =============================================
# 1. 전세 실거래가 전처리
# =============================================
def preprocess_jeonse(filepath: str) -> pd.DataFrame:
    df = pd.read_csv(filepath, encoding='utf-8')

    df = df[[
        'housing_type', 'property_name', 'dong_name',
        'jibun', 'exclusive_area_m2', 'deposit_amount',
        'monthly_rent', 'floor', 'build_year',
        'contract_type', 'contract_term', 'contract_date'
    ]]

    df['contract_type'] = df['contract_type'].fillna('미상')
    df['contract_term'] = df['contract_term'].fillna('')
    df['build_year'] = df['build_year'].fillna(0).astype(int).replace(0, None)
    df['contract_date'] = pd.to_datetime(df['contract_date'], errors='coerce').dt.date
    df = df[df['deposit_amount'] > 0]
    df['monthly_rent'] = df['monthly_rent'].fillna(0).astype(int)

    # 중복 제거 (unique 제약 기준)
    before = len(df)
    df = df.drop_duplicates(subset=['housing_type', 'dong_name', 'jibun', 'exclusive_area_m2', 'deposit_amount', 'contract_date', 'floor'])
    print(f"[전세] 처리 완료: {len(df)}건 (중복 {before - len(df)}건 제거)")
    return df


# =============================================
# 2. 매매 실거래가 전처리
# =============================================
def preprocess_sale(filepath: str, housing_type: str) -> pd.DataFrame:
    df = pd.read_csv(filepath, encoding='utf-8')

    df['deal_amount'] = (
        df['deal_amount']
        .astype(str)
        .str.replace(',', '', regex=False)
        .str.strip()
    )
    df['deal_amount'] = pd.to_numeric(df['deal_amount'], errors='coerce')
    df = df[df['deal_amount'] > 0]

    result = pd.DataFrame({
        'housing_type':   housing_type,
        'sigungu':        df['sigungu'],
        'bldg_nm':        df['bldg_nm'],
        'exclusive_area': pd.to_numeric(df['exclusive_area'], errors='coerce'),
        'deal_amount':    df['deal_amount'].astype(int),
        'floor':          pd.to_numeric(df['floor'], errors='coerce').fillna(0).astype(int),
        'build_year':     pd.to_numeric(df['build_year'], errors='coerce').fillna(0).astype(int),
        'deal_year_month':pd.to_numeric(df['deal_year_month'], errors='coerce').fillna(0).astype(int),
        'deal_type':      df.get('deal_type', ''),
    })

    # 중복 제거 (unique 제약 기준)
    before = len(result)
    result = result.drop_duplicates(subset=['housing_type', 'bldg_nm', 'exclusive_area', 'deal_amount', 'deal_year_month', 'floor'])
    print(f"[매매/{housing_type}] 처리 완료: {len(result)}건 (중복 {before - len(result)}건 제거)")
    return result


# =============================================
# 3. 전세가율 계산
# =============================================
def calc_price_ratio(jeonse_df: pd.DataFrame, sale_df: pd.DataFrame) -> pd.DataFrame:
    def area_bucket(area):
        if area < 33:   return '~33㎡'
        elif area < 66: return '33~66㎡'
        elif area < 99: return '66~99㎡'
        else:           return '99㎡~'

    jeonse_df = jeonse_df.copy()
    jeonse_df['area_range'] = jeonse_df['exclusive_area_m2'].apply(area_bucket)

    sale_df = sale_df.copy()
    sale_df['area_range'] = sale_df['exclusive_area'].apply(lambda x: area_bucket(x) if pd.notna(x) else '미상')

    jeonse_avg = jeonse_df.groupby(['dong_name', 'area_range', 'housing_type'])['deposit_amount'].mean().reset_index()
    jeonse_avg.columns = ['dong_name', 'area_range', 'housing_type', 'avg_deposit']

    sale_avg = sale_df.groupby(['area_range', 'housing_type'])['deal_amount'].mean().reset_index()
    sale_avg.columns = ['area_range', 'housing_type', 'avg_sale_price']

    merged = jeonse_avg.merge(sale_avg, on=['area_range', 'housing_type'], how='left')
    merged['jeonse_ratio'] = (merged['avg_deposit'] / merged['avg_sale_price'] * 100).round(2)

    def risk_level(ratio):
        if pd.isna(ratio): return '미상'
        elif ratio >= 80:  return '위험'
        elif ratio >= 70:  return '주의'
        else:              return '안전'

    merged['risk_level'] = merged['jeonse_ratio'].apply(risk_level)
    merged['base_year_month'] = 202512

    merged['avg_deposit']    = merged['avg_deposit'].fillna(0).astype(int)
    merged['avg_sale_price'] = merged['avg_sale_price'].fillna(0).astype(int)

    print(f"[전세가율] 계산 완료: {len(merged)}개 구간")
    print(merged['risk_level'].value_counts())
    return merged


# =============================================
# 4. PostgreSQL 적재 (트랜잭션 + ON CONFLICT DO UPDATE)
# =============================================
def load_to_postgres(jeonse_df, sale_연립, sale_오피스텔, ratio_df):
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # 전세 적재
        jeonse_rows = [
            (
                row.housing_type, row.property_name, row.dong_name,
                row.jibun, row.exclusive_area_m2, row.deposit_amount,
                row.monthly_rent, row.floor,
                int(row.build_year) if pd.notna(row.build_year) else None,
                row.contract_type, row.contract_term, row.contract_date
            )
            for row in jeonse_df.itertuples()
        ]
        execute_values(cur, """
            INSERT INTO jeonse_transactions
            (housing_type, property_name, dong_name, jibun, exclusive_area_m2,
             deposit_amount, monthly_rent, floor, build_year,
             contract_type, contract_term, contract_date)
            VALUES %s
            ON CONFLICT (housing_type, dong_name, jibun, exclusive_area_m2, deposit_amount, contract_date, floor)
            DO UPDATE SET
                property_name = EXCLUDED.property_name,
                contract_type = EXCLUDED.contract_type,
                contract_term = EXCLUDED.contract_term
        """, jeonse_rows)
        print(f"[적재] jeonse_transactions: {len(jeonse_rows)}건")

        # 매매 적재
        sale_all = pd.concat([sale_연립, sale_오피스텔], ignore_index=True)
        sale_rows = [
            (
                row.housing_type, row.sigungu, row.bldg_nm,
                row.exclusive_area, row.deal_amount, row.floor,
                row.build_year if row.build_year else None,
                row.deal_year_month if row.deal_year_month else None,
                row.deal_type
            )
            for row in sale_all.itertuples()
        ]
        execute_values(cur, """
            INSERT INTO sale_transactions
            (housing_type, sigungu, bldg_nm, exclusive_area, deal_amount,
             floor, build_year, deal_year_month, deal_type)
            VALUES %s
            ON CONFLICT (housing_type, bldg_nm, exclusive_area, deal_amount, deal_year_month, floor)
            DO UPDATE SET
                deal_type = EXCLUDED.deal_type,
                sigungu   = EXCLUDED.sigungu
        """, sale_rows)
        print(f"[적재] sale_transactions: {len(sale_rows)}건")

        # 전세가율 적재
        ratio_rows = [
            (
                row.dong_name, row.housing_type, row.area_range,
                row.avg_deposit, row.avg_sale_price,
                row.jeonse_ratio if pd.notna(row.jeonse_ratio) else None,
                row.risk_level, row.base_year_month
            )
            for row in ratio_df.itertuples()
        ]
        execute_values(cur, """
            INSERT INTO price_ratio
            (dong_name, housing_type, area_range, avg_deposit, avg_sale_price,
             jeonse_ratio, risk_level, base_year_month)
            VALUES %s
            ON CONFLICT (dong_name, housing_type, area_range, base_year_month)
            DO UPDATE SET
                avg_deposit    = EXCLUDED.avg_deposit,
                avg_sale_price = EXCLUDED.avg_sale_price,
                jeonse_ratio   = EXCLUDED.jeonse_ratio,
                risk_level     = EXCLUDED.risk_level
        """, ratio_rows)
        print(f"[적재] price_ratio: {len(ratio_rows)}건")

        conn.commit()
        print("✅ 전체 적재 완료!")

    except Exception as e:
        conn.rollback()
        print(f"❌ 에러 발생 - 롤백 완료: {e}")
        raise

    finally:
        cur.close()
        conn.close()


# =============================================
# 실행
# =============================================
if __name__ == "__main__":
    JEONSE_PATH       = "data/2025_전세_종로구_통합_cleaned.csv"
    SALE_연립_PATH    = "data/fixed_연립다세대(매매)_실거래가_20260507195717.csv"
    SALE_오피스텔_PATH = "data/fixed_오피스텔(매매)_실거래가_20260507195801.csv"

    print("=== 전처리 시작 ===")
    jeonse_df  = preprocess_jeonse(JEONSE_PATH)
    sale_연립   = preprocess_sale(SALE_연립_PATH, '연립다세대')
    sale_오피스텔 = preprocess_sale(SALE_오피스텔_PATH, '오피스텔')
    ratio_df   = calc_price_ratio(jeonse_df, pd.concat([sale_연립, sale_오피스텔]))

    print("\n=== DB 적재 시작 ===")
    load_to_postgres(jeonse_df, sale_연립, sale_오피스텔, ratio_df)