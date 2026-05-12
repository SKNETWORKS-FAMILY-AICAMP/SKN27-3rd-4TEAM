"""
전세계약 위험 진단 에이전트
데이터 전처리 + PostgreSQL 적재 스크립트

수정사항:
- 23~25년 여러 파일 glob으로 읽기
- 전세/매매 컬럼 통일 (파일명 기반 housing_type 자동 감지)
- 매매 23-24 vs 25 컬럼 분기 처리
- 날짜 처리 (deal_date → deal_year_month)
- encoding utf-8-sig 처리
- base_year_month 동적 설정
"""

import os
import glob
import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "db"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "jeonse_risk"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}

DATA_DIR = "data"


# =============================================
# 유틸
# =============================================
def read_csv(filepath: str) -> pd.DataFrame:
    """utf-8-sig → utf-8 순서로 읽기"""
    for enc in ["utf-8-sig", "utf-8", "cp949"]:
        try:
            return pd.read_csv(filepath, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩 실패: {filepath}")


def detect_housing_type(fname: str) -> str:
    """파일명으로 주택유형 자동 감지"""
    if "연립" in fname:
        return "연립다세대"
    elif "오피스텔" in fname or "오피" in fname:
        return "오피스텔"
    return "기타"


# =============================================
# 1. 전세 실거래가 전처리
# =============================================
def _normalize_jeonse_cols(df: pd.DataFrame, housing_type: str) -> pd.DataFrame:
    """파일마다 다른 컬럼명 통일"""

    # property_name 통일
    if "property_name" not in df.columns:
        if "house_name" in df.columns:
            df = df.rename(columns={"house_name": "property_name"})
        elif "officetel_name" in df.columns:
            df = df.rename(columns={"officetel_name": "property_name"})
        else:
            df["property_name"] = ""

    # housing_type 추가
    df["housing_type"] = housing_type

    # 필수 컬럼 확인 + 기본값
    df["jibun"]          = df.get("jibun", "")
    df["monthly_rent"]   = pd.to_numeric(df.get("monthly_rent", 0), errors="coerce").fillna(0).astype(int)
    df["contract_type"]  = df.get("contract_type", "미상").fillna("미상")
    df["contract_term"]  = df.get("contract_term", "").fillna("")
    df["build_year"]     = pd.to_numeric(df.get("build_year", 0), errors="coerce").fillna(0).astype(int)
    df["floor"]          = pd.to_numeric(df.get("floor", 0), errors="coerce").fillna(0).astype(int)
    df["exclusive_area_m2"] = pd.to_numeric(df.get("exclusive_area_m2", 0), errors="coerce").fillna(0)
    df["deposit_amount"] = pd.to_numeric(df.get("deposit_amount", 0), errors="coerce").fillna(0)
    df["contract_date"]  = pd.to_datetime(df.get("contract_date", ""), errors="coerce").dt.date
    df["dong_name"]      = df.get("dong_name", "").fillna("")

    return df


def preprocess_jeonse_all() -> pd.DataFrame:
    """23~25년 전세 파일 전부 읽어서 통합"""
    files = glob.glob(f"{DATA_DIR}/**/*전세*.csv", recursive=True)

    if not files:
        print("[WARNING] 전세 CSV 파일 없음")
        return pd.DataFrame()

    dfs = []
    for f in sorted(files):
        fname        = os.path.basename(f)
        housing_type = detect_housing_type(fname)
        print(f"  읽기: {fname} ({housing_type})")

        df = read_csv(f)
        df = _normalize_jeonse_cols(df, housing_type)
        dfs.append(df)

    result = pd.concat(dfs, ignore_index=True)

    # 유효 데이터만
    result = result[result["deposit_amount"] > 0]
    result = result[result["exclusive_area_m2"] > 0]
    result["build_year"] = result["build_year"].replace(0, None)

    # 중복 제거
    before = len(result)
    result = result.drop_duplicates(
        subset=["housing_type", "dong_name", "jibun",
                "exclusive_area_m2", "deposit_amount", "contract_date", "floor"]
    )
    print(f"[전세] 총 {len(result)}건 (중복 {before - len(result)}건 제거)")
    return result


# =============================================
# 2. 매매 실거래가 전처리
# =============================================
def _normalize_sale_cols(df: pd.DataFrame, housing_type: str, fname: str) -> pd.DataFrame:
    """파일마다 다른 컬럼명 통일 (23-24 vs 25 분기)"""

    df["housing_type"] = housing_type
    default_text = pd.Series([""] * len(df), index=df.index)
    default_zero = pd.Series([0] * len(df), index=df.index)

    # deal_amount 처리
    df["deal_amount"] = pd.to_numeric(
        df.get("deal_amount", default_zero).astype(str).str.replace(",", ""), errors="coerce"
    ).fillna(0)

    # bldg_nm / property_name 통일
    if "bldg_nm" not in df.columns:
        if "house_name" in df.columns:
            df["bldg_nm"] = df["house_name"]
        elif "officetel_name" in df.columns:
            df["bldg_nm"] = df["officetel_name"]
        else:
            df["bldg_nm"] = ""

    # exclusive_area 통일
    if "exclusive_area" not in df.columns:
        if "exclusive_area_m2" in df.columns:
            df["exclusive_area"] = df["exclusive_area_m2"]
        else:
            df["exclusive_area"] = 0
    df["exclusive_area"] = pd.to_numeric(df["exclusive_area"], errors="coerce").fillna(0)

    # sigungu 통일
    if "sigungu" not in df.columns:
        if "sgg_name" in df.columns:
            df["sigungu"] = df["sgg_name"]
        else:
            df["sigungu"] = ""
    df["sigungu"] = df["sigungu"].fillna("")

    # dong_name 통일
    if "dong_name" not in df.columns:
        if "umd_nm" in df.columns:
            df["dong_name"] = df["umd_nm"]
        elif "legal_dong" in df.columns:
            df["dong_name"] = df["legal_dong"]
        else:
            df["dong_name"] = ""
    df["dong_name"] = df["dong_name"].fillna("")

    # deal_year_month 처리
    if "deal_year_month" in df.columns:
        # 25년 매매: deal_year_month + deal_day 이미 분리돼 있음
        df["deal_year_month"] = pd.to_numeric(df["deal_year_month"], errors="coerce").fillna(0).astype(int)
    elif "deal_date" in df.columns:
        # 23-24년 매매: deal_date → deal_year_month 변환
        df["deal_year_month"] = pd.to_datetime(
            df["deal_date"], errors="coerce"
        ).dt.strftime("%Y%m").fillna(0).astype(int)
    else:
        df["deal_year_month"] = 0

    df["floor"]      = pd.to_numeric(df.get("floor", 0), errors="coerce").fillna(0).astype(int)
    df["build_year"] = pd.to_numeric(df.get("build_year", 0), errors="coerce").fillna(0).astype(int)
    df["deal_type"]  = df.get("deal_type", default_text).fillna("")

    return df


def preprocess_sale_all() -> tuple[pd.DataFrame, pd.DataFrame]:
    """23~25년 매매 파일 전부 읽어서 유형별 통합"""
    files = glob.glob(f"{DATA_DIR}/**/*매매*.csv", recursive=True)

    if not files:
        print("[WARNING] 매매 CSV 파일 없음")
        return pd.DataFrame(), pd.DataFrame()

    연립_dfs   = []
    오피스텔_dfs = []

    for f in sorted(files):
        fname        = os.path.basename(f)
        housing_type = detect_housing_type(fname)
        print(f"  읽기: {fname} ({housing_type})")

        df = read_csv(f)
        df = _normalize_sale_cols(df, housing_type, fname)

        if housing_type == "연립다세대":
            연립_dfs.append(df)
        elif housing_type == "오피스텔":
            오피스텔_dfs.append(df)

    def merge_and_clean(dfs, label):
        if not dfs:
            return pd.DataFrame()
        result = pd.concat(dfs, ignore_index=True)
        result = result[result["deal_amount"] > 0]
        result = result[result["exclusive_area"] > 0]
        result["build_year"] = result["build_year"].replace(0, None)
        before = len(result)
        result = result.drop_duplicates(
            subset=["housing_type", "bldg_nm", "exclusive_area",
                    "deal_amount", "deal_year_month", "floor"]
        )
        print(f"[매매/{label}] 총 {len(result)}건 (중복 {before - len(result)}건 제거)")
        return result

    sale_연립    = merge_and_clean(연립_dfs,    "연립다세대")
    sale_오피스텔 = merge_and_clean(오피스텔_dfs, "오피스텔")
    return sale_연립, sale_오피스텔


# =============================================
# 3. 전세가율 계산
# =============================================
def calc_price_ratio(jeonse_df: pd.DataFrame, sale_df: pd.DataFrame) -> pd.DataFrame:
    """기존 전세가율은 유지하고, 동/주택유형별 평당가율을 추가 계산."""
    M2_PER_PYEONG = 3.305785

    def area_bucket(area):
        if area < 33:   return "~33㎡"
        elif area < 66: return "33~66㎡"
        elif area < 99: return "66~99㎡"
        else:           return "99㎡~"

    jeonse_df = jeonse_df.copy()
    sale_df = sale_df.copy()

    jeonse_df["area_range"] = jeonse_df["exclusive_area_m2"].apply(area_bucket)
    sale_df["area_range"] = sale_df["exclusive_area"].apply(
        lambda x: area_bucket(x) if pd.notna(x) else "미상"
    )

    jeonse_avg = jeonse_df.groupby(
        ["dong_name", "area_range", "housing_type"], as_index=False
    )["deposit_amount"].mean()
    jeonse_avg = jeonse_avg.rename(columns={"deposit_amount": "avg_deposit"})

    sale_avg = sale_df.groupby(
        ["area_range", "housing_type"], as_index=False
    )["deal_amount"].mean()
    sale_avg = sale_avg.rename(columns={"deal_amount": "avg_sale_price"})

    merged = jeonse_avg.merge(sale_avg, on=["area_range", "housing_type"], how="left")
    merged["jeonse_ratio"] = (
        merged["avg_deposit"] / merged["avg_sale_price"].replace(0, np.nan) * 100
    ).round(2)

    jeonse_df["pyeong"] = jeonse_df["exclusive_area_m2"] / M2_PER_PYEONG
    sale_df["pyeong"] = sale_df["exclusive_area"] / M2_PER_PYEONG
    jeonse_per_pyeong = jeonse_df[jeonse_df["pyeong"] > 0].copy()
    sale_per_pyeong = sale_df[sale_df["pyeong"] > 0].copy()

    jeonse_per_pyeong["deposit_per_pyeong"] = (
        jeonse_per_pyeong["deposit_amount"] / jeonse_per_pyeong["pyeong"]
    )
    sale_per_pyeong["sale_price_per_pyeong"] = (
        sale_per_pyeong["deal_amount"] / sale_per_pyeong["pyeong"]
    )

    pyeong_jeonse_avg = jeonse_per_pyeong.groupby(
        ["dong_name", "housing_type"], as_index=False
    )["deposit_per_pyeong"].mean()
    pyeong_jeonse_avg = pyeong_jeonse_avg.rename(
        columns={"deposit_per_pyeong": "avg_deposit_per_pyeong"}
    )

    pyeong_sale_avg = sale_per_pyeong.groupby(
        ["dong_name", "housing_type"], as_index=False
    )["sale_price_per_pyeong"].mean()
    pyeong_sale_avg = pyeong_sale_avg.rename(
        columns={"sale_price_per_pyeong": "avg_sale_price_per_pyeong"}
    )

    pyeong_ratio = pyeong_jeonse_avg.merge(
        pyeong_sale_avg, on=["dong_name", "housing_type"], how="left"
    )
    pyeong_ratio["pyeong_jeonse_ratio"] = (
        pyeong_ratio["avg_deposit_per_pyeong"]
        / pyeong_ratio["avg_sale_price_per_pyeong"].replace(0, np.nan)
        * 100
    ).round(2)

    merged = merged.merge(
        pyeong_ratio,
        on=["dong_name", "housing_type"],
        how="left",
    )

    latest = jeonse_df["contract_date"].dropna().max()
    merged["base_year_month"] = int(
        pd.Timestamp(latest).strftime("%Y%m")
    ) if latest else 202512

    int_columns = [
        "avg_deposit", "avg_sale_price",
        "avg_deposit_per_pyeong", "avg_sale_price_per_pyeong",
    ]
    for col in int_columns:
        merged[col] = merged[col].fillna(0).round().astype(int)

    merged = merged[
        ["dong_name", "housing_type", "area_range", "avg_deposit",
         "avg_sale_price", "jeonse_ratio", "avg_deposit_per_pyeong",
         "avg_sale_price_per_pyeong", "pyeong_jeonse_ratio", "base_year_month"]
    ]

    print(f"[전세가율/평당가율] 계산 완료: {len(merged)}개 구간")
    return merged


# =============================================
# 4. PostgreSQL 적재
# =============================================
def load_to_postgres(jeonse_df, sale_연립, sale_오피스텔, ratio_df):
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur  = conn.cursor()

    try:
        cur.execute("""
            ALTER TABLE price_ratio
                ADD COLUMN IF NOT EXISTS avg_deposit_per_pyeong INTEGER,
                ADD COLUMN IF NOT EXISTS avg_sale_price_per_pyeong INTEGER,
                ADD COLUMN IF NOT EXISTS pyeong_jeonse_ratio NUMERIC(5,2),
                DROP COLUMN IF EXISTS risk_level
        """)

        # 전세 적재
        jeonse_rows = [
            (
                row.housing_type, row.property_name, row.dong_name,
                row.jibun, row.exclusive_area_m2, row.deposit_amount,
                row.monthly_rent, row.floor,
                int(row.build_year) if pd.notna(row.build_year) and row.build_year else None,
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
            ON CONFLICT (housing_type, dong_name, jibun, exclusive_area_m2,
                         deposit_amount, contract_date, floor)
            DO UPDATE SET
                property_name = EXCLUDED.property_name,
                contract_type = EXCLUDED.contract_type,
                contract_term = EXCLUDED.contract_term
        """, jeonse_rows)
        print(f"[적재] jeonse_transactions: {len(jeonse_rows)}건")

        # 매매 적재
        sale_all  = pd.concat([sale_연립, sale_오피스텔], ignore_index=True)
        sale_rows = [
            (
                row.housing_type, row.sigungu, row.bldg_nm,
                row.exclusive_area, row.deal_amount, row.floor,
                int(row.build_year) if row.build_year else None,
                int(row.deal_year_month) if row.deal_year_month else None,
                row.deal_type
            )
            for row in sale_all.itertuples()
        ]
        execute_values(cur, """
            INSERT INTO sale_transactions
            (housing_type, sigungu, bldg_nm, exclusive_area, deal_amount,
             floor, build_year, deal_year_month, deal_type)
            VALUES %s
            ON CONFLICT (housing_type, bldg_nm, exclusive_area,
                         deal_amount, deal_year_month, floor)
            DO UPDATE SET
                deal_type = EXCLUDED.deal_type,
                sigungu   = EXCLUDED.sigungu
        """, sale_rows)
        print(f"[적재] sale_transactions: {len(sale_rows)}건")

        # 전세가율/평당가율 적재
        ratio_rows = [
            (
                row.dong_name, row.housing_type, row.area_range,
                row.avg_deposit, row.avg_sale_price,
                row.jeonse_ratio if pd.notna(row.jeonse_ratio) else None,
                row.avg_deposit_per_pyeong,
                row.avg_sale_price_per_pyeong,
                row.pyeong_jeonse_ratio if pd.notna(row.pyeong_jeonse_ratio) else None,
                row.base_year_month,
            )
            for row in ratio_df.itertuples()
        ]
        execute_values(cur, """
            INSERT INTO price_ratio
            (dong_name, housing_type, area_range, avg_deposit, avg_sale_price,
             jeonse_ratio, avg_deposit_per_pyeong, avg_sale_price_per_pyeong,
             pyeong_jeonse_ratio, base_year_month)
            VALUES %s
            ON CONFLICT (dong_name, housing_type, area_range, base_year_month)
            DO UPDATE SET
                avg_deposit               = EXCLUDED.avg_deposit,
                avg_sale_price            = EXCLUDED.avg_sale_price,
                jeonse_ratio              = EXCLUDED.jeonse_ratio,
                avg_deposit_per_pyeong    = EXCLUDED.avg_deposit_per_pyeong,
                avg_sale_price_per_pyeong = EXCLUDED.avg_sale_price_per_pyeong,
                pyeong_jeonse_ratio       = EXCLUDED.pyeong_jeonse_ratio
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
    print("=== 전처리 시작 ===")
    print(f"데이터 경로: {DATA_DIR}/")

    jeonse_df            = preprocess_jeonse_all()
    sale_연립, sale_오피스텔 = preprocess_sale_all()

    if jeonse_df.empty:
        print("❌ 전세 데이터 없음")
        exit(1)

    sale_all = pd.concat([sale_연립, sale_오피스텔], ignore_index=True)
    ratio_df = calc_price_ratio(jeonse_df, sale_all)

    print("\n=== DB 적재 시작 ===")
    load_to_postgres(jeonse_df, sale_연립, sale_오피스텔, ratio_df)

