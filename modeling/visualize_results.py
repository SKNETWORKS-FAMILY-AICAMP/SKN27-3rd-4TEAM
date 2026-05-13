"""
깡통전세 예측 모델 — 결과 및 평가지표 시각화

실행:
    python modeling/visualize_results.py
    python modeling/visualize_results.py --output-dir modeling/artifacts/can_jeonse/plots

출력:
    modeling/artifacts/can_jeonse/plots/
        01_model_metrics.html       # 모델 평가지표 (AUC·F1·Recall·Precision·MAPE)
        02_confusion_matrices.html  # 호라이즌별 혼동행렬
        03_price_trend.html         # 매매가·전세가 월별 추이
        04_jeonse_ratio_trend.html  # 전세가율 월별 추이
        05_risk_forecast_24m.html   # 24개월 위험 예측 결과
        06_risk_by_dong.html        # 동별 위험도 분포
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "modeling" / "artifacts" / "can_jeonse"

HORIZON_LABELS = {1: "1개월", 3: "3개월", 6: "6개월", 12: "12개월", 24: "24개월"}
RISK_COLORS = {
    "안전":                  "#2ECC71",
    "주의":                  "#F1C40F",
    "위험":                  "#E67E22",
    "고위험":                "#E74C3C",
    "깡통 가능성 매우 높음":  "#8E44AD",
}
PROPERTY_COLORS = {"villa": "#3498DB", "officetel": "#E74C3C"}
PROPERTY_KO = {"villa": "연립다세대", "officetel": "오피스텔"}


# ─────────────────────────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────────────────────────
def load_artifacts(artifact_dir: Path) -> tuple[list[dict], pd.DataFrame, pd.DataFrame]:
    metrics = json.loads((artifact_dir / "metrics.json").read_text(encoding="utf-8"))
    panel   = pd.read_csv(artifact_dir / "monthly_panel.csv", parse_dates=["month"])
    risk    = pd.read_csv(artifact_dir / "can_jeonse_risk_24m.csv")
    return metrics, panel, risk


# ─────────────────────────────────────────────────────────────
# 01. 모델 평가지표 (AUC·F1·Recall·Precision·MAPE)
# ─────────────────────────────────────────────────────────────
def fig_model_metrics(metrics: list[dict]) -> go.Figure:
    df = pd.DataFrame(metrics)
    df["horizon_label"] = df["horizon_months"].map(HORIZON_LABELS)
    df["mape_pct"] = df["future_price_mape"] * 100

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("분류 성능 (위험 판별)", "회귀 성능 (가격 예측 오차)"),
        horizontal_spacing=0.12,
    )

    # ── 분류 지표 ──
    for metric, name, color, dash in [
        ("roc_auc",   "ROC-AUC",   "#2980B9", "solid"),
        ("pr_auc",    "PR-AUC",    "#27AE60", "dash"),
        ("f1_score",  "F1",        "#E67E22", "dot"),
        ("recall",    "Recall",    "#9B59B6", "dashdot"),
        ("precision", "Precision", "#E74C3C", "longdash"),
    ]:
        fig.add_trace(
            go.Scatter(
                x=df["horizon_label"], y=df[metric],
                name=name, mode="lines+markers",
                line=dict(color=color, dash=dash, width=2),
                marker=dict(size=8),
                hovertemplate=f"{name}: %{{y:.3f}}<extra></extra>",
            ),
            row=1, col=1,
        )

    # ── MAPE 바 차트 ──
    fig.add_trace(
        go.Bar(
            x=df["horizon_label"], y=df["mape_pct"],
            name="MAPE (%)", marker_color="#3498DB",
            text=df["mape_pct"].round(1).astype(str) + "%",
            textposition="outside",
            hovertemplate="MAPE: %{y:.1f}%<extra></extra>",
        ),
        row=1, col=2,
    )

    fig.update_yaxes(range=[0, 1.05], title_text="Score", row=1, col=1)
    fig.update_yaxes(title_text="MAPE (%)", row=1, col=2)
    fig.update_xaxes(title_text="예측 호라이즌", row=1, col=1)
    fig.update_xaxes(title_text="예측 호라이즌", row=1, col=2)
    fig.update_layout(
        title="모델 평가지표 — 호라이즌별 비교",
        height=480,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25),
        template="plotly_white",
    )
    return fig


# ─────────────────────────────────────────────────────────────
# 02. 호라이즌별 혼동행렬
# ─────────────────────────────────────────────────────────────
def fig_confusion_matrices(metrics: list[dict]) -> go.Figure:
    horizons = [m["horizon_months"] for m in metrics]
    fig = make_subplots(
        rows=1, cols=len(horizons),
        subplot_titles=[f"{HORIZON_LABELS[h]} 후" for h in horizons],
        horizontal_spacing=0.06,
    )

    for col_idx, m in enumerate(metrics, start=1):
        tn, fp = m["confusion_tn"], m["confusion_fp"]
        fn, tp = m["confusion_fn"], m["confusion_tp"]
        matrix = np.array([[tn, fp], [fn, tp]])
        labels = [["TN", "FP"], ["FN", "TP"]]
        text   = [[f"{v}<br>({v / matrix.sum() * 100:.1f}%)" for v in row] for row in matrix]

        fig.add_trace(
            go.Heatmap(
                z=matrix,
                x=["예측: 안전", "예측: 위험"],
                y=["실제: 안전", "실제: 위험"],
                text=text,
                texttemplate="%{text}",
                colorscale=[[0, "#EBF5FB"], [1, "#1A5276"]],
                showscale=(col_idx == len(horizons)),
                hovertemplate="%{y} / %{x}<br>건수: %{z}<extra></extra>",
            ),
            row=1, col=col_idx,
        )

    fig.update_layout(
        title="호라이즌별 혼동행렬 (위험 기준: 전세가율 ≥ 80%)",
        height=360,
        template="plotly_white",
    )
    return fig


# ─────────────────────────────────────────────────────────────
# 03. 매매가·전세가 월별 추이
# ─────────────────────────────────────────────────────────────
def fig_price_trend(panel: pd.DataFrame) -> go.Figure:
    agg = (
        panel.groupby(["month", "property_type"], observed=True)
        .agg(
            sale_per_pyeong=("sale_per_pyeong", "mean"),
            jeonse_per_pyeong=("jeonse_per_pyeong", "mean"),
        )
        .reset_index()
    )

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("연립다세대", "오피스텔"),
        shared_yaxes=True,
        horizontal_spacing=0.08,
    )

    for col_idx, prop in enumerate(["villa", "officetel"], start=1):
        sub = agg[agg["property_type"] == prop].sort_values("month")
        color = PROPERTY_COLORS[prop]

        fig.add_trace(
            go.Scatter(
                x=sub["month"], y=sub["sale_per_pyeong"],
                name=f"매매 ({PROPERTY_KO[prop]})", mode="lines",
                line=dict(color=color, width=2),
                hovertemplate="매매 평당가: %{y:,.0f} 만원/평<extra></extra>",
                showlegend=(col_idx == 1),
            ),
            row=1, col=col_idx,
        )
        fig.add_trace(
            go.Scatter(
                x=sub["month"], y=sub["jeonse_per_pyeong"],
                name=f"전세 ({PROPERTY_KO[prop]})", mode="lines",
                line=dict(color=color, width=2, dash="dash"),
                hovertemplate="전세 평당가: %{y:,.0f} 만원/평<extra></extra>",
                showlegend=(col_idx == 1),
            ),
            row=1, col=col_idx,
        )

    fig.update_yaxes(title_text="평당가 (만원/평)", row=1, col=1)
    fig.update_layout(
        title="매매가·전세가 월별 평균 추이 (종로구 전체, 평당가 기준)",
        height=440,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2),
        template="plotly_white",
        hovermode="x unified",
    )
    return fig


# ─────────────────────────────────────────────────────────────
# 04. 전세가율 월별 추이
# ─────────────────────────────────────────────────────────────
def fig_jeonse_ratio_trend(panel: pd.DataFrame) -> go.Figure:
    agg = (
        panel.dropna(subset=["jeonse_to_sale_ratio"])
        .groupby(["month", "property_type"], observed=True)["jeonse_to_sale_ratio"]
        .mean()
        .reset_index()
    )
    agg["ratio_pct"] = agg["jeonse_to_sale_ratio"] * 100

    fig = go.Figure()

    for prop in ["villa", "officetel"]:
        sub = agg[agg["property_type"] == prop].sort_values("month")
        fig.add_trace(
            go.Scatter(
                x=sub["month"], y=sub["ratio_pct"],
                name=PROPERTY_KO[prop], mode="lines",
                line=dict(color=PROPERTY_COLORS[prop], width=2),
                hovertemplate="전세가율: %{y:.1f}%<extra></extra>",
            )
        )

    # 위험 기준선
    for level, value, color in [
        ("위험(80%)",   80, "#E67E22"),
        ("주의(70%)",   70, "#F1C40F"),
    ]:
        fig.add_hline(
            y=value, line_dash="dot", line_color=color,
            annotation_text=level,
            annotation_position="right",
        )

    fig.update_layout(
        title="전세가율 월별 추이 (전세 평당가 ÷ 매매 평당가)",
        xaxis_title="월",
        yaxis_title="전세가율 (%)",
        height=420,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=-0.2),
        hovermode="x unified",
    )
    return fig


# ─────────────────────────────────────────────────────────────
# 05. 24개월 위험 예측 결과
# ─────────────────────────────────────────────────────────────
def fig_risk_forecast_24m(risk: pd.DataFrame) -> go.Figure:
    risk = risk.copy()
    risk["property_ko"] = risk["property_type"].map(PROPERTY_KO)
    risk["risk_ratio_pct"] = (risk["risk_ratio_24m"] * 100).round(1)

    risk_order = ["안전", "주의", "위험", "고위험", "깡통 가능성 매우 높음"]
    risk["risk_level"] = pd.Categorical(risk["risk_level"], categories=risk_order, ordered=True)
    risk = risk.sort_values("risk_ratio_24m", ascending=False)

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("위험 등급 분포", "동별 24개월 후 전세가율"),
        column_widths=[0.35, 0.65],
        horizontal_spacing=0.1,
        specs=[[{"type": "pie"}, {"type": "xy"}]],
    )

    # ── 도넛 차트 ──
    cnt = risk["risk_level"].value_counts().reindex(risk_order).dropna()
    fig.add_trace(
        go.Pie(
            labels=cnt.index.tolist(),
            values=cnt.values.tolist(),
            hole=0.45,
            marker_colors=[RISK_COLORS[r] for r in cnt.index],
            textinfo="label+percent",
            hovertemplate="%{label}: %{value}개 동<extra></extra>",
        ),
        row=1, col=1,
    )

    # ── 가로 바 차트 ──
    fig.add_trace(
        go.Bar(
            x=risk["risk_ratio_pct"],
            y=risk["dong_name"] + " (" + risk["property_ko"] + ")",
            orientation="h",
            marker_color=[RISK_COLORS.get(str(r), "#95A5A6") for r in risk["risk_level"]],
            text=risk["risk_ratio_pct"].astype(str) + "%",
            textposition="outside",
            hovertemplate=(
                "%{y}<br>"
                "24개월 후 전세가율: %{x:.1f}%<extra></extra>"
            ),
        ),
        row=1, col=2,
    )

    # add_vline은 mixed subplot에서 동작 안 함 → add_shape으로 대체
    for x_val, dash, color, label in [
        (80,  "dot",  "#E67E22", "위험(80%)"),
        (100, "dash", "#8E44AD", "깡통(100%)"),
    ]:
        fig.add_shape(
            type="line", xref="x2", yref="paper",
            x0=x_val, x1=x_val, y0=0, y1=1,
            line=dict(dash=dash, color=color, width=1.5),
        )
        fig.add_annotation(
            xref="x2", yref="paper",
            x=x_val, y=1.02, text=label,
            showarrow=False, font=dict(color=color, size=10),
        )

    fig.update_xaxes(title_text="24개월 후 예측 전세가율 (%)", row=1, col=2)
    fig.update_yaxes(autorange="reversed", tickfont_size=10, row=1, col=2)
    fig.update_layout(
        title="24개월 후 깡통전세 위험 예측 — 종로구 동별 현황",
        height=max(500, len(risk) * 20 + 150),
        showlegend=False,
        template="plotly_white",
    )
    return fig


# ─────────────────────────────────────────────────────────────
# 06. 동별 위험도 분포 (현재 전세가율 vs 예측 전세가율)
# ─────────────────────────────────────────────────────────────
def fig_risk_by_dong(risk: pd.DataFrame) -> go.Figure:
    risk = risk.copy()
    risk["property_ko"] = risk["property_type"].map(PROPERTY_KO)
    risk["current_ratio_pct"] = (risk["current_jeonse_per_pyeong"] / risk["current_sale_per_pyeong"] * 100).round(1)
    risk["forecast_ratio_pct"] = (risk["risk_ratio_24m"] * 100).round(1)
    risk["delta_pct"] = (risk["forecast_ratio_pct"] - risk["current_ratio_pct"]).round(1)

    fig = go.Figure()

    for prop in ["villa", "officetel"]:
        sub = risk[risk["property_type"] == prop]
        fig.add_trace(
            go.Scatter(
                x=sub["current_ratio_pct"],
                y=sub["forecast_ratio_pct"],
                mode="markers+text",
                name=PROPERTY_KO[prop],
                marker=dict(
                    color=[RISK_COLORS.get(str(r), "#95A5A6") for r in sub["risk_level"]],
                    size=12,
                    symbol="circle" if prop == "villa" else "diamond",
                    line=dict(width=1, color="white"),
                ),
                text=sub["dong_name"],
                textposition="top center",
                textfont=dict(size=9),
                hovertemplate=(
                    "<b>%{text}</b> (" + PROPERTY_KO[prop] + ")<br>"
                    "현재 전세가율: %{x:.1f}%<br>"
                    "24개월 후 예측: %{y:.1f}%<extra></extra>"
                ),
            )
        )

    # 기준선 (y = x: 변화 없음)
    max_val = max(risk["current_ratio_pct"].max(), risk["forecast_ratio_pct"].max()) + 10
    fig.add_trace(
        go.Scatter(
            x=[0, max_val], y=[0, max_val],
            mode="lines", name="변화 없음",
            line=dict(color="gray", dash="dot", width=1),
            showlegend=True,
        )
    )

    # 위험 기준선
    for pct, label, color in [(80, "위험(80%)", "#E67E22"), (100, "깡통(100%)", "#8E44AD")]:
        fig.add_hline(y=pct, line_dash="dash", line_color=color,
                      annotation_text=label, annotation_position="right")
        fig.add_vline(x=pct, line_dash="dash", line_color=color)

    fig.update_layout(
        title="현재 전세가율 vs 24개월 후 예측 전세가율 (동별)",
        xaxis_title="현재 전세가율 (%)",
        yaxis_title="24개월 후 예측 전세가율 (%)",
        height=580,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=-0.15),
    )
    return fig


# ─────────────────────────────────────────────────────────────
# 저장 및 실행
# ─────────────────────────────────────────────────────────────
def save_html(fig: go.Figure, path: Path, title: str) -> None:
    fig.write_html(str(path), include_plotlyjs="cdn")
    print(f"  [저장] {path.name}")


def run(artifact_dir: Path = ARTIFACT_DIR) -> None:
    output_dir = artifact_dir / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("[*] 데이터 로딩...")
    metrics, panel, risk = load_artifacts(artifact_dir)
    print(f"    패널: {len(panel)}행  위험예측: {len(risk)}행")

    print("[*] 시각화 생성 중...")
    save_html(fig_model_metrics(metrics),          output_dir / "01_model_metrics.html",       "모델 평가지표")
    save_html(fig_confusion_matrices(metrics),     output_dir / "02_confusion_matrices.html",  "혼동행렬")
    save_html(fig_price_trend(panel),              output_dir / "03_price_trend.html",         "가격 추이")
    save_html(fig_jeonse_ratio_trend(panel),       output_dir / "04_jeonse_ratio_trend.html",  "전세가율 추이")
    save_html(fig_risk_forecast_24m(risk),         output_dir / "05_risk_forecast_24m.html",   "24개월 위험 예측")
    save_html(fig_risk_by_dong(risk),              output_dir / "06_risk_by_dong.html",        "동별 위험도 산점도")

    print(f"\n[+] 완료. 결과물 위치: {output_dir}")
    print("    브라우저에서 HTML 파일을 열어 확인하세요.")


def main() -> None:
    parser = argparse.ArgumentParser(description="깡통전세 모델 결과 시각화")
    parser.add_argument("--artifact-dir", type=Path, default=ARTIFACT_DIR)
    args = parser.parse_args()
    run(args.artifact_dir)


if __name__ == "__main__":
    main()
