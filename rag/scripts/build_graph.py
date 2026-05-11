"""
전세계약 위험 진단 에이전트 - Neo4j 지식 그래프 구축 스크립트
역할: 법령·판례·위험요소 간 관계를 Neo4j 그래프로 저장

그래프 구조:
  (:RiskFactor) -[:REGULATED_BY]-> (:Law)
  (:RiskFactor) -[:EVIDENCED_BY]-> (:Case)
  (:Law)        -[:CITED_IN]->     (:Case)
  (:Case)       -[:INVOLVES]->     (:RiskFactor)

실행: python rag/scripts/build_graph.py
"""

import os
import sys
import psycopg2
from neo4j import GraphDatabase
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# ── 설정 ─────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "jeonse_risk"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "password"),
}

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "jeonse1234")


# ── 법령명 정규화 매핑 ────────────────────────────────────
# 문서에서 자주 등장하는 법령명을 표준 노드명으로 매핑

LAW_ALIASES = {
    "주택임대차보호법": "주택임대차보호법",
    "주임법": "주택임대차보호법",
    "민법": "민법",
    "공인중개사법": "공인중개사법",
    "주택도시보증공사법": "주택도시보증공사법",
    "부동산 거래신고 등에 관한 법률": "부동산거래신고법",
    "전세사기피해자 지원": "전세사기피해자특별법",
    "특별법": "전세사기피해자특별법",
}

# 법령 조문 패턴 (판례 텍스트에서 추출용)
import re
LAW_PATTERN = re.compile(
    r"(주택임대차보호법|공인중개사법|민법|주택도시보증공사법|전세사기피해자\s*특별법)"
    r"\s*(제\d+조(?:의\d+)?(?:\s*제\d+항)?)",
    re.IGNORECASE,
)

CASE_PATTERN = re.compile(
    r"(대법원|헌법재판소|고등법원|지방법원)\s+"
    r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})[.]?\s+"
    r"선고\s+([\w\d가-힣]+)\s+판결",
)


# ── Neo4j 스키마 초기화 ───────────────────────────────────

def init_schema(driver):
    """제약조건 + 인덱스 생성"""
    with driver.session() as session:
        stmts = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:RiskFactor) REQUIRE n.factor_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Law)        REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Case)       REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:CheckItem)  REQUIRE n.item_id IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (n:RiskFactor) ON (n.severity)",
            "CREATE INDEX IF NOT EXISTS FOR (n:RiskFactor) ON (n.category)",
        ]
        for stmt in stmts:
            session.run(stmt)
    print("✅ Neo4j 스키마 초기화 완료")


# ── 위험 요소 시드 데이터 적재 ────────────────────────────

def seed_risk_factors(driver):
    """위험 요소 + 법령 관계 적재 (GraphStore.seed_risk_factors와 동일 로직)"""
    # 백엔드 GraphStore의 seed 메서드를 재사용
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from app.config import get_settings
    from app.core.graph_store import GraphStore

    settings = get_settings()
    gs = GraphStore(settings)
    gs.init_schema()
    gs.seed_risk_factors()
    gs.close()


# ── 판례 문서에서 법령·판례 관계 추출 ────────────────────

def extract_and_link_cases(driver, pg_conn):
    """
    rag_documents 테이블의 판례 청크에서
    법령 인용 + 판결 정보를 추출하여 Neo4j에 연결.
    """
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

    print(f"판례 청크 {len(rows)}개에서 관계 추출 중...")

    case_law_pairs: dict[str, set] = {}  # case_name → {law_name, ...}

    for title, chunk_text in rows:
        # 판결 노드 이름 (파일명 기반)
        case_name = title.replace(".pdf", "").strip()

        # 법령 인용 추출
        law_matches = LAW_PATTERN.findall(chunk_text)
        for law_base, article in law_matches:
            law_name = f"{LAW_ALIASES.get(law_base.strip(), law_base.strip())} {article.strip()}"
            if case_name not in case_law_pairs:
                case_law_pairs[case_name] = set()
            case_law_pairs[case_name].add(law_name)

    # Neo4j에 적재
    with driver.session() as session:
        for case_name, laws in tqdm(case_law_pairs.items(), desc="판례-법령 관계 적재"):
            # Case 노드 생성
            session.run(
                "MERGE (c:Case {name: $name})",
                name=case_name,
            )
            # Law 노드 + 관계 생성
            for law_name in laws:
                session.run(
                    """
                    MERGE (l:Law {name: $law_name})
                    WITH l
                    MATCH (c:Case {name: $case_name})
                    MERGE (c)-[:CITES]->(l)
                    MERGE (l)-[:CITED_IN]->(c)
                    """,
                    law_name=law_name,
                    case_name=case_name,
                )

    print(f"✅ 판례-법령 관계 {sum(len(v) for v in case_law_pairs.values())}건 적재")


# ── 사례집에서 위험 요소 관계 연결 ───────────────────────

RISK_KEYWORD_MAP = {
    "전세가율": "RF001",
    "근저당": "RF002",
    "가압류": "RF002",
    "미등기": "RF003",
    "현금": "RF004",
    "소유자": "RF005",
    "확정일자": "RF008",
    "전입신고": "RF008",
    "전세보증보험": "RF010",
    "빌라왕": "RF009",
    "다수 전세": "RF009",
    "특약": "RF007",
}


def link_case_studies(driver, pg_conn):
    """사례집 청크를 Case 노드로 연결하고 위험 요소 관계 추가"""
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT id, title, chunk_text
        FROM rag_documents
        WHERE doc_type IN ('사례집')
          AND LENGTH(chunk_text) > 50
        LIMIT 500
    """)
    rows = cur.fetchall()
    cur.close()

    with driver.session() as session:
        for row_id, title, chunk_text in tqdm(rows, desc="사례집-위험요소 연결"):
            case_node_name = f"사례_{row_id}"
            session.run(
                """
                MERGE (c:Case {name: $name})
                SET c.doc_type = '사례집', c.summary = $summary
                """,
                name=case_node_name,
                summary=chunk_text[:200],
            )

            # 키워드 기반 위험 요소 연결
            for keyword, factor_id in RISK_KEYWORD_MAP.items():
                if keyword in chunk_text:
                    session.run(
                        """
                        MATCH (c:Case {name: $case_name})
                        MATCH (rf:RiskFactor {factor_id: $factor_id})
                        MERGE (c)-[:INVOLVES]->(rf)
                        MERGE (rf)-[:EVIDENCED_BY]->(c)
                        """,
                        case_name=case_node_name,
                        factor_id=factor_id,
                    )

    print(f"✅ 사례집 {len(rows)}개 청크 → 위험 요소 관계 연결 완료")


# ── 메인 실행 ─────────────────────────────────────────────

def run():
    print("=== Neo4j 지식 그래프 구축 시작 ===\n")

    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    )

    # 연결 확인
    try:
        driver.verify_connectivity()
        print("✅ Neo4j 연결 성공")
    except Exception as e:
        print(f"❌ Neo4j 연결 실패: {e}")
        return

    pg_conn = psycopg2.connect(**DB_CONFIG)

    # 1. 스키마 + 위험 요소 시드
    print("\n[1/3] 스키마 + 위험 요소 시드 적재...")
    init_schema(driver)
    seed_risk_factors(driver)

    # 2. 판례 → 법령 관계
    print("\n[2/3] 판례-법령 관계 추출 및 적재...")
    extract_and_link_cases(driver, pg_conn)

    # 3. 사례집 → 위험 요소 관계
    print("\n[3/3] 사례집-위험 요소 관계 연결...")
    link_case_studies(driver, pg_conn)

    pg_conn.close()
    driver.close()

    print("\n🎉 Neo4j 지식 그래프 구축 완료!")


if __name__ == "__main__":
    run()
