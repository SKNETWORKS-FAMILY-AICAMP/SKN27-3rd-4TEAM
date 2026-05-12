"""
[미사용 — 향후 참고용]
load_market_data.py 로 CSV 적재 완료 후 market_price_service.py 검증용 테스트입니다.
현재 시세 기능이 비활성화 상태이므로 실행하지 않아도 됩니다.

시세 비교 기능 통합 테스트
실행: python rag/ingestion/test_market_price.py
"""
from __future__ import annotations
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from rag_server.config import Settings
from rag_server.services.market_price_service import MarketPriceService
import psycopg2

settings = Settings()
svc      = MarketPriceService(settings)

SEP = "=" * 62


def section(t): print(f"\n{SEP}\n  {t}\n{SEP}")
def ok(m):   print(f"  ✅ {m}")
def warn(m): print(f"  ⚠️  {m}")
def fail(m): print(f"  ❌ {m}")
def info(m): print(f"     {m}")


# ══════════════════════════════════════════════════════════════════════
# TEST 1 — DB 적재 현황
# ══════════════════════════════════════════════════════════════════════
section("TEST 1 — DB 적재 현황")

try:
    conn = psycopg2.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        dbname=settings.DB_NAME, user=settings.DB_USER,
        password=settings.DB_PASSWORD,
    )
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM sale_transactions WHERE dong_name IS NOT NULL")
    sale_total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM jeonse_transactions WHERE dong_name IS NOT NULL")
    jeonse_total = cur.fetchone()[0]

    cur.execute("""
        SELECT housing_type, FLOOR(deal_year_month/100)::INT AS yr, COUNT(*) AS cnt
        FROM sale_transactions WHERE dong_name IS NOT NULL
        GROUP BY housing_type, yr ORDER BY housing_type, yr
    """)
    sale_rows = cur.fetchall()

    cur.execute("""
        SELECT housing_type, EXTRACT(YEAR FROM contract_date)::INT AS yr, COUNT(*) AS cnt
        FROM jeonse_transactions WHERE dong_name IS NOT NULL
        GROUP BY housing_type, yr ORDER BY housing_type, yr
    """)
    jeonse_rows = cur.fetchall()

    cur.close(); conn.close()

    ok(f"sale_transactions:   {sale_total:,}행")
    ok(f"jeonse_transactions: {jeonse_total:,}행")

    print(f"\n  {'[매매]':<14} {'연도':>6} {'건수':>6}")
    for ht, yr, cnt in sale_rows:
        print(f"  {ht:<14} {yr:>6} {cnt:>6}건")

    if jeonse_rows:
        print(f"\n  {'[전세]':<14} {'연도':>6} {'건수':>6}")
        for ht, yr, cnt in jeonse_rows:
            print(f"  {ht:<14} {yr:>6} {cnt:>6}건")
    else:
        warn("전세 데이터 없음 — 전세 CSV를 재업로드 후 load_market_data.py 실행 필요")

    if sale_total == 0:
        fail("매매 데이터 없음 — load_market_data.py 먼저 실행하세요")
        sys.exit(1)

except Exception as e:
    fail(f"DB 연결 실패: {e}")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════
# TEST 2 — 동별 매매 시세
# ══════════════════════════════════════════════════════════════════════
section("TEST 2 — 동별 매매 시세")

for dong in ["숭인동", "내수동", "평창동", "수송동"]:
    s = svc.get_sale_stats(dong, years=3)
    if s:
        ok(f"{dong}: 중위 {s.median_price:,}만원 / ㎡당 {s.avg_price_per_m2:,}만원 ({s.sample_count}건)")
    else:
        warn(f"{dong}: 데이터 없음")


# ══════════════════════════════════════════════════════════════════════
# TEST 3 — 전세가율 (매매 시세 기반)
# ══════════════════════════════════════════════════════════════════════
section("TEST 3 — 전세가율 계산 (매매 시세 기반)")

sale_ref = svc.get_sale_stats("숭인동", "오피스텔", years=3)
base = sale_ref.median_price if sale_ref else 15000

RATIO_CASES = [
    ("안전 (60%)",     int(base * 0.60)),
    ("주의 (75%)",     int(base * 0.75)),
    ("위험 (85%)",     int(base * 0.85)),
    ("사기 의심 (105%)", int(base * 1.05)),
]
for label, dep in RATIO_CASES:
    r = svc.calculate_jeonse_ratio(dep, "숭인동", "오피스텔")
    if r:
        icon = {"안전":"🟢","주의":"🟡","위험":"🔴"}.get(r.risk_level,"⚪")
        print(f"\n  [{label}] 전세금 {dep:,}만원")
        print(f"    {icon} 전세가율 {r.jeonse_ratio}% → {r.risk_level}")
        info(r.message)
    else:
        warn(f"{label}: 계산 불가")


# ══════════════════════════════════════════════════════════════════════
# TEST 4 — 전세 시장가 이상 탐지
# ══════════════════════════════════════════════════════════════════════
section("TEST 4 — 시장 전세가 비교 (사기 징조 탐지)")

jeonse_ref = svc.get_jeonse_stats("숭인동", "오피스텔")
if jeonse_ref:
    ok(f"숭인동 오피스텔 시장 전세 중위가: {jeonse_ref.median_deposit:,}만원 ({jeonse_ref.sample_count}건)")
    base_j = jeonse_ref.median_deposit
    ANOMALY_CASES = [
        ("정상 (±10%)",          int(base_j * 1.05)),
        ("고가 전세 (+30%)",      int(base_j * 1.30)),
        ("저가 전세 (-35%)",      int(base_j * 0.65)),
    ]
    for label, dep in ANOMALY_CASES:
        a = svc.detect_jeonse_anomaly(dep, "숭인동", "오피스텔")
        if a:
            icon = {"NORMAL":"🟢","LOW":"🟡","HIGH":"🔴"}.get(a.anomaly_type,"⚪")
            print(f"\n  [{label}] 전세금 {dep:,}만원")
            print(f"    {icon} 편차 {a.deviation_pct:+.1f}% → {a.anomaly_type} ({a.risk_level})")
            info(a.message)
else:
    warn("전세 데이터 없음 — 전세 CSV 재업로드 후 테스트 가능")


# ══════════════════════════════════════════════════════════════════════
# TEST 5 — 연도별 추세
# ══════════════════════════════════════════════════════════════════════
section("TEST 5 — 연도별 매매·전세가 추세")

for dong in ["숭인동", "평창동"]:
    for dtype in ["매매", "전세"]:
        t = svc.get_price_trend(dong, data_type=dtype)
        if t and t.yearly:
            trend_str = " → ".join(f"{y['year']}:{y['median']:,}만" for y in t.yearly)
            icon = "📈" if t.direction=="상승" else ("📉" if t.direction=="하락" else "➡️")
            print(f"  {dong} [{dtype}] {icon} {t.direction} {trend_str}")
        else:
            warn(f"{dong} [{dtype}] 데이터 없음")


# ══════════════════════════════════════════════════════════════════════
# TEST 6 — LLM 주입 통합 컨텍스트 (실제 계약서 시나리오)
# ══════════════════════════════════════════════════════════════════════
section("TEST 6 — LLM 주입 컨텍스트 (평창동 럭키평창빌라 4억 전세)")

ctx = svc.build_context_text(
    dong_name="평창동",
    deposit_amount=40000,
    housing_type="연립다세대",
)
print()
for line in ctx.split("\n"):
    print(f"  {line}")


print(f"\n{SEP}\n  모든 테스트 완료\n{SEP}")
