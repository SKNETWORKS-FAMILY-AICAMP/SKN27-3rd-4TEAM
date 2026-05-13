"""
Neo4j 지식 그래프 v2 검증 테스트
실행: python test_neo4j.py [--verbose]
"""

import sys
from dotenv import load_dotenv
import os

load_dotenv()

from neo4j import GraphDatabase

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "jeonse1234")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
VERBOSE = "--verbose" in sys.argv

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

results = []

def q(cypher: str, params: dict = None) -> list[dict]:
    with driver.session() as s:
        return [dict(r) for r in s.run(cypher, **(params or {}))]

def check(name: str, passed: bool, detail: str = ""):
    icon = PASS if passed else FAIL
    results.append((icon, name, detail))
    print(f"  {icon}  {name}" + (f"\n      {detail}" if VERBOSE and detail else ""))

def section(title: str):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")


# ─────────────────────────────────────────────────────────
# 1. 노드 수량 검증
# ─────────────────────────────────────────────────────────
section("1. 노드 수량 검증")

EXPECTED_COUNTS = {
    "RiskFactor":      12,
    "LegalConcept":    15,
    "Procedure":        7,
    "Domain":           7,
    "DocumentCategory":10,
    "AgentScope":       8,
}

rows = q("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt")
actual = {r["label"]: r["cnt"] for r in rows}

for label, expected in EXPECTED_COUNTS.items():
    cnt = actual.get(label, 0)
    check(
        f"{label}: {cnt}개 (기대값 {expected}개)",
        cnt >= expected,
        f"실제={cnt}",
    )

# Law / Case는 DB 기반 동적 생성 — 존재 여부만 확인
for label in ["Law", "Case"]:
    cnt = actual.get(label, 0)
    check(f"{label}: {cnt}개 (1개 이상)", cnt >= 1, f"실제={cnt}")


# ─────────────────────────────────────────────────────────
# 2. 관계 수량 검증
# ─────────────────────────────────────────────────────────
section("2. 관계 수량 검증")

EXPECTED_RELS = {
    "REGULATED_BY": 1,
    "RELATED_TO":   1,
    "BELONGS_TO":   1,
    "COVERS":       1,
    "GOVERNED_BY":  1,
    "REQUIRES":     1,
    "DEFINED_IN":   1,
    "DETECTED_BY":  1,
    "IN_CATEGORY":  1,
    "INVOLVES":     1,
    "EVIDENCED_BY": 1,
}

rel_rows = q("MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS cnt")
actual_rels = {r["rel"]: r["cnt"] for r in rel_rows}

for rel, min_count in EXPECTED_RELS.items():
    cnt = actual_rels.get(rel, 0)
    check(f":{rel} 관계 존재", cnt >= min_count, f"실제={cnt}건")


# ─────────────────────────────────────────────────────────
# 3. 에이전트 연결 검증
# ─────────────────────────────────────────────────────────
section("3. AgentScope 연결 검증")

EXPECTED_AGENTS = [
    "special_clause_agent",
    "ownership_risk_agent",
    "market_risk_agent",
    "insurance_risk_agent",
    "required_check_agent",
    "legal_basis_agent",
    "legal_rag_agent",
    "friendly_counselor_agent",
]

for agent in EXPECTED_AGENTS:
    rows = q("""
        MATCH (a:AgentScope {name: $name})-[:COVERS]->(dc:DocumentCategory)
        RETURN count(dc) AS cnt
    """, {"name": agent})
    cnt = rows[0]["cnt"] if rows else 0
    check(f"{agent} → DocumentCategory {cnt}개 연결", cnt >= 1)

# 에이전트별 DETECTED_BY 위험요소 수
rows = q("""
    MATCH (a:AgentScope)-[:DETECTED_BY]->(rf:RiskFactor)
    RETURN a.name AS agent, count(rf) AS cnt
    ORDER BY cnt DESC
""")
if VERBOSE:
    print("\n  [에이전트별 담당 RiskFactor]")
    for r in rows:
        print(f"    {r['agent']}: {r['cnt']}개")


# ─────────────────────────────────────────────────────────
# 4. 법률 개념 선후관계 검증
# ─────────────────────────────────────────────────────────
section("4. LegalConcept 선후관계 검증")

EXPECTED_REQUIRES = [
    ("대항력",     "전입신고"),
    ("우선변제권", "전입신고"),
    ("우선변제권", "확정일자"),
    ("임차권등기", "전입신고"),
]

for concept, req in EXPECTED_REQUIRES:
    rows = q("""
        MATCH (lc:LegalConcept {name: $concept})-[:REQUIRES]->(r:LegalConcept {name: $req})
        RETURN count(r) AS cnt
    """, {"concept": concept, "req": req})
    cnt = rows[0]["cnt"] if rows else 0
    check(f"{concept} -[:REQUIRES]-> {req}", cnt == 1)


# ─────────────────────────────────────────────────────────
# 5. RiskFactor 핵심 연결 검증
# ─────────────────────────────────────────────────────────
section("5. RiskFactor 핵심 연결 검증")

# RF001~RF012 모두 존재하는지
for rf_id in [f"RF{i:03d}" for i in range(1, 13)]:
    rows = q("MATCH (rf:RiskFactor {factor_id: $id}) RETURN count(rf) AS cnt", {"id": rf_id})
    cnt = rows[0]["cnt"] if rows else 0
    check(f"{rf_id} 존재", cnt == 1)

# RiskFactor가 최소 1개의 Law에 연결됐는지
rows = q("""
    MATCH (rf:RiskFactor)
    WHERE NOT (rf)-[:REGULATED_BY]->(:Law)
    RETURN rf.factor_id AS id
""")
no_law = [r["id"] for r in rows]
check("모든 RiskFactor에 Law 연결", len(no_law) == 0,
      f"Law 없는 RiskFactor: {no_law}" if no_law else "")


# ─────────────────────────────────────────────────────────
# 6. 고아 노드 검증 (관계 없는 노드)
# ─────────────────────────────────────────────────────────
section("6. 고아 노드 검증")

rows = q("""
    MATCH (n)
    WHERE NOT (n)--()
      AND NOT n:Law        // Law는 키워드 미매칭 시 단독 존재 가능
      AND NOT n:Case       // Case는 키워드 미매칭 시 IN_CATEGORY 없을 수 있음
    RETURN labels(n)[0] AS label, n.name AS name
    LIMIT 20
""")
check(
    f"고아 노드 없음 (발견={len(rows)}개)",
    len(rows) == 0,
    str([(r["label"], r["name"]) for r in rows]) if rows else "",
)


# ─────────────────────────────────────────────────────────
# 7. graph_store.py 메서드 통합 테스트
# ─────────────────────────────────────────────────────────
section("7. graph_store.py 메서드 통합 테스트")

try:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
    from rag_server.config import Settings
    from rag_server.core.graph_store import GraphStore

    settings = Settings()
    gs = GraphStore(settings)

    # get_risk_factors_by_keywords
    risks = gs.get_risk_factors_by_keywords(["근저당", "전세가율"])
    check("get_risk_factors_by_keywords()", len(risks) > 0, f"결과 {len(risks)}건")

    # get_context_for_agent
    ctx = gs.get_context_for_agent("ownership_risk_agent")
    check("get_context_for_agent('ownership_risk_agent')", len(ctx) > 0, f"결과 {len(ctx)}건")

    # get_legal_concepts
    concepts = gs.get_legal_concepts(["대항력", "전입신고"])
    check("get_legal_concepts(['대항력','전입신고'])", len(concepts) > 0, f"결과 {len(concepts)}건")

    # get_document_categories_for_agent
    cats = gs.get_document_categories_for_agent("market_risk_agent")
    check("get_document_categories_for_agent('market_risk_agent')", len(cats) > 0,
          str([c["name"] for c in cats]))

    # get_full_graph_context
    full_ctx = gs.get_full_graph_context(["근저당", "전입신고", "확정일자"])
    check("get_full_graph_context()", len(full_ctx) > 0, f"결과 {len(full_ctx)}건")
    if VERBOSE:
        print("\n  [graph_context 샘플 (상위 5개)]")
        for item in full_ctx[:5]:
            print(f"    {item['node']} --[{item['relation']}]--> {item['target']}")

    gs.close()

except Exception as e:
    check("graph_store.py import/실행", False, str(e))


# ─────────────────────────────────────────────────────────
# 최종 요약
# ─────────────────────────────────────────────────────────
print(f"\n{'='*55}")
total  = len(results)
passed = sum(1 for r in results if r[0] == PASS)
failed = total - passed

print(f"  결과: {passed}/{total} 통과  |  실패: {failed}건")
if failed > 0:
    print(f"\n  [실패 항목]")
    for icon, name, detail in results:
        if icon == FAIL:
            print(f"    {FAIL}  {name}")
            if detail:
                print(f"        → {detail}")
print(f"{'='*55}\n")

driver.close()
sys.exit(0 if failed == 0 else 1)
