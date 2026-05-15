"""
데이터 로더 + 2년후 예측 데이터 생성

방식: 동+면적구간별 연평균 상승률 계산 → 2025 기준 2년 적용 → 2027 예측
"""

import os
import pandas as pd
import numpy as np


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


# ── 면적 구간 분류 ───────────────────────────────────────

def area_bucket(area: float) -> str:
    if area < 33:
        return "~33㎡"
    elif area < 66:
        return "33~66㎡"
    elif area < 99:
        return "66~99㎡"
    else:
        return "99㎡~"


# ── CSV 로드 ─────────────────────────────────────────────

def load_all_csv() -> tuple[pd.DataFrame, pd.DataFrame]:
    """전세/매매 CSV 전부 로드 → (전세df, 매매df) 반환"""
    all_files = sorted(os.listdir(DATA_DIR))

    jeonse_dfs = []
    sale_dfs = []

    for f in all_files:
        if not f.endswith(".csv"):
            continue
        path = os.path.join(DATA_DIR, f)
        year = int(f.split("_")[0])
        df = pd.read_csv(path, encoding="utf-8")
        df["year"] = year

        # 건물명 통일
        if "officetel_name" in df.columns:
            df["building_name"] = df["officetel_name"]
            df["housing_type"] = "오피스텔"
        elif "house_name" in df.columns:
            df["building_name"] = df["house_name"]
            df["housing_type"] = "연립다세대"

        if "전세" in f:
            df = df[df["monthly_rent"] == 0]  # 순수 전세만
            jeonse_dfs.append(df)
        elif "매매" in f:
            sale_dfs.append(df)

    jeonse = pd.concat(jeonse_dfs, ignore_index=True)
    sale = pd.concat(sale_dfs, ignore_index=True)

    return jeonse, sale


# ── 연평균 상승률 기반 2년후 예측 ────────────────────────

def generate_predictions(jeonse: pd.DataFrame, sale: pd.DataFrame) -> pd.DataFrame:
    """
    동+면적구간별로:
    1. 연도별 평균 전세금/매매가 계산
    2. 연평균 상승률(CAGR) 계산
    3. 2025 기준 → 2027 예측가 생성
    4. 전세가율 = 예측전세금 / 예측매매가 * 100
    """
    jeonse = jeonse.copy()
    sale = sale.copy()

    jeonse["area_bucket"] = jeonse["exclusive_area_m2"].apply(area_bucket)
    sale["area_bucket"] = sale["exclusive_area_m2"].apply(area_bucket)

    # 동+면적구간+연도별 평균
    j_avg = (jeonse.groupby(["dong_name", "area_bucket", "year"])["deposit_amount"]
             .mean().reset_index())
    j_avg.columns = ["dong_name", "area_bucket", "year", "avg_deposit"]

    s_avg = (sale.groupby(["dong_name", "area_bucket", "year"])
             .agg(avg_sale=("deal_amount", "mean")).reset_index())

    # 동+면적구간별 CAGR 계산
    predictions = []

    for (dong, area), group in j_avg.groupby(["dong_name", "area_bucket"]):
        group = group.sort_values("year")
        if len(group) < 2:
            continue

        first_year = group["year"].min()
        last_year = group["year"].max()
        first_val = group[group["year"] == first_year]["avg_deposit"].values[0]
        last_val = group[group["year"] == last_year]["avg_deposit"].values[0]

        n_years = last_year - first_year
        if n_years == 0 or first_val <= 0:
            cagr_jeonse = 0.0
        else:
            cagr_jeonse = (last_val / first_val) ** (1 / n_years) - 1

        # 2025 기준값 (없으면 최신 데이터)
        base_jeonse = group[group["year"] == 2025]["avg_deposit"].values
        if len(base_jeonse) == 0:
            base_jeonse = last_val
        else:
            base_jeonse = base_jeonse[0]

        predicted_deposit_2027 = int(base_jeonse * (1 + cagr_jeonse) ** 2)

        # 매매 예측
        s_group = s_avg[(s_avg["dong_name"] == dong) & (s_avg["area_bucket"] == area)]
        s_group = s_group.sort_values("year")

        if len(s_group) >= 2:
            s_first = s_group["avg_sale"].iloc[0]
            s_last = s_group["avg_sale"].iloc[-1]
            s_n = s_group["year"].iloc[-1] - s_group["year"].iloc[0]
            cagr_sale = (s_last / s_first) ** (1 / s_n) - 1 if s_n > 0 and s_first > 0 else 0.0

            base_sale = s_group[s_group["year"] == 2025]["avg_sale"].values
            if len(base_sale) == 0:
                base_sale = s_last
            else:
                base_sale = base_sale[0]

            predicted_sale_2027 = int(base_sale * (1 + cagr_sale) ** 2)
        else:
            predicted_sale_2027 = None
            cagr_sale = None

        # 전세가율
        if predicted_sale_2027 and predicted_sale_2027 > 0:
            jeonse_ratio = round(predicted_deposit_2027 / predicted_sale_2027 * 100, 1)
        else:
            jeonse_ratio = None

        # 위험도
        if jeonse_ratio is None:
            risk = "미상"
        elif jeonse_ratio >= 80:
            risk = "위험"
        elif jeonse_ratio >= 70:
            risk = "주의"
        else:
            risk = "안전"

        predictions.append({
            "dong_name": dong,
            "area_bucket": area,
            "base_deposit_2025": int(base_jeonse),
            "predicted_deposit_2027": predicted_deposit_2027,
            "cagr_jeonse": round(cagr_jeonse * 100, 2),
            "predicted_sale_2027": predicted_sale_2027,
            "cagr_sale": round(cagr_sale * 100, 2) if cagr_sale else None,
            "jeonse_ratio_2027": jeonse_ratio,
            "risk_level": risk,
        })

    return pd.DataFrame(predictions)


# ── 특정 주소의 예측 데이터 조회 ──────────────────────────

_predictions_cache = None

def get_predictions() -> pd.DataFrame:
    global _predictions_cache
    if _predictions_cache is None:
        jeonse, sale = load_all_csv()
        _predictions_cache = generate_predictions(jeonse, sale)
    return _predictions_cache


def lookup_prediction(dong_name: str, area_m2: float | None = None) -> dict | None:
    """동 이름 + 면적으로 2027 예측 데이터 조회"""
    preds = get_predictions()

    # 동 이름 매칭 (부분 일치)
    matched = preds[preds["dong_name"].str.contains(dong_name, na=False)]
    if matched.empty:
        return None

    # 면적 구간 매칭
    if area_m2:
        bucket = area_bucket(area_m2)
        exact = matched[matched["area_bucket"] == bucket]
        if not exact.empty:
            return exact.iloc[0].to_dict()

    # 면적 없으면 동 평균
    return matched.iloc[0].to_dict()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    print("=== 데이터 로드 ===")
    jeonse, sale = load_all_csv()
    print(f"전세: {len(jeonse):,}건 / 매매: {len(sale):,}건")

    print("\n=== 2027 예측 생성 ===")
    preds = generate_predictions(jeonse, sale)
    print(f"예측 데이터: {len(preds)}개 구간")
    print(f"\n위험도 분포:")
    print(preds["risk_level"].value_counts().to_string())
    print(f"\n샘플 (상위 5개):")
    print(preds.head().to_string())
