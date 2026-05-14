"""
시세 비교 서비스 (diagnosis_agents.py의 ModelAgent에서 호출)
- 매매 실거래가 기반: 전세가율 계산 (전세금 ÷ 매매 시세)
- 전세 실거래가 기반: 시장 전세가 비교 (계약 전세금이 너무 높거나 낮으면 사기 신호)

전제 조건:
  sale_transactions 테이블에 dong_name 컬럼이 있어야 합니다.
  database/migration_market.sql 실행 후 rag/ingestion/load_market_data.py 를 실행하세요.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import psycopg2
import psycopg2.extras

from rag_server.config import Settings


# ── 결과 데이터 클래스 ────────────────────────────────────────────────

@dataclass
class MarketStats:
    """매매 시세 통계"""
    dong_name: str
    housing_type: Optional[str]
    sample_count: int
    median_price: int        # 만원
    avg_price: int           # 만원
    avg_price_per_m2: float  # 만원/㎡

@dataclass
class JeonseMarketStats:
    """전세 시장 통계 (실거래 전세가)"""
    dong_name: str
    housing_type: Optional[str]
    sample_count: int
    median_deposit: int      # 만원
    avg_deposit: int         # 만원
    p25_deposit: int         # 하위 25% (너무 저렴한 매물 기준)
    p75_deposit: int         # 상위 75% (고가 경계선)
    pure_jeonse_ratio: float # 순전세(월세=0) 비율 (%)

@dataclass
class JeonseRatioResult:
    """전세가율 분석 결과"""
    jeonse_ratio: float
    deposit_amount: int
    estimated_sale_price: int   # 매매 중위 시세 (만원)
    risk_level: str             # 안전 / 주의 / 위험
    message: str
    sample_count: int
    dong_name: str

@dataclass
class JeonseAnomalyResult:
    """전세가 이상 탐지 결과 (시장 전세가 비교)"""
    deposit_amount: int           # 계약 전세금
    market_median: int            # 시장 중위 전세가
    deviation_pct: float          # 시장 대비 편차 (%)
    anomaly_type: str             # NORMAL / HIGH / LOW
    risk_level: str               # 안전 / 주의 / 위험
    message: str
    sample_count: int

@dataclass
class PriceTrend:
    """연도별 가격 추세"""
    dong_name: str
    data_type: str              # 매매 / 전세
    yearly: list[dict] = field(default_factory=list)
    direction: str = "데이터 부족"
    change_rate_pct: float = 0.0


# ── 서비스 본체 ───────────────────────────────────────────────────────

class MarketPriceService:

    def __init__(self, settings: Settings):
        self._cfg = dict(
            host=settings.DB_HOST, port=settings.DB_PORT,
            dbname=settings.DB_NAME, user=settings.DB_USER,
            password=settings.DB_PASSWORD,
        )

    def _conn(self):
        return psycopg2.connect(**self._cfg)

    # ── 주소/유형 유틸 ────────────────────────────────────────────────

    @staticmethod
    def extract_dong(address: str) -> Optional[str]:
        """'서울특별시 종로구 평창동 329-2' → '평창동'"""
        m = re.search(r"(\S+(?:동|읍|면|리|가))\b", address)
        return m.group(1) if m else None

    @staticmethod
    def detect_housing_type(text: str) -> Optional[str]:
        if re.search(r"오피스텔", text):
            return "오피스텔"
        if re.search(r"연립|다세대|빌라", text):
            return "연립다세대"
        return None

    @staticmethod
    def _min_ym(years: int) -> int:
        from datetime import date
        d = date.today()
        return (d.year - years) * 100 + d.month

    # ── 1. 매매 시세 조회 ─────────────────────────────────────────────

    def get_sale_stats(
        self,
        dong_name: str,
        housing_type: Optional[str] = None,
        area_m2: Optional[float] = None,
        years: int = 3,
    ) -> Optional[MarketStats]:
        """동별 매매 중위 시세 조회"""
        sql = """
        SELECT
            COUNT(*)                                                    AS cnt,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deal_amount)   AS median,
            AVG(deal_amount)::INT                                       AS avg,
            AVG(deal_amount::FLOAT / NULLIF(exclusive_area, 0))        AS per_m2
        FROM sale_transactions
        WHERE dong_name = %(dong)s
          AND deal_year_month >= %(min_ym)s
          AND (%(ht)s IS NULL OR housing_type = %(ht)s)
          AND (%(area)s IS NULL
               OR exclusive_area BETWEEN %(area_lo)s AND %(area_hi)s)
        """
        params = dict(
            dong=dong_name, min_ym=self._min_ym(years), ht=housing_type,
            area=area_m2,
            area_lo=(area_m2 - 15) if area_m2 else 0,
            area_hi=(area_m2 + 15) if area_m2 else 9999,
        )
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, params)
                    row = cur.fetchone()
            if not row or row["cnt"] == 0:
                # 면적 조건 완화 재시도
                if area_m2:
                    return self.get_sale_stats(dong_name, housing_type, None, years)
                return None
            return MarketStats(
                dong_name=dong_name, housing_type=housing_type,
                sample_count=int(row["cnt"]),
                median_price=int(row["median"]),
                avg_price=int(row["avg"]),
                avg_price_per_m2=round(float(row["per_m2"] or 0), 1),
            )
        except Exception as e:
            print(f"[MarketPriceService] get_sale_stats 오류: {e}")
            return None

    # ── 2. 전세 시장 통계 조회 ────────────────────────────────────────

    def get_jeonse_stats(
        self,
        dong_name: str,
        housing_type: Optional[str] = None,
        area_m2: Optional[float] = None,
        years: int = 2,
        pure_only: bool = True,   # True = 순전세(월세=0)만
    ) -> Optional[JeonseMarketStats]:
        """동별 전세 시장 통계 (실거래 전세가 분포)"""
        sql = """
        SELECT
            COUNT(*)                                                        AS cnt,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deposit_amount)    AS median,
            AVG(deposit_amount)::INT                                        AS avg,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY deposit_amount)   AS p25,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY deposit_amount)   AS p75,
            ROUND(
                100.0 * SUM(CASE WHEN monthly_rent = 0 THEN 1 ELSE 0 END) / COUNT(*),
                1
            )                                                               AS pure_ratio
        FROM jeonse_transactions
        WHERE dong_name = %(dong)s
          AND contract_date >= (CURRENT_DATE - INTERVAL '%(years)s years')
          AND (%(ht)s IS NULL OR housing_type = %(ht)s)
          AND (%(pure)s = FALSE OR monthly_rent = 0)
          AND (%(area)s IS NULL
               OR exclusive_area_m2 BETWEEN %(area_lo)s AND %(area_hi)s)
        """
        params = dict(
            dong=dong_name, years=years, ht=housing_type,
            pure=pure_only, area=area_m2,
            area_lo=(area_m2 - 15) if area_m2 else 0,
            area_hi=(area_m2 + 15) if area_m2 else 9999,
        )
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, params)
                    row = cur.fetchone()
            if not row or row["cnt"] == 0:
                if area_m2:
                    return self.get_jeonse_stats(dong_name, housing_type, None, years, pure_only)
                # 순전세 한정 해제 후 재시도
                if pure_only:
                    return self.get_jeonse_stats(dong_name, housing_type, area_m2, years, False)
                return None
            return JeonseMarketStats(
                dong_name=dong_name, housing_type=housing_type,
                sample_count=int(row["cnt"]),
                median_deposit=int(row["median"]),
                avg_deposit=int(row["avg"]),
                p25_deposit=int(row["p25"]),
                p75_deposit=int(row["p75"]),
                pure_jeonse_ratio=float(row["pure_ratio"] or 0),
            )
        except Exception as e:
            print(f"[MarketPriceService] get_jeonse_stats 오류: {e}")
            return None

    # ── 3. 전세가율 계산 (매매 시세 기반) ────────────────────────────

    def calculate_jeonse_ratio(
        self,
        deposit_amount: int,
        dong_name: str,
        housing_type: Optional[str] = None,
        area_m2: Optional[float] = None,
    ) -> Optional[JeonseRatioResult]:
        """전세금 ÷ 매매 중위 시세 × 100"""
        stats = self.get_sale_stats(dong_name, housing_type, area_m2)
        if not stats or stats.median_price <= 0:
            return None

        ratio = deposit_amount / stats.median_price * 100

        if ratio >= 100:
            level = "위험"
            msg   = (f"⚠️ 전세금({deposit_amount:,}만원)이 매매 시세({stats.median_price:,}만원)를 "
                     f"초과합니다 (전세가율 {ratio:.1f}%). 전세사기 강력 의심.")
        elif ratio >= 80:
            level = "위험"
            msg   = (f"전세가율 {ratio:.1f}% — 매매 시세({stats.median_price:,}만원) 대비 "
                     f"80% 초과. 경매 시 보증금 회수 불가 위험.")
        elif ratio >= 70:
            level = "주의"
            msg   = (f"전세가율 {ratio:.1f}% — 70~80% 주의 구간. "
                     f"전세보증보험 가입 필수.")
        else:
            level = "안전"
            msg   = (f"전세가율 {ratio:.1f}% — 정상 범위 "
                     f"(시세 {stats.median_price:,}만원 기준).")

        return JeonseRatioResult(
            jeonse_ratio=round(ratio, 1),
            deposit_amount=deposit_amount,
            estimated_sale_price=stats.median_price,
            risk_level=level, message=msg,
            sample_count=stats.sample_count,
            dong_name=dong_name,
        )

    # ── 4. 전세가 이상 탐지 (전세 시장가 비교) ───────────────────────

    def detect_jeonse_anomaly(
        self,
        deposit_amount: int,
        dong_name: str,
        housing_type: Optional[str] = None,
        area_m2: Optional[float] = None,
    ) -> Optional[JeonseAnomalyResult]:
        """
        계약 전세금을 시장 전세가와 비교.
        - 시장가보다 20%+ 높음  → 고가 전세 (보증금 떼먹기 세팅 의심)
        - 시장가보다 30%+ 낮음  → 저가 전세 (급전 필요 신호, 갭투자 의심)
        """
        stats = self.get_jeonse_stats(dong_name, housing_type, area_m2)
        if not stats or stats.median_deposit <= 0:
            return None

        dev = (deposit_amount - stats.median_deposit) / stats.median_deposit * 100

        if dev >= 20:
            anomaly = "HIGH"
            level   = "위험"
            msg     = (f"⚠️ 계약 전세금({deposit_amount:,}만원)이 시장 중위 전세가 "
                       f"({stats.median_deposit:,}만원)보다 {dev:.1f}% 높습니다. "
                       f"보증금을 돌려받지 못할 위험이 있는 고가 전세입니다.")
        elif dev <= -30:
            anomaly = "LOW"
            level   = "주의"
            msg     = (f"계약 전세금({deposit_amount:,}만원)이 시장 중위 전세가 "
                       f"({stats.median_deposit:,}만원)보다 {abs(dev):.1f}% 낮습니다. "
                       f"임대인이 급전이 필요하거나 갭투자·재전세 의심.")
        else:
            anomaly = "NORMAL"
            level   = "안전"
            msg     = (f"전세금이 시장 전세가 범위 내 정상 수준입니다 "
                       f"(시장 중위 {stats.median_deposit:,}만원, 편차 {dev:+.1f}%).")

        return JeonseAnomalyResult(
            deposit_amount=deposit_amount,
            market_median=stats.median_deposit,
            deviation_pct=round(dev, 1),
            anomaly_type=anomaly,
            risk_level=level,
            message=msg,
            sample_count=stats.sample_count,
        )

    # ── 5. 연도별 가격 추세 ───────────────────────────────────────────

    def get_price_trend(
        self,
        dong_name: str,
        housing_type: Optional[str] = None,
        data_type: str = "매매",   # "매매" | "전세"
    ) -> Optional[PriceTrend]:
        """연도별 중위가 추세 및 방향 분석"""
        if data_type == "전세":
            sql = """
            SELECT
                EXTRACT(YEAR FROM contract_date)::INT                        AS yr,
                COUNT(*)                                                      AS cnt,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deposit_amount)  AS median
            FROM jeonse_transactions
            WHERE dong_name = %(dong)s
              AND (%(ht)s IS NULL OR housing_type = %(ht)s)
              AND monthly_rent = 0
            GROUP BY yr ORDER BY yr
            """
        else:
            sql = """
            SELECT
                FLOOR(deal_year_month / 100)::INT                            AS yr,
                COUNT(*)                                                      AS cnt,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY deal_amount)     AS median
            FROM sale_transactions
            WHERE dong_name = %(dong)s
              AND (%(ht)s IS NULL OR housing_type = %(ht)s)
            GROUP BY yr ORDER BY yr
            """
        try:
            with self._conn() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, {"dong": dong_name, "ht": housing_type})
                    rows = cur.fetchall()
            if not rows:
                return None

            yearly = [
                {"year": int(r["yr"]), "count": int(r["cnt"]), "median": int(r["median"])}
                for r in rows
            ]
            if len(yearly) >= 2:
                old, new = yearly[-2]["median"], yearly[-1]["median"]
                chg = (new - old) / old * 100 if old else 0
                direction = "상승" if chg > 2 else ("하락" if chg < -2 else "보합")
            else:
                chg, direction = 0.0, "데이터 부족"

            return PriceTrend(
                dong_name=dong_name, data_type=data_type,
                yearly=yearly, direction=direction,
                change_rate_pct=round(chg, 1),
            )
        except Exception as e:
            print(f"[MarketPriceService] get_price_trend 오류: {e}")
            return None

    # ── 6. LLM 주입용 통합 컨텍스트 생성 ────────────────────────────

    def build_context_text(
        self,
        dong_name: str,
        deposit_amount: int,
        housing_type: Optional[str] = None,
        area_m2: Optional[float] = None,
    ) -> str:
        """
        매매 시세 + 전세 시장가 + 추세를 종합한 LLM 프롬프트용 텍스트.
        이 텍스트가 계약서 앞에 붙어 LLM의 위험 판단 근거가 됩니다.
        """
        lines = [f"[실거래가 시세 분석 — {dong_name}]"]

        # ① 전세가율 (매매 시세 기반)
        ratio_r = self.calculate_jeonse_ratio(deposit_amount, dong_name, housing_type, area_m2)
        if ratio_r:
            lines += [
                f"• 전세가율 분석 (매매 시세 기준)",
                f"  - 계약 전세금: {deposit_amount:,}만원",
                f"  - 매매 중위 시세: {ratio_r.estimated_sale_price:,}만원 "
                  f"(표본 {ratio_r.sample_count}건)",
                f"  - 전세가율: {ratio_r.jeonse_ratio}% → {ratio_r.risk_level}",
                f"  - 판정: {ratio_r.message}",
            ]
        else:
            lines.append(f"• 매매 시세 데이터 없음 ({dong_name}) — 직접 시세 확인 필요")

        # ② 전세 시장가 비교 (사기 탐지)
        anomaly_r = self.detect_jeonse_anomaly(deposit_amount, dong_name, housing_type, area_m2)
        if anomaly_r:
            lines += [
                f"• 시장 전세가 비교",
                f"  - 시장 전세 중위가: {anomaly_r.market_median:,}만원 "
                  f"(표본 {anomaly_r.sample_count}건)",
                f"  - 시장 대비 편차: {anomaly_r.deviation_pct:+.1f}% → {anomaly_r.anomaly_type}",
                f"  - 판정: {anomaly_r.message}",
            ]
        else:
            lines.append("• 전세 실거래 데이터 없음 — 시장가 비교 불가")

        # ③ 매매 추세
        sale_trend = self.get_price_trend(dong_name, housing_type, "매매")
        if sale_trend and sale_trend.yearly:
            trend_str = " → ".join(
                f"{y['year']}년 {y['median']:,}만원" for y in sale_trend.yearly
            )
            lines += [
                f"• 매매가 추세: {trend_str}",
                f"  - 방향: {sale_trend.direction} ({sale_trend.change_rate_pct:+.1f}%)",
            ]
            if sale_trend.direction == "하락":
                lines.append(
                    "  ⚠️ 하락장: 2년 후 계약 만료 시 집값이 더 하락하면 보증금 반환 거부 위험"
                )

        # ④ 전세 추세
        jeonse_trend = self.get_price_trend(dong_name, housing_type, "전세")
        if jeonse_trend and jeonse_trend.yearly:
            trend_str = " → ".join(
                f"{y['year']}년 {y['median']:,}만원" for y in jeonse_trend.yearly
            )
            lines += [
                f"• 전세가 추세: {trend_str}",
                f"  - 방향: {jeonse_trend.direction} ({jeonse_trend.change_rate_pct:+.1f}%)",
            ]
            if jeonse_trend.direction == "하락":
                lines.append(
                    "  ⚠️ 전세가 하락장: 계약 전세금이 향후 시세보다 높아질 수 있음"
                )

        return "\n".join(lines)
