"""
[미사용 — 향후 참고용]
market_price_service.py 와 세트로 사용되는 데이터 적재 스크립트입니다.
현재 금액 기반 판단은 딥러닝 파트에서 담당하므로 실행하지 않아도 됩니다.

실행 전 필수 조건:
  1. database/migration_market.sql 실행 (sale_transactions에 dong_name 컬럼 추가)
  2. data/market/ 폴더에 CSV 파일 12개 배치
     (2023~2025, 매매+전세, 오피스텔+연립다세대, 서울 종로구)

매매·전세 실거래가 CSV → PostgreSQL 적재 스크립트
- 매매: sale_transactions
- 전세: jeonse_transactions

사용법: python rag/ingestion/load_market_data.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

ROOT     = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "market"
load_dotenv(ROOT / ".env")

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "jeonse_risk"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "risk1234"),
)

# ── 대상 파일 목록 ────────────────────────────────────────────────────
SALE_FILES = [
    ("2023_매매_오피스텔_서울_종로구.csv",   "오피스텔"),
    ("2024_매매_오피스텔_서울_종로구.csv",   "오피스텔"),
    ("2025_매매_오피스텔_서울_종로구.csv",   "오피스텔"),
    ("2023_매매_연립다세대_서울_종로구.csv", "연립다세대"),
    ("2024_매매_연립다세대_서울_종로구.csv", "연립다세대"),
    ("2025_매매_연립다세대_서울_종로구.csv", "연립다세대"),
]

JEONSE_FILES = [
    ("2023_전세_오피스텔_서울_종로구.csv",   "오피스텔"),
    ("2024_전세_오피스텔_서울_종로구.csv",   "오피스텔"),
    ("2025_전세_오피스텔_서울_종로구.csv",   "오피스텔"),
    ("2023_전세_연립다세대_서울_종로구.csv", "연립다세대"),
    ("2024_전세_연립다세대_서울_종로구.csv", "연립다세대"),
    ("2025_전세_연립다세대_서울_종로구.csv", "연립다세대"),
]

# ── CSV 파싱 ──────────────────────────────────────────────────────────

def _deal_ym(date_str: str) -> int:
    """'2023-01-19' or '202301' → 202301"""
    s = str(date_str).replace("-", "")[:6]
    return int(s)


def parse_sale(path: Path, housing_type: str) -> pd.DataFrame:
    """
    매매 CSV → sale_transactions 컬럼으로 정규화
    오피스텔:    officetel_name, dong_name, exclusive_area_m2, deal_amount, floor, build_year, contract_date
    연립다세대:  house_name,     dong_name, exclusive_area_m2, deal_amount, floor, build_year, deal_date
    """
    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame()

    # property_name 통일
    if "officetel_name" in df.columns:
        df = df.rename(columns={"officetel_name": "property_name"})
    elif "house_name" in df.columns:
        df = df.rename(columns={"house_name": "property_name"})

    # exclusive_area 통일
    if "exclusive_area_m2" in df.columns:
        df = df.rename(columns={"exclusive_area_m2": "exclusive_area"})

    # deal_year_month
    date_col = "contract_date" if "contract_date" in df.columns else "deal_date"
    df["deal_year_month"] = df[date_col].astype(str).apply(_deal_ym)

    df["housing_type"] = housing_type
    df["deal_type"]    = "중개거래"
    df["sigungu"]      = "서울특별시 종로구"

    return df[[
        "housing_type", "sigungu", "property_name", "dong_name",
        "exclusive_area", "deal_amount", "floor", "build_year",
        "deal_year_month", "deal_type",
    ]].rename(columns={"property_name": "bldg_nm"})


def parse_jeonse(path: Path, housing_type: str) -> pd.DataFrame:
    """
    전세 CSV → jeonse_transactions 컬럼으로 정규화
    컬럼: officetel_name/house_name, dong_name, exclusive_area_m2,
          deposit_amount, monthly_rent, floor, build_year,
          contract_type, contract_term, contract_date
    """
    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame()

    if "officetel_name" in df.columns:
        df = df.rename(columns={"officetel_name": "property_name"})
    elif "house_name" in df.columns:
        df = df.rename(columns={"house_name": "property_name"})

    df["housing_type"] = housing_type

    # 선택적 컬럼 보완
    for col, default in [("monthly_rent", 0), ("contract_type", None), ("contract_term", None)]:
        if col not in df.columns:
            df[col] = default

    return df[[
        "housing_type", "property_name", "dong_name",
        "exclusive_area_m2", "deposit_amount", "monthly_rent",
        "floor", "build_year", "contract_type", "contract_term", "contract_date",
    ]]


# ── INSERT SQL ────────────────────────────────────────────────────────

SALE_SQL = """
INSERT INTO sale_transactions
    (housing_type, sigungu, bldg_nm, dong_name,
     exclusive_area, deal_amount, floor, build_year, deal_year_month, deal_type)
VALUES (%(housing_type)s, %(sigungu)s, %(bldg_nm)s, %(dong_name)s,
        %(exclusive_area)s, %(deal_amount)s, %(floor)s, %(build_year)s,
        %(deal_year_month)s, %(deal_type)s)
ON CONFLICT (housing_type, bldg_nm, exclusive_area, deal_amount, deal_year_month, floor)
DO NOTHING;
"""

JEONSE_SQL = """
INSERT INTO jeonse_transactions
    (housing_type, property_name, dong_name,
     exclusive_area_m2, deposit_amount, monthly_rent,
     floor, build_year, contract_type, contract_term, contract_date)
VALUES (%(housing_type)s, %(property_name)s, %(dong_name)s,
        %(exclusive_area_m2)s, %(deposit_amount)s, %(monthly_rent)s,
        %(floor)s, %(build_year)s, %(contract_type)s, %(contract_term)s,
        %(contract_date)s)
ON CONFLICT (housing_type, dong_name, jibun, exclusive_area_m2, deposit_amount, contract_date, floor)
DO NOTHING;
"""

# jibun이 CSV에 없을 수 있으므로 UNIQUE 제약 우회용 SQL
JEONSE_SQL_SAFE = """
INSERT INTO jeonse_transactions
    (housing_type, property_name, dong_name,
     exclusive_area_m2, deposit_amount, monthly_rent,
     floor, build_year, contract_type, contract_term, contract_date)
SELECT %(housing_type)s, %(property_name)s, %(dong_name)s,
       %(exclusive_area_m2)s, %(deposit_amount)s, %(monthly_rent)s,
       %(floor)s, %(build_year)s, %(contract_type)s, %(contract_term)s,
       %(contract_date)s
WHERE NOT EXISTS (
    SELECT 1 FROM jeonse_transactions
    WHERE housing_type    = %(housing_type)s
      AND dong_name       = %(dong_name)s
      AND exclusive_area_m2 = %(exclusive_area_m2)s
      AND deposit_amount  = %(deposit_amount)s
      AND contract_date   = %(contract_date)s
      AND floor           = %(floor)s
);
"""


# ── 메인 실행 ─────────────────────────────────────────────────────────

def run():
    conn = psycopg2.connect(**DB)
    cur  = conn.cursor()
    total = {"sale": 0, "jeonse": 0, "skip": 0}

    # ── 매매 데이터 적재 ─────────────────────────────────────────────
    print("\n[ 매매 실거래가 적재 ]")
    for fname, htype in SALE_FILES:
        path = DATA_DIR / fname
        if not path.exists():
            print(f"  SKIP {fname} — 파일 없음")
            total["skip"] += 1
            continue
        df = parse_sale(path, htype)
        if df.empty:
            print(f"  SKIP {fname} — 빈 파일")
            total["skip"] += 1
            continue

        rows = df.to_dict("records")
        inserted = 0
        for row in rows:
            cur.execute(SALE_SQL, row)
            inserted += cur.rowcount
        conn.commit()
        print(f"  ✅ {fname}: {inserted}/{len(rows)}행 적재")
        total["sale"] += inserted

    # ── 전세 데이터 적재 ─────────────────────────────────────────────
    print("\n[ 전세 실거래가 적재 ]")
    for fname, htype in JEONSE_FILES:
        path = DATA_DIR / fname
        if not path.exists():
            print(f"  SKIP {fname} — 파일 없음")
            total["skip"] += 1
            continue
        df = parse_jeonse(path, htype)
        if df.empty:
            print(f"  SKIP {fname} — 빈 파일")
            total["skip"] += 1
            continue

        rows = df.to_dict("records")
        inserted = 0
        for row in rows:
            try:
                cur.execute(JEONSE_SQL_SAFE, row)
                inserted += cur.rowcount
            except Exception as e:
                conn.rollback()
                print(f"    행 삽입 오류: {e} | {row}")
        conn.commit()
        print(f"  ✅ {fname}: {inserted}/{len(rows)}행 적재")
        total["jeonse"] += inserted

    cur.close()
    conn.close()

    print(f"\n🏁 완료 — 매매 {total['sale']}행 / 전세 {total['jeonse']}행 적재 / {total['skip']}개 파일 스킵")


if __name__ == "__main__":
    run()
