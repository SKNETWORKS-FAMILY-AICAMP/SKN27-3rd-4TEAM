"""Deep Learning → RAG 브리지.

deep_learning/risk_inference.analyze() 결과를 RAG ContextPack으로 변환하여
진단 파이프라인의 context_packs["dl_market"]에 주입합니다.

연결 구조:
    market_analysis_node
        └─▶ dl_market_bridge.run_dl_analysis(contract_fields)
                └─▶ deep_learning.risk_inference.analyze()
                        ├─ DB: jeonse_transactions, sale_transactions
                        ├─ LSTM: 24개월 가격 예측
                        └─ score_risk: risk_score, reasons, advice
        └─▶ ContextPack("dl_market", ...) → context_packs["dl_market"]
        └─▶ list[RiskFinding] → market_findings에 추가
"""
from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any

from common.schemas.shared import ContextPack, RetrievalQuality, RetrievedContext, RiskFinding

# deep_learning 패키지 경로를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DL_DIR = _PROJECT_ROOT / "deep_learning"
if str(_DL_DIR) not in sys.path:
    sys.path.insert(0, str(_DL_DIR))


# ── DL 분석 실행 ────────────────────────────────────────────────────────

def run_dl_analysis(contract_fields: dict[str, Any]) -> tuple[ContextPack, list[RiskFinding]]:
    """계약서 필드를 딥러닝 모델에 전달하고 결과를 ContextPack + RiskFinding으로 반환.

    Args:
        contract_fields: DiagnosisState의 contract_fields (주소, 보증금, 면적 등)

    Returns:
        (ContextPack, list[RiskFinding]) — RAG context와 위험 발견 목록
    """
    dl_result = _call_dl_module(contract_fields)

    if dl_result is None:
        # DL 모듈 호출 실패 → 빈 ContextPack 반환
        return _empty_pack("dl_market"), []

    context_pack = _to_context_pack(dl_result)
    risk_findings = _to_risk_findings(dl_result)
    return context_pack, risk_findings


# ── DL 모듈 호출 ────────────────────────────────────────────────────────

def _call_dl_module(fields: dict[str, Any]) -> dict[str, Any] | None:
    """deep_learning.risk_inference.analyze() 호출. 실패 시 None 반환."""
    try:
        from risk_inference import analyze  # deep_learning/ 경로

        args = _build_dl_args(fields)
        if args is None:
            return None

        result = analyze(args)
        return result

    except ImportError as e:
        print(f"[DL Bridge] deep_learning 모듈 임포트 실패: {e}")
        return None
    except Exception as e:
        print(f"[DL Bridge] DL 분석 오류: {e}")
        return None


def _build_dl_args(fields: dict[str, Any]):
    """contract_fields에서 DL analyze()에 필요한 argparse.Namespace 객체 생성."""
    import argparse

    deposit = _to_float(fields.get("deposit_amount"))
    area_m2 = _to_float(fields.get("exclusive_area_m2"))

    # 필수 값 없으면 DL 분석 불가
    if deposit is None or area_m2 is None or area_m2 <= 0:
        print(f"[DL Bridge] 필수 입력 부족 (deposit={deposit}, area_m2={area_m2}) → DL 분석 스킵")
        return None

    address = str(fields.get("address") or "")
    dong = _extract_dong(address) or fields.get("dong_name") or "청운동"
    housing_type = _normalize_housing_type(fields.get("housing_type")) or "연립다세대"

    args = argparse.Namespace(
        sido="서울특별시",
        sigungu="종로구",
        dong=dong,
        property_name=str(fields.get("property_name") or ""),
        housing_type=housing_type,
        area_m2=float(area_m2),
        floor=float(fields.get("floor") or 0),
        deposit=float(deposit),
    )
    return args


# ── ContextPack 변환 ────────────────────────────────────────────────────

def _to_context_pack(dl_result: dict[str, Any]) -> ContextPack:
    """DL 분석 결과를 RAG ContextPack으로 변환."""
    market = dl_result.get("market_analysis", {})
    risk = dl_result.get("risk", {})
    inp = dl_result.get("input", {})
    building = dl_result.get("building_analysis", {})
    forecast = market.get("forecast_24m") or {}

    # ── 핵심 시세 컨텍스트 문서 ───────────────────────────────────────
    market_text = _format_market_context(inp, market, building, forecast)
    # ── 위험 판단 근거 문서 ──────────────────────────────────────────
    risk_text = _format_risk_context(risk)

    contexts: list[RetrievedContext] = []

    if market_text:
        contexts.append(RetrievedContext(
            source_id="dl-market-analysis",
            title="딥러닝 시세 분석 (LSTM + 실거래가)",
            doc_type="dl_market",
            text=market_text,
            score=0.92,   # DL 모델 기반 — 높은 신뢰도
            metadata={
                "provider": "deep_learning",
                "model": "risk_inference+LSTM",
                "dong": inp.get("dong"),
                "housing_type": inp.get("housing_type"),
                "area_bucket": inp.get("area_bucket"),
                "market_phase": market.get("market_phase"),
            },
        ))

    if risk_text:
        contexts.append(RetrievedContext(
            source_id="dl-risk-assessment",
            title="딥러닝 위험도 평가 결과",
            doc_type="dl_risk",
            text=risk_text,
            score=0.95,
            metadata={
                "provider": "deep_learning",
                "risk_score": risk.get("risk_score"),
                "risk_level": risk.get("risk_level"),
            },
        ))

    sufficient = len(contexts) > 0 and risk.get("risk_score") is not None
    quality = RetrievalQuality(
        sufficient=sufficient,
        score=0.93 if sufficient else 0.0,
        reason="딥러닝 모델(LSTM + 통계 기반 시세 분석) 결과" if sufficient else "DL 분석 데이터 부족",
    )

    return ContextPack(
        task_type="dl_market",
        query=f"전세 시세 위험 분석 {inp.get('dong','')} {inp.get('housing_type','')}",
        contexts=contexts,
        quality=quality,
    )


def _format_market_context(inp: dict, market: dict, building: dict, forecast: dict) -> str:
    lines = ["[딥러닝 시세 분석 결과]"]

    dong = inp.get("dong", "미상")
    h_type = inp.get("housing_type", "미상")
    area_bucket = inp.get("area_bucket", "미상")
    deposit = inp.get("deposit_amount_manwon")
    per_pyeong = inp.get("input_deposit_per_pyeong")

    lines.append(f"분석 대상: {dong} / {h_type} / 면적구간 {area_bucket}")
    if deposit:
        lines.append(f"입력 보증금: {deposit:,}만원 (평당 {per_pyeong:,.0f}만원)" if per_pyeong else f"입력 보증금: {deposit:,}만원")

    # 지역 시세 비교
    region_median = market.get("recent_region_median_deposit_per_pyeong")
    gap_pct = market.get("region_deposit_gap_pct")
    if region_median:
        lines.append(f"지역 최근 3개월 전세 중위 평당가: {region_median:,.0f}만원")
    if gap_pct is not None:
        direction = "높음" if gap_pct > 0 else "낮음"
        lines.append(f"입력 보증금과 지역 시세 차이: {gap_pct:+.1f}% ({direction})")

    # 전세가율
    jeonse_ratio = market.get("jeonse_ratio")
    sale_per_pyeong = market.get("sale_per_pyeong")
    if jeonse_ratio and sale_per_pyeong:
        lines.append(f"매매 평당가 대비 전세 비율(전세가율): {jeonse_ratio:.1f}% (매매 평당 {sale_per_pyeong:,.0f}만원)")

    # 건물 단위 비교
    building_gap = building.get("building_gap_pct")
    building_median = building.get("recent_building_median_per_pyeong")
    if building_gap is not None and building_median:
        lines.append(f"같은 건물 평균 대비 보증금 차이: {building_gap:+.1f}% (건물 평균 {building_median:,.0f}만원/평)")

    # LSTM 예측
    if forecast:
        current = forecast.get("current_per_pyeong")
        predicted = forecast.get("predicted_24m_per_pyeong")
        change = forecast.get("change_rate")
        trend = forecast.get("trend", "보합")
        if current and predicted:
            lines.append(f"LSTM 24개월 예측: 현재 {current:,.0f}만원/평 → {predicted:,.0f}만원/평 ({change:+.1f}%, {trend})")
        lines.append(f"시장 국면: {market.get('market_phase', '예측 부족')}")

    return "\n".join(lines)


def _format_risk_context(risk: dict) -> str:
    score = risk.get("risk_score")
    level = risk.get("risk_level", "미평가")
    reasons = risk.get("reasons", [])
    advice = risk.get("advice", [])

    if score is None:
        return ""

    lines = [
        f"[딥러닝 위험도 평가]",
        f"위험 점수: {score}점 / 위험 등급: {level}",
    ]
    if reasons:
        lines.append("위험 근거:")
        for r in reasons:
            lines.append(f"  - {r}")
    if advice:
        lines.append("대응 조언:")
        for a in advice:
            lines.append(f"  - {a}")
    return "\n".join(lines)


# ── RiskFinding 변환 ────────────────────────────────────────────────────

def _to_risk_findings(dl_result: dict[str, Any]) -> list[RiskFinding]:
    """DL 위험 근거를 RiskFinding 목록으로 변환."""
    risk = dl_result.get("risk", {})
    market = dl_result.get("market_analysis", {})
    score = risk.get("risk_score", 0)
    level = risk.get("risk_level", "보통")
    reasons = risk.get("reasons", [])
    findings: list[RiskFinding] = []

    # 전세가율 위험
    jeonse_ratio = market.get("jeonse_ratio")
    if jeonse_ratio is not None:
        if jeonse_ratio >= 90:
            findings.append(RiskFinding(
                code="DL_JEONSE_RATIO_CRITICAL",
                title=f"딥러닝: 전세가율 위험 ({jeonse_ratio:.1f}%)",
                severity="CRITICAL",
                score_delta=25,
                description=f"딥러닝 분석 결과 전세가율이 {jeonse_ratio:.1f}%로 깡통전세 위험 구간입니다.",
                required_action="반환보증 가입 가능 여부와 선순위 채권을 즉시 확인하세요.",
                source="dl_market_bridge",
            ))
        elif jeonse_ratio >= 80:
            findings.append(RiskFinding(
                code="DL_JEONSE_RATIO_HIGH",
                title=f"딥러닝: 전세가율 주의 ({jeonse_ratio:.1f}%)",
                severity="HIGH",
                score_delta=15,
                description=f"전세가율 {jeonse_ratio:.1f}%로 보증금 회수 여력이 낮습니다.",
                source="dl_market_bridge",
            ))

    # 지역 시세 대비 과고평가
    gap_pct = market.get("region_deposit_gap_pct")
    if gap_pct is not None and gap_pct >= 25:
        findings.append(RiskFinding(
            code="DL_DEPOSIT_OVERPRICED",
            title=f"딥러닝: 보증금 지역 시세 초과 ({gap_pct:+.1f}%)",
            severity="HIGH",
            score_delta=20,
            description=f"입력 보증금이 지역 최근 시세보다 {gap_pct:.1f}% 높습니다.",
            required_action="등기부 권리관계, 반환보증 가입 가능 여부를 확인하세요.",
            source="dl_market_bridge",
        ))

    # LSTM 하락 예측
    forecast = market.get("forecast_24m") or {}
    change_rate = forecast.get("change_rate")
    if change_rate is not None and change_rate <= -10:
        findings.append(RiskFinding(
            code="DL_LSTM_PRICE_DROP",
            title=f"딥러닝: LSTM 24개월 가격 하락 예측 ({change_rate:.1f}%)",
            severity="HIGH",
            score_delta=20,
            description=f"LSTM 모델이 계약 만기 시점의 시세가 {abs(change_rate):.1f}% 하락할 것으로 예측합니다.",
            required_action="계약 만기 후 보증금 회수 가능성을 보수적으로 검토하세요.",
            source="dl_market_bridge",
        ))

    # 종합 위험도 (위험/주의 레벨일 때만 추가)
    if level in {"위험", "주의"} and reasons:
        severity = "HIGH" if level == "위험" else "MEDIUM"
        delta = 15 if level == "위험" else 8
        findings.append(RiskFinding(
            code="DL_OVERALL_RISK",
            title=f"딥러닝 종합 위험도: {level} ({score}점)",
            severity=severity,
            score_delta=delta,
            description="딥러닝 모델 종합 평가: " + " / ".join(reasons[:2]),
            source="dl_market_bridge",
        ))

    return findings


# ── 유틸 ────────────────────────────────────────────────────────────────

def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _extract_dong(address: str) -> str | None:
    import re
    m = re.search(r"([가-힣0-9]+동)", address)
    return m.group(1) if m else None


def _normalize_housing_type(value: Any) -> str | None:
    if not value:
        return None
    v = str(value)
    if "오피스텔" in v:
        return "오피스텔"
    if "연립" in v or "다세대" in v:
        return "연립다세대"
    if "단독" in v or "다가구" in v:
        return "단독다가구"
    return v


def _empty_pack(task_type: str) -> ContextPack:
    return ContextPack(
        task_type=task_type,
        query="",
        contexts=[],
        quality=RetrievalQuality(sufficient=False, score=0.0, reason="DL 분석 불가 (입력 부족 또는 모듈 오류)"),
    )
