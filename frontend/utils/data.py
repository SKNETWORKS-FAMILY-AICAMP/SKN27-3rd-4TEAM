"""종로구 실거래가 CSV 로더 + 인근 시세 계산."""

from pathlib import Path
import pandas as pd
import streamlit as st


DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "jongno_jeonse_2025.csv"


@st.cache_data(show_spinner=False)
def load_jongno() -> pd.DataFrame:
    """종로구 2025 전세 실거래가."""
    if not DATA_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(DATA_PATH)
    # 보증금은 만원 단위로 들어옴
    df["deposit_won"] = df["deposit_amount"].astype(float) * 10_000
    df["pyeong"] = df["exclusive_area_m2"].astype(float) / 3.3058
    df["price_per_pyeong"] = df["deposit_won"] / df["pyeong"]
    return df


@st.cache_data(show_spinner=False)
def dong_stats(dong: str) -> dict:
    """특정 동의 전세 통계."""
    df = load_jongno()
    if df.empty:
        return {}
    sub = df[df["dong_name"] == dong]
    if sub.empty:
        return {}
    return {
        "count": len(sub),
        "median_deposit": int(sub["deposit_won"].median()),
        "median_per_pyeong": int(sub["price_per_pyeong"].median()),
        "p25": int(sub["deposit_won"].quantile(0.25)),
        "p75": int(sub["deposit_won"].quantile(0.75)),
        "recent": sub.sort_values("contract_date", ascending=False).head(8),
    }


def won_to_eok(won: int | float) -> str:
    """원 → '2.5억' 형식."""
    eok = won / 100_000_000
    if eok >= 1:
        return f"₩{eok:.2f}억"
    return f"₩{int(won / 10_000):,}만"


def dong_list() -> list[str]:
    df = load_jongno()
    if df.empty:
        return []
    return sorted(df["dong_name"].dropna().unique().tolist())
