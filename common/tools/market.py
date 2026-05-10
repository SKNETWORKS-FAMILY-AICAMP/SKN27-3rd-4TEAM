"""Market data analyzer for jeonse deposit and sale-price comparison."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from common.schemas.diagnosis import MarketAnalysis
from common.schemas.shared import RiskFinding

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
JEONSE_CSV = DATA_DIR / "2025_전세_종로구_통합_cleaned.csv"
SALE_FILES = [
    DATA_DIR / "fixed_연립다세대(매매)_실거래가_20260507195717.csv",
    DATA_DIR / "fixed_오피스텔(매매)_실거래가_20260507195801.csv",
]


def analyze_market(fields: dict[str, Any]) -> tuple[MarketAnalysis, list[RiskFinding]]:
    housing_type = fields.get("housing_type")
    dong_name = fields.get("dong_name")
    deposit = _to_number(fields.get("deposit_amount"))
    area = _to_float(fields.get("exclusive_area_m2"))

    analysis = MarketAnalysis(
        housing_type=housing_type,
        dong_name=dong_name,
        input_deposit_amount=int(deposit) if deposit is not None else None,
        input_area_m2=area,
    )
    findings: list[RiskFinding] = []

    if deposit is None:
        findings.append(_finding("MARKET_MISSING_DEPOSIT", "보증금 정보 부족", "MEDIUM", 8, "계약서에서 보증금을 확정하지 못해 시세 기반 위험도를 계산하기 어렵습니다."))
        return analysis, findings

    try:
        jeonse_df = pd.read_csv(JEONSE_CSV)
        sale_df = pd.concat([pd.read_csv(path) for path in SALE_FILES if path.exists()], ignore_index=True)
    except Exception as exc:
        findings.append(_finding("MARKET_DATA_ERROR", "시세 데이터 로딩 실패", "LOW", 5, f"CSV 시세 데이터를 읽지 못했습니다: {exc}"))
        return analysis, findings

    jeonse_comp = _filter_jeonse(jeonse_df, housing_type, dong_name, area)
    sale_comp = _filter_sale(sale_df, housing_type, dong_name, area)

    analysis.comparable_jeonse_count = len(jeonse_comp)
    analysis.comparable_sale_count = len(sale_comp)

    if len(jeonse_comp) > 0:
        deposits = _numeric_series(jeonse_comp["deposit_amount"]).dropna()
        if len(deposits) > 0:
            analysis.median_jeonse_deposit = float(deposits.median())
            analysis.deposit_percentile = float((deposits <= deposit).mean() * 100)

    if len(sale_comp) > 0:
        sale_prices = _numeric_series(sale_comp["deal_amount"]).dropna()
        if len(sale_prices) > 0:
            analysis.median_sale_price = float(sale_prices.median())
            if analysis.median_sale_price > 0:
                analysis.estimated_jeonse_ratio = float(deposit / analysis.median_sale_price * 100)

    analysis.confidence = _confidence(analysis)
    findings.extend(_market_findings(analysis))
    return analysis, findings


def _filter_jeonse(df: pd.DataFrame, housing_type: str | None, dong_name: str | None, area: float | None) -> pd.DataFrame:
    out = df.copy()
    if housing_type and "housing_type" in out:
        out = out[out["housing_type"].astype(str).str.contains(housing_type, na=False)]
    if dong_name and "dong_name" in out:
        same_dong = out[out["dong_name"].astype(str).str.contains(dong_name, na=False)]
        if len(same_dong) >= 5:
            out = same_dong
    if area is not None and "exclusive_area_m2" in out:
        numeric_area = _numeric_series(out["exclusive_area_m2"])
        close_area = out[(numeric_area - area).abs() <= 10]
        if len(close_area) >= 5:
            out = close_area
    return out


def _filter_sale(df: pd.DataFrame, housing_type: str | None, dong_name: str | None, area: float | None) -> pd.DataFrame:
    out = df.copy()
    if housing_type and "housing_type" in out:
        out = out[out["housing_type"].astype(str).str.contains(housing_type, na=False)]
    if dong_name and "sigungu" in out:
        same_dong = out[out["sigungu"].astype(str).str.contains(dong_name, na=False)]
        if len(same_dong) >= 5:
            out = same_dong
    if area is not None and "exclusive_area" in out:
        numeric_area = _numeric_series(out["exclusive_area"])
        close_area = out[(numeric_area - area).abs() <= 10]
        if len(close_area) >= 5:
            out = close_area
    return out


def _market_findings(analysis: MarketAnalysis) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    ratio = analysis.estimated_jeonse_ratio
    if ratio is None:
        findings.append(_finding("MARKET_RATIO_UNKNOWN", "전세가율 산정 불가", "MEDIUM", 10, "비교 가능한 매매 실거래가가 부족해 전세가율을 계산하지 못했습니다.", "실거래가 범위를 넓히거나 등기부/감정가 등 추가 자료를 확인하세요."))
    elif ratio >= 80:
        findings.append(_finding("MARKET_RATIO_HIGH", "전세가율 80% 이상", "HIGH", 25, f"추정 전세가율이 {ratio:.1f}%로 높습니다. 보증금 반환 위험을 보수적으로 봐야 합니다.", "주변 매매가, 보증보험 가능 여부, 선순위 권리를 반드시 확인하세요."))
    elif ratio >= 70:
        findings.append(_finding("MARKET_RATIO_CAUTION", "전세가율 주의 구간", "MEDIUM", 15, f"추정 전세가율이 {ratio:.1f}%입니다. 안전 여유가 크지 않을 수 있습니다."))

    if analysis.deposit_percentile is not None and analysis.deposit_percentile >= 85:
        findings.append(_finding("MARKET_DEPOSIT_HIGH", "주변 전세 대비 보증금 높음", "MEDIUM", 10, f"보증금이 비교 전세 거래의 상위 {analysis.deposit_percentile:.0f}% 수준입니다."))

    if analysis.confidence == "LOW":
        findings.append(_finding("MARKET_LOW_CONFIDENCE", "시세 분석 신뢰도 낮음", "LOW", 5, "동일 유형/면적 비교 데이터가 부족해 시세 판단 신뢰도가 낮습니다."))
    return findings


def _numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(',', '', regex=False).str.strip(), errors='coerce')
def _confidence(analysis: MarketAnalysis) -> str:
    if analysis.comparable_jeonse_count >= 20 and analysis.comparable_sale_count >= 20:
        return "HIGH"
    if analysis.comparable_jeonse_count >= 5 and analysis.comparable_sale_count >= 5:
        return "MEDIUM"
    return "LOW"


def _finding(code: str, title: str, severity: str, score: int, description: str, action: str | None = None) -> RiskFinding:
    return RiskFinding(code=code, title=title, severity=severity, score_delta=score, description=description, required_action=action, source="market_analyzer")


def _to_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    return _to_number(value)




