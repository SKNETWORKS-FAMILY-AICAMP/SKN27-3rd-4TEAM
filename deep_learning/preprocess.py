from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd


PYEONG_M2 = 3.3058
_CURRENT_FILE = Path(__file__).resolve()
# preprocess.py 위치: <project_root>/deep_learning/preprocess.py
# parents[0] = deep_learning/, parents[1] = <project_root>
PROJECT_ROOT = _CURRENT_FILE.parents[1]
ARTIFACT_ROOT = Path(__file__).resolve().parent / "artifacts"
PROCESSED_DIR = ARTIFACT_ROOT / "processed"


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_db() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    import psycopg2

    _load_env()
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "jeonse_risk"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )
    try:
        jeonse = pd.read_sql_query("select * from jeonse_transactions", conn)
        sale = pd.read_sql_query("select * from sale_transactions", conn)
    finally:
        conn.close()
    return jeonse, sale, {"jeonse_transactions": len(jeonse), "sale_transactions": len(sale)}


def read_csv(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    jeonse_parts, sale_parts, counts = [], [], {}
    for path in sorted(data_dir.glob("*.csv")):
        df = pd.read_csv(path, encoding="utf-8-sig")
        counts[path.name] = len(df)
        name = path.name
        housing_type = "오피스텔" if "오피스텔" in name else "연립다세대" if "연립" in name else "기타"
        if "전세" in name:
            df = df.rename(columns={"house_name": "property_name", "officetel_name": "property_name"})
            df["housing_type"] = housing_type
            jeonse_parts.append(df)
        elif "매매" in name:
            df = df.rename(
                columns={
                    "house_name": "bldg_nm",
                    "officetel_name": "bldg_nm",
                    "exclusive_area_m2": "exclusive_area",
                }
            )
            df["housing_type"] = housing_type
            sale_parts.append(df)
    return (
        pd.concat(jeonse_parts, ignore_index=True) if jeonse_parts else pd.DataFrame(),
        pd.concat(sale_parts, ignore_index=True) if sale_parts else pd.DataFrame(),
        counts,
    )


def area_bucket(area_m2: float) -> str:
    if pd.isna(area_m2):
        return "미상"
    if area_m2 < 20:
        return "20㎡ 미만"
    if area_m2 < 33:
        return "20~33㎡"
    if area_m2 < 66:
        return "33~66㎡"
    if area_m2 < 99:
        return "66~99㎡"
    return "99㎡ 이상"


def floor_bucket(floor: float) -> str:
    if pd.isna(floor):
        return "층 미상"
    if floor < 1:
        return "지하/반지하"
    if floor <= 3:
        return "저층"
    if floor <= 10:
        return "중층"
    return "고층"


def normalize_jeonse(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["sido"] = out.get("sido", "서울특별시")
    out["sigungu"] = out.get("sigungu", out.get("sgg_name", "종로구"))
    out["dong_name"] = out.get("dong_name", "").fillna("").astype(str).str.strip()
    out["property_name"] = out.get("property_name", "").fillna("").astype(str).str.strip()
    out["jibun"] = out.get("jibun", "").fillna("").astype(str).str.strip()
    out["housing_type"] = out.get("housing_type", "기타").fillna("기타")
    out["exclusive_area_m2"] = pd.to_numeric(out.get("exclusive_area_m2", 0), errors="coerce")
    out["deposit_amount"] = pd.to_numeric(out.get("deposit_amount", 0), errors="coerce")
    out["floor"] = pd.to_numeric(out.get("floor", 0), errors="coerce").fillna(0)
    out["build_year"] = pd.to_numeric(out.get("build_year", np.nan), errors="coerce")
    out["contract_date"] = pd.to_datetime(out.get("contract_date", pd.NaT), errors="coerce")
    out = out[(out["exclusive_area_m2"] > 0) & (out["deposit_amount"] > 0)].copy()
    out["contract_month"] = out["contract_date"].dt.to_period("M").astype(str)
    out["area_pyeong"] = out["exclusive_area_m2"] / PYEONG_M2
    out["deposit_per_pyeong"] = out["deposit_amount"] / out["area_pyeong"]
    out["area_bucket"] = out["exclusive_area_m2"].apply(area_bucket)
    out["floor_bucket"] = out["floor"].apply(floor_bucket)
    return out.dropna(subset=["contract_date", "deposit_per_pyeong"])


def normalize_sale(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "deal_amount" not in df.columns:
        return pd.DataFrame()
    out = df.copy()
    out["sido"] = out.get("sido", "서울특별시")
    out["sigungu"] = out.get("sigungu", out.get("sgg_name", "종로구"))
    sigungu_text = out["sigungu"].fillna("").astype(str).str.strip()
    parts = sigungu_text.str.split()
    out["sido"] = np.where(sigungu_text.str.startswith("서울특별시"), "서울특별시", out["sido"])
    out["sigungu"] = np.where(
        sigungu_text.str.startswith("서울특별시") & (parts.str.len() >= 2),
        parts.str[1],
        sigungu_text.replace("", "종로구"),
    )
    out["housing_type"] = out.get("housing_type", "기타").fillna("기타")
    out["exclusive_area"] = pd.to_numeric(out.get("exclusive_area", 0), errors="coerce")
    out["deal_amount"] = pd.to_numeric(out.get("deal_amount", 0), errors="coerce")
    if "deal_year_month" in out.columns:
        deal_ym = pd.to_numeric(out["deal_year_month"], errors="coerce").astype("Int64").astype(str)
        deal_ym = deal_ym.replace("<NA>", "")
        out["deal_month"] = pd.to_datetime(deal_ym, format="%Y%m", errors="coerce")
    else:
        out["deal_month"] = pd.to_datetime(out.get("deal_date", pd.NaT), errors="coerce")
    out = out[(out["exclusive_area"] > 0) & (out["deal_amount"] > 0)].copy()
    out["contract_month"] = out["deal_month"].dt.to_period("M").astype(str)
    out["area_pyeong"] = out["exclusive_area"] / PYEONG_M2
    out["sale_per_pyeong"] = out["deal_amount"] / out["area_pyeong"]
    out["area_bucket"] = out["exclusive_area"].apply(area_bucket)
    return out.dropna(subset=["deal_month", "sale_per_pyeong"])


def monthly_stats(df: pd.DataFrame, value_col: str, output_col: str, include_dong: bool) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    group_cols = ["sido", "sigungu", "housing_type", "area_bucket"]
    if include_dong:
        group_cols.insert(2, "dong_name")
    rows = []
    for keys, group in df.groupby(group_cols + ["contract_month"], dropna=False):
        skew = group[value_col].dropna().skew()
        method = "median" if pd.notna(skew) and abs(skew) >= 1 else "mean"
        value = group[value_col].median() if method == "median" else group[value_col].mean()
        row = dict(zip(group_cols + ["contract_month"], keys, strict=False))
        row.update(
            {
                output_col: round(float(value), 2),
                "count": int(len(group)),
                "std": round(float(group[value_col].std() or 0), 2),
                "q25": round(float(group[value_col].quantile(0.25)), 2),
                "q75": round(float(group[value_col].quantile(0.75)), 2),
                "agg_method": method,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def building_monthly_stats(jeonse: pd.DataFrame) -> pd.DataFrame:
    if jeonse.empty:
        return pd.DataFrame()
    group_cols = [
        "sido",
        "sigungu",
        "dong_name",
        "housing_type",
        "property_name",
        "area_bucket",
        "floor_bucket",
        "contract_month",
    ]
    rows = []
    for keys, group in jeonse.groupby(group_cols, dropna=False):
        row = dict(zip(group_cols, keys, strict=False))
        row.update(
            {
                "building_median_deposit": round(float(group["deposit_amount"].median()), 2),
                "building_mean_deposit": round(float(group["deposit_amount"].mean()), 2),
                "building_median_deposit_per_pyeong": round(float(group["deposit_per_pyeong"].median()), 2),
                "building_mean_deposit_per_pyeong": round(float(group["deposit_per_pyeong"].mean()), 2),
                "building_min_deposit_per_pyeong": round(float(group["deposit_per_pyeong"].min()), 2),
                "building_max_deposit_per_pyeong": round(float(group["deposit_per_pyeong"].max()), 2),
                "building_avg_floor": round(float(group["floor"].mean()), 2),
                "building_avg_area_m2": round(float(group["exclusive_area_m2"].mean()), 2),
                "building_count": int(len(group)),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def label_anomalies(jeonse: pd.DataFrame, jeonse_monthly: pd.DataFrame, sale_monthly: pd.DataFrame) -> pd.DataFrame:
    if jeonse.empty or jeonse_monthly.empty:
        return pd.DataFrame()
    stats = jeonse_monthly.rename(columns={"median_deposit_per_pyeong": "region_price"})
    labeled = jeonse.merge(
        stats[["sido", "sigungu", "dong_name", "housing_type", "area_bucket", "contract_month", "region_price", "std", "q25", "q75"]],
        on=["sido", "sigungu", "dong_name", "housing_type", "area_bucket", "contract_month"],
        how="left",
    )
    if not sale_monthly.empty:
        sale_ref = sale_monthly.rename(columns={"median_sale_per_pyeong": "sale_price"})
        labeled = labeled.merge(
            sale_ref[["sido", "sigungu", "housing_type", "area_bucket", "contract_month", "sale_price"]],
            on=["sido", "sigungu", "housing_type", "area_bucket", "contract_month"],
            how="left",
        )
    else:
        labeled["sale_price"] = np.nan
    labeled["z_score"] = ((labeled["deposit_per_pyeong"] - labeled["region_price"]) / labeled["std"].replace(0, np.nan)).fillna(0)
    labeled["jeonse_ratio"] = labeled["deposit_per_pyeong"] / labeled["sale_price"].replace(0, np.nan) * 100
    labeled["is_price_anomaly"] = (labeled["z_score"].abs() >= 2).astype(int)
    labeled["is_ratio_anomaly"] = ((labeled["jeonse_ratio"] >= 90) | (labeled["jeonse_ratio"] <= 30)).fillna(False).astype(int)
    labeled["is_anomaly"] = ((labeled["is_price_anomaly"] == 1) | (labeled["is_ratio_anomaly"] == 1)).astype(int)
    return labeled


def run(source: str = "db", data_dir: Path | None = None, output_dir: Path = PROCESSED_DIR) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    if source == "csv":
        jeonse_raw, sale_raw, source_counts = read_csv(data_dir or PROJECT_ROOT / "data")
        source_counts = {"csv_files": source_counts}
    else:
        jeonse_raw, sale_raw, source_counts = read_db()
    jeonse = normalize_jeonse(jeonse_raw)
    sale = normalize_sale(sale_raw)
    jeonse_monthly = monthly_stats(jeonse, "deposit_per_pyeong", "median_deposit_per_pyeong", include_dong=True)
    sale_monthly = monthly_stats(sale, "sale_per_pyeong", "median_sale_per_pyeong", include_dong=False)
    jeonse_building_monthly = building_monthly_stats(jeonse)
    labeled = label_anomalies(jeonse, jeonse_monthly, sale_monthly)
    jeonse_monthly.to_csv(output_dir / "jeonse_monthly.csv", index=False, encoding="utf-8-sig")
    sale_monthly.to_csv(output_dir / "sale_monthly.csv", index=False, encoding="utf-8-sig")
    jeonse_building_monthly.to_csv(output_dir / "jeonse_building_monthly.csv", index=False, encoding="utf-8-sig")
    labeled.to_csv(output_dir / "jeonse_labeled.csv", index=False, encoding="utf-8-sig")
    summary = {
        "source": source,
        "source_counts": source_counts,
        "processed_counts": {
            "jeonse_rows": int(len(jeonse)),
            "sale_rows": int(len(sale)),
            "jeonse_monthly_rows": int(len(jeonse_monthly)),
            "sale_monthly_rows": int(len(sale_monthly)),
            "jeonse_building_monthly_rows": int(len(jeonse_building_monthly)),
            "labeled_rows": int(len(labeled)),
        },
    }
    (output_dir / "load_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["db", "csv"], default="db")
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.data_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
