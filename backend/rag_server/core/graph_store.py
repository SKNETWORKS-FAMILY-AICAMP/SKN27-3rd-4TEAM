"""
전세계약 위험 진단 에이전트 - Neo4j 그래프 스토어 v2
LangGraph 설계서 기반 8종 노드·15+종 관계 쿼리 메서드 포함
"""

from __future__ import annotations

from neo4j import Driver, GraphDatabase

from rag_server.config import Settings


class GraphStore:
    def __init__(self, settings: Settings):
        self._driver: Driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )

    def close(self) -> None:
        self._driver.close()

    def is_ready(self) -> bool:
        try:
            self._driver.verify_connectivity()
            return True
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────
    # 기존 호환 메서드
    # ─────────────────────────────────────────────────────────

    def get_risk_factors_by_keywords(self, keywords: list[str]) -> list[dict]:
        """키워드로 RiskFactor 검색 (기존 호환)"""
        query = """
        UNWIND $keywords AS kw
        MATCH (rf:RiskFactor)
        WHERE rf.keywords CONTAINS kw OR rf.description CONTAINS kw
        OPTIONAL MATCH (rf)-[:REGULATED_BY]->(law:Law)
        OPTIONAL MATCH (rf)-[:EVIDENCED_BY]->(c:Case)
        OPTIONAL MATCH (rf)-[:RELATED_TO]->(lc:LegalConcept)
        RETURN DISTINCT
            rf.factor_id   AS factor_id,
            rf.category    AS category,
            rf.description AS description,
            rf.severity    AS severity,
            rf.advice      AS advice,
            collect(DISTINCT law.name)  AS laws,
            collect(DISTINCT c.name)    AS cases,
            collect(DISTINCT lc.name)   AS legal_concepts
        ORDER BY
            CASE rf.severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END
        """
        with self._driver.session() as session:
            return [dict(r) for r in session.run(query, keywords=keywords)]

    def get_all_risk_factors(self) -> list[dict]:
        """모든 RiskFactor 조회"""
        query = """
        MATCH (rf:RiskFactor)
        OPTIONAL MATCH (rf)-[:REGULATED_BY]->(law:Law)
        OPTIONAL MATCH (rf)-[:RELATED_TO]->(lc:LegalConcept)
        RETURN rf.factor_id AS factor_id, rf.category AS category,
               rf.description AS description, rf.severity AS severity,
               rf.keywords AS keywords, rf.advice AS advice,
               collect(DISTINCT law.name) AS laws,
               collect(DISTINCT lc.name)  AS legal_concepts
        ORDER BY rf.factor_id
        """
        with self._driver.session() as session:
            return [dict(r) for r in session.run(query)]

    # ─────────────────────────────────────────────────────────
    # v2 에이전트별 컨텍스트 메서드
    # ─────────────────────────────────────────────────────────

    def get_context_for_agent(
        self,
        agent_name: str,
        keywords: list[str] | None = None,
    ) -> list[dict]:
        """
        에이전트 이름으로 관련 RiskFactor·LegalConcept·Law·Procedure 컨텍스트 조회.

        반환 형식:
        [{"node": "대항력", "relation": "requires", "target": "전입신고"}, ...]
        """
        query = """
        MATCH (a:AgentScope {name: $agent_name})-[:DETECTED_BY]->(rf:RiskFactor)
        OPTIONAL MATCH (rf)-[:REGULATED_BY]->(law:Law)
        OPTIONAL MATCH (rf)-[:RELATED_TO]->(lc:LegalConcept)
        WITH rf, collect(DISTINCT law.name) AS laws, collect(DISTINCT lc.name) AS concepts
        RETURN
            rf.factor_id   AS node,
            'detected_by'  AS relation,
            rf.description AS target,
            rf.severity    AS severity,
            rf.advice      AS advice,
            laws,
            concepts
        ORDER BY
            CASE rf.severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END
        """
        with self._driver.session() as session:
            rows = [dict(r) for r in session.run(query, agent_name=agent_name)]

        # 키워드 필터 (옵션)
        if keywords:
            rows = [
                r for r in rows
                if any(kw in (r.get("target") or "") for kw in keywords)
            ]
        return rows

    def get_legal_concepts(self, keywords: list[str]) -> list[dict]:
        """
        키워드로 LegalConcept 및 연결된 요소 조회.

        반환 형식:
        [{"node": "대항력", "relation": "requires", "target": "전입신고"}, ...]
        """
        query = """
        UNWIND $keywords AS kw
        MATCH (lc:LegalConcept)
        WHERE lc.name CONTAINS kw OR lc.definition CONTAINS kw
        OPTIONAL MATCH (lc)-[:REQUIRES]->(req:LegalConcept)
        OPTIONAL MATCH (lc)-[:DEFINED_IN]->(law:Law)
        OPTIONAL MATCH (lc)<-[:RELATED_TO]-(rf:RiskFactor)
        RETURN DISTINCT
            lc.name       AS node,
            lc.definition AS definition,
            lc.law_ref    AS law_ref,
            collect(DISTINCT req.name)  AS requires,
            collect(DISTINCT law.name)  AS defined_in,
            collect(DISTINCT rf.factor_id) AS risk_factors
        """
        with self._driver.session() as session:
            raw = [dict(r) for r in session.run(query, keywords=keywords)]

        # graph_context 형식으로 변환
        result = []
        for r in raw:
            for req in r.get("requires", []):
                result.append({"node": r["node"], "relation": "requires", "target": req})
            for law in r.get("defined_in", []):
                result.append({"node": r["node"], "relation": "defined_in", "target": law})
            for rf_id in r.get("risk_factors", []):
                result.append({"node": r["node"], "relation": "related_to_risk", "target": rf_id})
            if not r.get("requires") and not r.get("defined_in"):
                result.append({
                    "node": r["node"],
                    "relation": "definition",
                    "target": r.get("definition", ""),
                })
        return result

    def get_related_context(
        self,
        keywords: list[str],
        domain: str | None = None,
    ) -> list[dict]:
        """
        키워드 + 도메인으로 그래프 컨텍스트 조회 (LegalConcept + RiskFactor + Law).

        반환 형식:
        [{"node": ..., "relation": ..., "target": ...}, ...]
        """
        domain_filter = "AND d.name = $domain" if domain else ""
        query = f"""
        UNWIND $keywords AS kw
        MATCH (rf:RiskFactor)
        WHERE rf.keywords CONTAINS kw OR rf.description CONTAINS kw
        OPTIONAL MATCH (rf)-[:REGULATED_BY]->(law:Law)
        OPTIONAL MATCH (rf)-[:RELATED_TO]->(lc:LegalConcept)
        OPTIONAL MATCH (rf)-[:BELONGS_TO]->(d:Domain)
        WHERE 1=1 {domain_filter}
        OPTIONAL MATCH (rf)-[:EVIDENCED_BY]->(c:Case)
        RETURN DISTINCT
            rf.factor_id   AS rf_id,
            rf.description AS rf_desc,
            rf.severity    AS severity,
            rf.advice      AS advice,
            collect(DISTINCT law.name)  AS laws,
            collect(DISTINCT lc.name)   AS concepts,
            collect(DISTINCT c.name)    AS cases
        ORDER BY
            CASE rf.severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END
        LIMIT 10
        """
        params: dict = {"keywords": keywords}
        if domain:
            params["domain"] = domain

        with self._driver.session() as session:
            raw = [dict(r) for r in session.run(query, **params)]

        result = []
        for r in raw:
            for law in r.get("laws", []):
                result.append({"node": r["rf_id"], "relation": "regulated_by", "target": law})
            for concept in r.get("concepts", []):
                result.append({"node": r["rf_id"], "relation": "related_to", "target": concept})
            for case in r.get("cases", []):
                result.append({"node": r["rf_id"], "relation": "evidenced_by", "target": case})
            if not r.get("laws") and not r.get("concepts"):
                result.append({
                    "node": r["rf_id"],
                    "relation": "description",
                    "target": r.get("rf_desc", ""),
                })
        return result

    def get_document_categories_for_agent(self, agent_name: str) -> list[dict]:
        """
        에이전트가 담당하는 DocumentCategory 목록 조회.
        RAG 검색 시 doc_type 필터에 활용.

        반환:
        [{"name": "판례", "source_type": "judicial", "domain": "법적절차"}, ...]
        """
        query = """
        MATCH (a:AgentScope {name: $agent_name})-[:COVERS]->(dc:DocumentCategory)
        OPTIONAL MATCH (dc)-[:BELONGS_TO]->(d:Domain)
        RETURN dc.name        AS name,
               dc.source_type AS source_type,
               dc.description AS description,
               d.name         AS domain
        ORDER BY dc.name
        """
        with self._driver.session() as session:
            return [dict(r) for r in session.run(query, agent_name=agent_name)]

    def get_procedures_for_concept(self, concept_name: str) -> list[dict]:
        """법률 개념과 연결된 절차 목록 조회"""
        query = """
        MATCH (p:Procedure)-[:RELATED_TO]->(lc:LegalConcept {name: $concept_name})
        RETURN p.name        AS name,
               p.order       AS order,
               p.timing      AS timing,
               p.description AS description
        ORDER BY p.order
        """
        with self._driver.session() as session:
            return [dict(r) for r in session.run(query, concept_name=concept_name)]

    def get_cases_by_risk_factor(
        self,
        factor_id: str,
        doc_type: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        특정 RiskFactor와 연결된 판례·사례집 조회.

        doc_type: '판례' | '사례집' | None (전체)
        """
        doc_filter = "AND c.doc_type = $doc_type" if doc_type else ""
        query = f"""
        MATCH (rf:RiskFactor {{factor_id: $factor_id}})-[:EVIDENCED_BY]->(c:Case)
        WHERE 1=1 {doc_filter}
        RETURN c.name    AS name,
               c.doc_type AS doc_type,
               c.summary  AS summary
        LIMIT $limit
        """
        params: dict = {"factor_id": factor_id, "limit": limit}
        if doc_type:
            params["doc_type"] = doc_type
        with self._driver.session() as session:
            return [dict(r) for r in session.run(query, **params)]

    def get_full_graph_context(self, keywords: list[str]) -> list[dict]:
        """
        키워드 기반 전체 그래프 컨텍스트 반환.
        RAG 응답의 graph_context 필드에 직접 삽입 가능한 형식.

        반환: [{"node": ..., "relation": ..., "target": ...}, ...]
        """
        context = []
        context.extend(self.get_legal_concepts(keywords))
        context.extend(self.get_related_context(keywords))
        # 중복 제거
        seen = set()
        unique = []
        for item in context:
            key = (item["node"], item["relation"], item["target"])
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique[:20]  # 최대 20개

    # ─────────────────────────────────────────────────────────
    # 초기화 (호환용)
    # ─────────────────────────────────────────────────────────

    def init_schema(self) -> None:
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:RiskFactor)       REQUIRE n.factor_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Law)              REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Case)             REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:LegalConcept)     REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Domain)           REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:DocumentCategory) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:AgentScope)       REQUIRE n.name IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (n:RiskFactor) ON (n.severity)",
        ]
        with self._driver.session() as session:
            for stmt in constraints:
                session.run(stmt)
