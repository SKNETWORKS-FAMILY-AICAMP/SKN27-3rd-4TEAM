"""
전세계약 위험 진단 에이전트 - Neo4j 지식 그래프 구축 스크립트
역할: 법령·판례·위험요소 간 관계를 Neo4j 그래프로 저장

그래프 구조:
  (:RiskFactor) -[:REGULATED_BY]-> (:Law)
  (:RiskFactor) -[:EVIDENCED_BY]-> (:Case)
  (:Law)        -[:CITED_IN]->     (:Case)
  (:Case)       -[:INVOLVES]->     (:RiskFactor)

실행: python rag/ingestion/build_graph.py
"""

import os
import re
import psycopg2
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

# ── Neo4j 연결 설정 ───────────────────────────────────────

host     = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
username = os.getenv("NEO4J_USER",     "neo4j")
password = os.getenv("NEO4J_PASSWORD", "jeonse1234")

driver = GraphDatabase.driver(uri=host, auth=(username, password))

# ── PostgreSQL 연결 설정 ──────────────────────────────────

DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME",     "jeonse_risk"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", "risk1234"),
}

# ── 법령 인식 패턴 ────────────────────────────────────────

LAW_PATTERN = re.compile(
    r"(주택임대차보호법|공인중개사법|민법|주택도시보증공사법|전세사기피해자\s*특별법)"
    r"\s*(제\d+조(?:의\d+)?(?:\s*제\d+항)?)",
    re.IGNORECASE,
)

RISK_KEYWORD_MAP = {
    "전세가율":    "RF001",
    "근저당":      "RF002",
    "가압류":      "RF002",
    "미등기":      "RF003",
    "현금":        "RF004",
    "소유자":      "RF005",
    "확정일자":    "RF008",
    "전입신고":    "RF008",
    "전세보증보험": "RF010",
    "빌라왕":      "RF009",
    "다수 전세":   "RF009",
    "특약":        "RF007",
}

# ── 시드 데이터 ───────────────────────────────────────────

RISK_FACTORS = [
    {
        "factor_id": "RF001", "category": "전세가율",
        "description": "전세가율 80% 초과 — 집값 대비 전세금이 지나치게 높아 경매 시 보증금 회수 불가 위험",
        "severity": "HIGH", "keywords": "전세가율 보증금 매매가",
        "advice": "KB부동산·호갱노노에서 시세 확인 후 전세가율 80% 미만 매물 선택",
        "laws": ["주택임대차보호법 제3조의3"],
    },
    {
        "factor_id": "RF002", "category": "권리관계",
        "description": "근저당·가압류 과다 — 선순위 권리 합계가 보증금을 초과하면 경매 시 손실",
        "severity": "HIGH", "keywords": "근저당 가압류 저당권 선순위",
        "advice": "계약 전 등기부등본 발급, 선순위 권리 합산액 확인",
        "laws": ["민법 제356조", "주택임대차보호법 제8조"],
    },
    {
        "factor_id": "RF003", "category": "권리관계",
        "description": "미등기·무허가 건물 — 등기가 없으면 임차인의 대항력 취득 자체 불가",
        "severity": "HIGH", "keywords": "미등기 무허가 건축물대장",
        "advice": "건축물대장·등기부등본 일치 여부 반드시 확인",
        "laws": ["주택임대차보호법 제3조"],
    },
    {
        "factor_id": "RF004", "category": "절차",
        "description": "계약금 현금 요구 — 사기 가능성 신호",
        "severity": "HIGH", "keywords": "현금 계약금 직접 입금",
        "advice": "계좌 이체 후 영수증 보관, 임대인 본인 계좌 확인",
        "laws": ["공인중개사법 제33조"],
    },
    {
        "factor_id": "RF005", "category": "절차",
        "description": "임대인 신원 미확인 — 계약서상 임대인과 등기부 소유자가 다른 경우",
        "severity": "HIGH", "keywords": "임대인 소유자 신분증 대리인",
        "advice": "신분증·등기권리증 대조, 대리인 계약 시 위임장·인감증명서 필수",
        "laws": ["공인중개사법 제25조"],
    },
    {
        "factor_id": "RF006", "category": "전세가율",
        "description": "전세가율 70~80% — 주의 구간, 시세 변동에 취약",
        "severity": "MEDIUM", "keywords": "전세가율",
        "advice": "전세보증보험(HUG/SGI) 가입 검토",
        "laws": ["주택도시보증공사법"],
    },
    {
        "factor_id": "RF007", "category": "특약",
        "description": "불리한 특약 조항 — 과도한 의무 전가",
        "severity": "MEDIUM", "keywords": "특약 원상복구 수리 책임",
        "advice": "특약 조항 법률 검토 후 협의",
        "laws": ["주택임대차보호법 제10조"],
    },
    {
        "factor_id": "RF008", "category": "절차",
        "description": "확정일자·전입신고 미이행 — 대항력과 우선변제권 미취득",
        "severity": "MEDIUM", "keywords": "확정일자 전입신고 대항력",
        "advice": "입주 당일 전입신고 + 확정일자 동시 취득 필수",
        "laws": ["주택임대차보호법 제3조의2"],
    },
    {
        "factor_id": "RF009", "category": "권리관계",
        "description": "집주인의 다수 전세 계약 — 빌라왕 패턴",
        "severity": "HIGH", "keywords": "다수 전세 빌라왕 동일 건물",
        "advice": "등기부등본에서 임차권등기 다수 여부 확인",
        "laws": ["주택임대차보호법 제3조의3"],
    },
    {
        "factor_id": "RF010", "category": "절차",
        "description": "전세보증보험 미가입 — 보증금 반환 수단 없음",
        "severity": "MEDIUM", "keywords": "전세보증보험 HUG SGI",
        "advice": "HUG 전세보증금반환보증 또는 SGI서울보증 가입 권고",
        "laws": ["주택도시보증공사법 제16조"],
    },
]

# ── 헬퍼 함수 ─────────────────────────────────────────────

def run_query(query: str, params=None):
    with driver.session() as conn:
        result = conn.run(query=query, params=params)
        return [r for r in result]


# ── Step 1: 스키마 초기화 ─────────────────────────────────

def init_schema():
    print("[1/4] 스키마 초기화...")
    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:RiskFactor) REQUIRE n.factor_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Law)        REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Case)       REQUIRE n.name IS UNIQUE",
        "CREATE INDEX IF NOT EXISTS FOR (n:RiskFactor) ON (n.severity)",
        "CREATE INDEX IF NOT EXISTS FOR (n:RiskFactor) ON (n.category)",
    ]
    for stmt in constraints:
        run_query(stmt)
    print("  ✅ 스키마 초기화 완료")


# ── Step 2: 위험 요소 시드 데이터 적재 ───────────────────

def seed_risk_factors():
    print("[2/4] 위험 요소 시드 데이터 적재...")

    # RiskFactor 노드 생성/업데이트
    params = [
        {
            "factor_id":   rf["factor_id"],
            "category":    rf["category"],
            "description": rf["description"],
            "severity":    rf["severity"],
            "keywords":    rf["keywords"],
            "advice":      rf["advice"],
        }
        for rf in RISK_FACTORS
    ]

    query = """
    UNWIND $params as param
    MERGE (rf:RiskFactor {factor_id: param.factor_id})
    SET rf.category    = param.category,
        rf.description = param.description,
        rf.severity    = param.severity,
        rf.keywords    = param.keywords,
        rf.advice      = param.advice
    """
    run_query(query, params=params)

    # RiskFactor -[:REGULATED_BY]-> Law 관계 생성
    law_params = []
    for rf in RISK_FACTORS:
        for law in rf.get("laws", []):
            law_params.append({
                "factor_id": rf["factor_id"],
                "law_name":  law,
            })

    query = """
    UNWIND $params as param
    MERGE (l:Law {name: param.law_name})
    WITH l, param
    MATCH (rf:RiskFactor {factor_id: param.factor_id})
    MERGE (rf)-[:REGULATED_BY]->(l)
    """
    run_query(query, params=law_params)

    print(f"  ✅ 위험 요소 {len(RISK_FACTORS)}개 + 법령 관계 {len(law_params)}건 적재 완료")


# ── Step 3: 판례 → 법령 관계 추출 ───────────────────────

def extract_and_link_cases(pg_conn):
    print("[3/4] 판례 → 법령 관계 추출 및 적재...")

    cur = pg_conn.cursor()
    cur.execute("""
        SELECT title, chunk_text
        FROM rag_documents
        WHERE doc_type = '판례'
          AND LENGTH(chunk_text) > 50
        ORDER BY title, chunk_index
    """)
    rows = cur.fetchall()
    cur.close()

    print(f"  판례 청크 {len(rows)}개 처리 중...")

    # 판례별 인용 법령 수집
    case_law_map: dict[str, set] = {}
    for title, chunk_text in rows:
        case_name = title.replace(".pdf", "").strip()
        for law_base, article in LAW_PATTERN.findall(chunk_text):
            law_name = f"{law_base.strip()} {article.strip()}"
            case_law_map.setdefault(case_name, set()).add(law_name)

    # Case 노드 생성
    case_params = [{"name": name} for name in case_law_map]
    query = """
    UNWIND $params as param
    MERGE (c:Case {name: param.name})
    SET c.doc_type = '판례'
    """
    run_query(query, params=case_params)

    # Case -[:CITES]-> Law, Law -[:CITED_IN]-> Case 관계 생성
    rel_params = []
    for case_name, laws in case_law_map.items():
        for law_name in laws:
            rel_params.append({
                "case_name": case_name,
                "law_name":  law_name,
            })

    query = """
    UNWIND $params as param
    MERGE (l:Law {name: param.law_name})
    WITH l, param
    MATCH (c:Case {name: param.case_name})
    MERGE (c)-[:CITES]->(l)
    MERGE (l)-[:CITED_IN]->(c)
    """
    run_query(query, params=rel_params)

    print(f"  ✅ 판례 노드 {len(case_law_map)}개 + 판례-법령 관계 {len(rel_params)}건 적재 완료")


# ── Step 4: 사례집 → 위험 요소 관계 연결 ────────────────

def link_case_studies(pg_conn):
    print("[4/4] 사례집 → 위험 요소 관계 연결...")

    cur = pg_conn.cursor()
    cur.execute("""
        SELECT id, title, chunk_text
        FROM rag_documents
        WHERE doc_type = '사례집'
          AND LENGTH(chunk_text) > 50
        LIMIT 500
    """)
    rows = cur.fetchall()
    cur.close()

    print(f"  사례집 청크 {len(rows)}개 처리 중...")

    # Case 노드 생성
    case_params = [
        {
            "name":    f"사례_{row_id}",
            "summary": chunk_text[:200],
        }
        for row_id, title, chunk_text in rows
    ]

    query = """
    UNWIND $params as param
    MERGE (c:Case {name: param.name})
    SET c.doc_type = '사례집',
        c.summary  = param.summary
    """
    run_query(query, params=case_params)

    # Case -[:INVOLVES]-> RiskFactor, RiskFactor -[:EVIDENCED_BY]-> Case 관계 생성
    rel_params = []
    for row_id, title, chunk_text in rows:
        case_name = f"사례_{row_id}"
        for keyword, factor_id in RISK_KEYWORD_MAP.items():
            if keyword in chunk_text:
                rel_params.append({
                    "case_name": case_name,
                    "factor_id": factor_id,
                })

    if rel_params:
        query = """
        UNWIND $params as param
        MATCH (c:Case {name: param.case_name})
        MATCH (rf:RiskFactor {factor_id: param.factor_id})
        MERGE (c)-[:INVOLVES]->(rf)
        MERGE (rf)-[:EVIDENCED_BY]->(c)
        """
        run_query(query, params=rel_params)

    print(f"  ✅ 사례집 {len(rows)}개 청크 → 위험 요소 관계 {len(rel_params)}건 연결 완료")


# ── 메인 실행 ─────────────────────────────────────────────

def run():
    print("=" * 50)
    print("  Neo4j 지식 그래프 구축 시작")
    print("=" * 50)

    # Neo4j 연결 확인
    try:
        driver.verify_connectivity()
        print("✅ Neo4j 연결 성공\n")
    except Exception as e:
        print(f"❌ Neo4j 연결 실패: {e}")
        return

    # PostgreSQL 연결
    pg_conn = psycopg2.connect(**DB_CONFIG)

    init_schema()
    seed_risk_factors()
    extract_and_link_cases(pg_conn)
    link_case_studies(pg_conn)

    pg_conn.close()
    driver.close()

    print("\n" + "=" * 50)
    print("  🎉 Neo4j 지식 그래프 구축 완료!")
    print("=" * 50)


if __name__ == "__main__":
    run()
