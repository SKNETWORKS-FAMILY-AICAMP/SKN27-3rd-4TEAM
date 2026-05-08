"""
전세계약 위험 진단 에이전트
공공데이터포털 API로 실거래가 자동 수집

실행: python fetch_data.py
"""

import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from datetime import datetime
from dateutil.relativedelta import relativedelta
from PublicDataReader import TransactionPrice

load_dotenv()

API_KEY      = os.getenv("PUBLIC_DATA_API_KEY")
SIGUNGU_CODE = "11110"  # 서울 종로구

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "db"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "jeonse_risk"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}

api = TransactionPrice(API_KEY)


# =============================================
# 0. 수집 기간 결정 (마지막 데이터 ~ 현재달)
# =============================================
def get_date_range() -> tuple[str, str]:
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    cur.execute("SELECT MAX(contract_date) FROM jeonse_transactions")
    last_date = cur.fetchone()[0]

    cur.close()
    conn.close()

    end_ym = datetime.now().strftime("%Y%m")

    if last_date is None:
        # DB가 비어있으면 기본 시작월
        start_ym = "202501"
    else:
        # 마지막 데이터 다음달부터
        start_ym = (last_date + relativedelta(months=1)).strftime("%Y%m")

    print(f"[수집 기간] {start_ym} ~ {end_ym}")
    return start_ym, end_ym


# =============================================
# 1. 전세 데이터 수집
# =============================================
def fetch_jeonse(start_ym: str, end_ym: str) -> pd.DataFrame:
    print("[수집] 연립다세대 전월세...")
    df1 = api.get_data(
        property_type="연립다세대",
        trade_type="전월세",
        sigungu_code=SIGUNGU_CODE,
        start_year_month=start_ym,
        end_year_month=end_ym,
    )

    print("[수집] 오피스텔 전월세...")
    df2 = api.get_data(
        property_type="오피스텔",
        trade_type="전월세",
        sigungu_code=SIGUNGU_CODE,
        start_year_month=start_ym,
        end_year_month=end_ym,
    )

    df1["housing_type"] = "연립다세대"
    df2["housing_type"] = "오피스텔"
    df = pd.concat([df1, df2], ignore_index=True)
    print(f"[완료] 전세 총 {len(df)}건 수집")
    return df


# =============================================
# 2. 매매 데이터 수집
# =============================================
def fetch_sale(start_ym: str, end_ym: str) -> pd.DataFrame:
    print("[수집] 연립다세대 매매...")
    df1 = api.get_data(
        property_type="연립다세대",
        trade_type="매매",
        sigungu_code=SIGUNGU_CODE,
        start_year_month=start_ym,
        end_year_month=end_ym,
    )

    print("[수집] 오피스텔 매매...")
    df2 = api.get_data(
        property_type="오피스텔",
        trade_type="매매",
        sigungu_code=SIGUNGU_CODE,
        start_year_month=start_ym,
        end_year_month=end_ym,
    )

    df1["housing_type"] = "연립다세대"
    df2["housing_type"] = "오피스텔"
    df = pd.concat([df1, df2], ignore_index=True)
    print(f"[완료] 매매 총 {len(df)}건 수집")
    return df


# =============================================
# 3. DB 적재 (기존 데이터 유지 + 신규만 추가)
# =============================================
def load_jeonse(df: pd.DataFrame):
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    rows = []
    for _, row in df.iterrows():
        try:
            rows.append((
                row.get("housing_type"),
                row.get("단지명") or row.get("연립다세대명") or "",
                row.get("법정동"),
                row.get("지번"),
                float(row.get("전용면적", 0) or 0),
                int(str(row.get("보증금액", 0)).replace(",", "") or 0),
                int(str(row.get("월세금액", 0)).replace(",", "") or 0),
                int(row.get("층", 0) or 0),
                int(row.get("건축년도", 0) or 0) or None,
                row.get("전월세구분"),
                row.get("계약기간"),
                pd.to_datetime(
                    str(row.get("계약년월", "")) + str(row.get("계약일", "")).zfill(2),
                    format="%Y%m%d", errors="coerce"
                ).date() if row.get("계약년월") else None,
            ))
        except Exception as e:
            print(f"행 스킵: {e}")
            continue

    try:
        conn.autocommit = False
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
        """, rows)
        conn.commit()
        print(f"[적재] jeonse_transactions: {len(rows)}건 처리 완료")
    except Exception as e:
        conn.rollback()
        print(f"[에러] jeonse_transactions 롤백: {e}")
    finally:
        cur.close()
        conn.close()


def load_sale(df: pd.DataFrame):
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()

    rows = []
    for _, row in df.iterrows():
        try:
            rows.append((
                row.get("housing_type"),
                row.get("법정구분") or "",
                row.get("단지명") or row.get("연립다세대명") or "",
                float(row.get("전용면적", 0) or 0),
                int(str(row.get("거래금액", 0)).replace(",", "") or 0),
                int(row.get("층", 0) or 0),
                int(row.get("건축년도", 0) or 0) or None,
                int(str(row.get("계약년월", 0))) if row.get("계약년월") else None,
                row.get("거래유형") or "",
            ))
        except Exception as e:
            print(f"행 스킵: {e}")
            continue

    try:
        conn.autocommit = False
        execute_values(cur, """
            INSERT INTO sale_transactions
            (housing_type, sigungu, bldg_nm, exclusive_area, deal_amount,
             floor, build_year, deal_year_month, deal_type)
            VALUES %s
            ON CONFLICT (housing_type, bldg_nm, exclusive_area, deal_amount, deal_year_month, floor)
            DO UPDATE SET
                deal_type = EXCLUDED.deal_type,
                sigungu   = EXCLUDED.sigungu
        """, rows)
        conn.commit()
        print(f"[적재] sale_transactions: {len(rows)}건 처리 완료")
    except Exception as e:
        conn.rollback()
        print(f"[에러] sale_transactions 롤백: {e}")
    finally:
        cur.close()
        conn.close()


# =============================================
# 실행
# =============================================
if __name__ == "__main__":
    print("=== 실거래가 API 수집 시작 ===")

    start_ym, end_ym = get_date_range()

    if start_ym > end_ym:
        print("✅ 이미 최신 데이터입니다. 수집 종료.")
    else:
        jeonse_df = fetch_jeonse(start_ym, end_ym)
        sale_df   = fetch_sale(start_ym, end_ym)

        print("\n=== DB 적재 시작 ===")
        load_jeonse(jeonse_df)
        load_sale(sale_df)

        print("\n✅ 완료!")
