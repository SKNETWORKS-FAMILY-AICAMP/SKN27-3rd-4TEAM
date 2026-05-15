"""
Neo4j 그래프 빌더 — 추출된 판례 엔티티를 그래프로 저장

노드:
  - (:Case) 판례 — case_id, court, date, summary
  - (:Law)  법조문 — name
  - (:Issue) 쟁점 — name

관계:
  - (Case)-[:CITES_LAW]->(Law)
  - (Case)-[:CITES_CASE]->(Case)
  - (Case)-[:DEALS_WITH]->(Issue)
"""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv
from backend.graph.extract_entities import CaseEntity

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "jeonse1234")


def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def init_constraints(driver):
    """유니크 제약 생성"""
    with driver.session() as session:
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Case) REQUIRE c.case_id IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (l:Law) REQUIRE l.name IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (i:Issue) REQUIRE i.name IS UNIQUE")


def insert_entity(driver, entity: CaseEntity):
    """단일 엔티티를 그래프에 삽입"""
    with driver.session() as session:
        # Case 노드
        session.run("""
            MERGE (c:Case {case_id: $case_id})
            SET c.court = $court,
                c.date = $date,
                c.summary = $summary,
                c.filename = $filename
        """, case_id=entity.case_id, court=entity.court,
             date=entity.date, summary=entity.summary,
             filename=entity.filename)

        # Law 노드 + 관계
        for law in entity.cited_laws:
            session.run("""
                MERGE (l:Law {name: $law_name})
                WITH l
                MATCH (c:Case {case_id: $case_id})
                MERGE (c)-[:CITES_LAW]->(l)
            """, law_name=law, case_id=entity.case_id)

        # 인용 판례 관계
        for cited_id in entity.cited_cases:
            session.run("""
                MERGE (cited:Case {case_id: $cited_id})
                WITH cited
                MATCH (c:Case {case_id: $case_id})
                MERGE (c)-[:CITES_CASE]->(cited)
            """, cited_id=cited_id, case_id=entity.case_id)

        # Issue 노드 + 관계
        for issue in entity.issues:
            session.run("""
                MERGE (i:Issue {name: $issue_name})
                WITH i
                MATCH (c:Case {case_id: $case_id})
                MERGE (c)-[:DEALS_WITH]->(i)
            """, issue_name=issue, case_id=entity.case_id)


def build_graph(entities: list[CaseEntity]):
    """전체 엔티티 리스트를 Neo4j에 삽입"""
    driver = get_driver()
    init_constraints(driver)

    for i, entity in enumerate(entities, 1):
        if not entity.case_id:
            print(f"  [{i}] 스킵 (case_id 없음): {entity.filename}")
            continue
        insert_entity(driver, entity)
        print(f"  [{i}/{len(entities)}] {entity.court} {entity.case_id} 저장 완료")

    # 통계
    with driver.session() as session:
        cases = session.run("MATCH (c:Case) RETURN count(c) AS cnt").single()["cnt"]
        laws = session.run("MATCH (l:Law) RETURN count(l) AS cnt").single()["cnt"]
        issues = session.run("MATCH (i:Issue) RETURN count(i) AS cnt").single()["cnt"]
        rels = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt").single()["cnt"]

    print(f"\n=== 그래프 통계 ===")
    print(f"판례: {cases}개 / 법조문: {laws}개 / 쟁점: {issues}개 / 관계: {rels}개")

    driver.close()


def query_by_issue(issue_keyword: str) -> list[dict]:
    """쟁점 키워드로 관련 판례 + 법조문 조회"""
    driver = get_driver()
    with driver.session() as session:
        result = session.run("""
            MATCH (i:Issue)
            WHERE i.name CONTAINS $keyword
            MATCH (c:Case)-[:DEALS_WITH]->(i)
            OPTIONAL MATCH (c)-[:CITES_LAW]->(l:Law)
            OPTIONAL MATCH (c)-[:CITES_CASE]->(cited:Case)
            RETURN c.case_id AS case_id,
                   c.court AS court,
                   c.date AS date,
                   c.summary AS summary,
                   collect(DISTINCT l.name) AS laws,
                   collect(DISTINCT cited.case_id) AS cited_cases,
                   collect(DISTINCT i.name) AS issues
            ORDER BY c.date DESC
        """, keyword=issue_keyword)

        records = [dict(r) for r in result]
    driver.close()
    return records


def query_related_cases(case_id: str, depth: int = 2) -> list[dict]:
    """특정 판례에서 depth단계까지 연결된 판례 탐색"""
    driver = get_driver()
    with driver.session() as session:
        result = session.run(f"""
            MATCH path = (c:Case {{case_id: $case_id}})-[*1..{depth}]-(related:Case)
            WHERE related.case_id <> $case_id
            OPTIONAL MATCH (related)-[:DEALS_WITH]->(i:Issue)
            OPTIONAL MATCH (related)-[:CITES_LAW]->(l:Law)
            RETURN DISTINCT related.case_id AS case_id,
                   related.court AS court,
                   related.summary AS summary,
                   collect(DISTINCT i.name) AS issues,
                   collect(DISTINCT l.name) AS laws
        """, case_id=case_id)

        records = [dict(r) for r in result]
    driver.close()
    return records
