"""
전세계약 위험 진단 에이전트
데이터 전처리 + PostgreSQL 적재 스크립트

수정사항:
- 2016~2025년 전세/매매 데이터 glob으로 읽기
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
# 3. 전세가율 계산 (v2: 최근 6개월 가중 이동평균)
# =============================================
def calc_price_ratio(jeonse_df: pd.DataFrame, sale_df: pd.DataFrame) -> pd.DataFrame:
    """
    개선사항 (v2):
      - 전체 기간 단순 평균 → 최근 6개월 데이터 우선 사용 (없으면 12개월 확장)
      - 매매가도 최근 6개월 실거래가 기준 적용
      - 면적 구간 5개 세분화 (~33, 33~50, 50~66, 66~99, 99~)
      - 평당가율(pyeong_jeonse_ratio) 추가 계산
    """
    from datetime import date, timedelta
    M2_PER_PYEONG = 3.305785

    def area_bucket(area):
        if area < 33:   return '~33㎡'
        elif area < 50: return '33~50㎡'
        elif area < 66: return '50~66㎡'
        elif area < 99: return '66~99㎡'
        else:           return '99㎡~'

    jeonse_df = jeonse_df.copy()
    sale_df   = sale_df.copy()

    jeonse_df['area_range'] = jeonse_df['exclusive_area_m2'].apply(area_bucket)
    sale_df['area_range']   = sale_df['exclusive_area'].apply(
        lambda x: area_bucket(x) if pd.notna(x) else '미상'
    )

    # ── 최근 6개월 컷오프 ──────────────────────────────────
    today        = date.today()
    cutoff_6m    = today - timedelta(days=180)
    cutoff_12m   = today - timedelta(days=365)

    if pd.api.types.is_datetime64_any_dtype(jeonse_df['contract_date']):
        jeonse_df['contract_date'] = jeonse_df['contract_date'].dt.date

    recent_6m  = jeonse_df[jeonse_df['contract_date'] >= cutoff_6m]
    recent_12m = jeonse_df[jeonse_df['contract_date'] >= cutoff_12m]

    group_keys = ['dong_name', 'area_range', 'housing_type']

    def _weighted_mean(df_6m, df_12m, group_keys, value_col):
        avg_6m  = df_6m.groupby(group_keys)[value_col].mean().rename('avg_6m')
        avg_12m = df_12m.groupby(group_keys)[value_col].mean().rename('avg_12m')
        merged  = avg_6m.to_frame().join(avg_12m, how='outer')
        merged['avg_final'] = merged['avg_6m'].combine_first(merged['avg_12m'])
        merged['data_period'] = merged['avg_6m'].notna().map({True: '최근6개월', False: '최근12개월'})
        return merged[['avg_final', 'data_period']].reset_index()

    jeonse_avg = _weighted_mean(recent_6m, recent_12m, group_keys, 'deposit_amount')
    jeonse_avg.columns = group_keys + ['avg_deposit', 'data_period']

    cutoff_ym = int(f"{cutoff_6m.year}{cutoff_6m.month:02d}")
    recent_sale = sale_df[sale_df['deal_year_month'] >= cutoff_ym]
    if len(recent_sale) < 10:
        cutoff_ym_12 = int(f"{cutoff_12m.year}{cutoff_12m.month:02d}")
        recent_sale = sale_df[sale_df['deal_year_month'] >= cutoff_ym_12]

    sale_avg = recent_sale.groupby(['area_range', 'housing_type'])['deal_amount'].mean().reset_index()
    sale_avg.columns = ['area_range', 'housing_type', 'avg_sale_price']

    merged = jeonse_avg.merge(sale_avg, on=["area_range", "housing_type"], how="left")
    merged["jeonse_ratio"] = (merged["avg_deposit"] / merged["avg_sale_price"].replace(0, np.nan) * 100).round(2)

    # ── 평당가율 추가 계산 ────────────────────────────────
    jeonse_df["pyeong"] = jeonse_df["exclusive_area_m2"] / M2_PER_PYEONG
    sale_df["pyeong"]   = sale_df["exclusive_area"] / M2_PER_PYEONG
    jeonse_per_pyeong = jeonse_df[jeonse_df["pyeong"] > 0].copy()
    sale_per_pyeong   = sale_df[sale_df["pyeong"] > 0].copy()

    jeonse_per_pyeong["deposit_per_pyeong"] = jeonse_per_pyeong["deposit_amount"] / jeonse_per_pyeong["pyeong"]
    sale_per_pyeong["sale_price_per_pyeong"] = sale_per_pyeong["deal_amount"] / sale_per_pyeong["pyeong"]

    pyeong_jeonse_avg = jeonse_per_pyeong.groupby(["dong_name", "housing_type"], as_index=False)["deposit_per_pyeong"].mean()
    pyeong_jeonse_avg = pyeong_jeonse_avg.rename(columns={"deposit_per_pyeong": "avg_deposit_per_pyeong"})

    pyeong_sale_avg = sale_per_pyeong.groupby(["dong_name", "housing_type"], as_index=False)["sale_price_per_pyeong"].mean()
    pyeong_sale_avg = pyeong_sale_avg.rename(columns={"sale_price_per_pyeong": "avg_sale_price_per_pyeong"})

    pyeong_ratio = pyeong_jeonse_avg.merge(pyeong_sale_avg, on=["dong_name", "housing_type"], how="left")
    pyeong_ratio["pyeong_jeonse_ratio"] = (
        pyeong_ratio["avg_deposit_per_pyeong"] / pyeong_ratio["avg_sale_price_per_pyeong"].replace(0, np.nan) * 100
    ).round(2)

    merged = merged.merge(pyeong_ratio, on=["dong_name", "housing_type"], how="left")

    # base_year_month: 최근 계약일 또는 현재 기준 자동 설정
    latest = jeonse_df["contract_date"].dropna().max()
    merged["base_year_month"] = int(pd.Timestamp(latest).strftime("%Y%m")) if latest else int(f"{today.year}{today.month:02d}")

    int_columns = ["avg_deposit", "avg_sale_price", "avg_deposit_per_pyeong", "avg_sale_price_per_pyeong"]
    for col in int_columns:
        merged[col] = merged[col].fillna(0).round().astype(int)

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
# data/market/ 연도별 파일 자동 병합 유틸
# =============================================
def _merge_market_files(market_dir: str, keyword: str) -> pd.DataFrame:
    """
    data/market/ 폴더에서 keyword가 포함된 CSV를 모두 읽어 합친다.
    예) keyword='전세_연립' → 2023~2025_전세_연립다세대_*.csv 병합
    """
    import glob as _glob
    pattern = os.path.join(market_dir, f"*{keyword}*.csv")
    files = sorted(_glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"[merge] '{pattern}' 파일을 찾을 수 없습니다.")

    frames = []
    for f in files:
        try:
            raw = open(f, 'rb').read(100)
            if raw.count(b'\x00') > 50:
                raise ValueError("null bytes detected — git lfs pull 필요")
            df = pd.read_csv(f, encoding='utf-8')
            frames.append(df)
            print(f"  ✅ {os.path.basename(f)}: {len(df)}행")
        except Exception as e:
            print(f"  ❌ {os.path.basename(f)} 읽기 실패: {e}")
    if not frames:
        raise RuntimeError(f"읽을 수 있는 CSV가 없습니다 ({keyword}). git lfs pull 후 재실행하세요.")
    return pd.concat(frames, ignore_index=True)


def _build_jeonse_df(market_dir: str) -> pd.DataFrame:
    """
    전세_연립다세대 + 전세_오피스텔 파일을 합쳐 preprocess_jeonse 입력 형태로 반환.
    연도별 파일 컬럼명이 영문(cleaned)이면 그대로, 한글이면 매핑 후 사용.
    """
    COL_MAP = {
        # 한글 원시 컬럼 → preprocess_jeonse 기대 컬럼
        '주택유형':   'housing_type',
        '건물명':     'property_name',
        '법정동명':   'dong_name',
        '지번':       'jibun',
        '전용면적':   'exclusive_area_m2',
        '보증금(만원)': 'deposit_amount',
        '월세금액(만원)': 'monthly_rent',
        '층':         'floor',
        '건축년도':   'build_year',
        '계약구분':   'contract_type',
        '계약기간':   'contract_term',
        '계약일':     'contract_date',
    }
    frames = []
    for housing_kw, housing_val in [('전세_연립', '연립다세대'), ('전세_오피스텔', '오피스텔')]:
        df = _merge_market_files(market_dir, housing_kw)
        df = df.rename(columns=COL_MAP)
        if 'housing_type' not in df.columns:
            df['housing_type'] = housing_val
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _build_sale_df(market_dir: str, housing_kw: str, housing_val: str) -> pd.DataFrame:
    """
    매매 연도별 파일 병합 후 preprocess_sale 기대 컬럼으로 매핑.
    """
    COL_MAP = {
        # 한글 원시 컬럼 → preprocess_sale 기대 컬럼
        '자치구명':       'sigungu',
        '건물명':         'bldg_nm',
        '전용면적':       'exclusive_area',
        '물건금액(만원)': 'deal_amount',
        '층':             'floor',
        '건축년도':       'build_year',
        '거래유형':       'deal_type',
    }
    df = _merge_market_files(market_dir, housing_kw)
    df = df.rename(columns=COL_MAP)

    # deal_year_month: YYYYMM 컬럼이 없으면 년+월 컬럼에서 합성
    if 'deal_year_month' not in df.columns:
        if '년' in df.columns and '월' in df.columns:
            df['deal_year_month'] = (
                df['년'].astype(str).str.zfill(4) +
                df['월'].astype(str).str.zfill(2)
            ).astype(int)
        else:
            df['deal_year_month'] = 0

    if 'deal_type' not in df.columns:
        df['deal_type'] = ''

    return df


# =============================================
# 실행
# =============================================
if __name__ == "__main__":
    MARKET_DIR = "data/market"

    print("=== 전처리 시작 ===")
    print(f"\n[전세] {MARKET_DIR}/ 에서 연도별 파일 자동 병합...")
    from pcj_common.tools.contract_tools import preprocess_jeonse, preprocess_sale
    try:
        raw_jeonse = _build_jeonse_df(MARKET_DIR)
        # 임시 파일로 저장 후 preprocess_jeonse 재사용
        _tmp_jeonse = os.path.join(MARKET_DIR, "_merged_jeonse_tmp.csv")
        raw_jeonse.to_csv(_tmp_jeonse, index=False, encoding='utf-8')
        jeonse_df = preprocess_jeonse(_tmp_jeonse)
        os.remove(_tmp_jeonse)
    except Exception as e:
        print(f"❌ 전세 데이터 로드 실패: {e}")
        raise

    print(f"\n[매매] {MARKET_DIR}/ 에서 연도별 파일 자동 병합...")
    try:
        raw_연립 = _build_sale_df(MARKET_DIR, '매매_연립', '연립다세대')
        raw_오피스텔 = _build_sale_df(MARKET_DIR, '매매_오피스텔', '오피스텔')
        _tmp_연립 = os.path.join(MARKET_DIR, "_merged_sale_연립_tmp.csv")
        _tmp_오피스텔 = os.path.join(MARKET_DIR, "_merged_sale_오피스텔_tmp.csv")
        raw_연립.to_csv(_tmp_연립, index=False, encoding='utf-8')
        raw_오피스텔.to_csv(_tmp_오피스텔, index=False, encoding='utf-8')
        sale_연립   = preprocess_sale(_tmp_연립, '연립다세대')
        sale_오피스텔 = preprocess_sale(_tmp_오피스텔, '오피스텔')
        os.remove(_tmp_연립)
        os.remove(_tmp_오피스텔)
    except Exception as e:
        print(f"❌ 매매 데이터 로드 실패: {e}")
        raise

    ratio_df = calc_price_ratio(jeonse_df, pd.concat([sale_연립, sale_오피스텔]))

    print("\n=== DB 적재 시작 ===")
    load_to_postgres(jeonse_df, sale_연립, sale_오피스텔, ratio_df)
