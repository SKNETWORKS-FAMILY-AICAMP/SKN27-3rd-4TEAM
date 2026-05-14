"""
전세계약 위험 진단 에이전트 - Neo4j 그래프 스토어
(backend/app/core/graph_store.py 와 동일 로직, 임포트 경로만 수정)
"""

from __future__ import annotations
from neo4j import GraphDatabase, Driver
from rag_server.config import Settings

GRAPH_STOPWORDS = {
    "전세",
    "계약",
    "위험",
    "확인",
    "이유",
    "어떻게",
    "무엇",
    "하나요",
    "있나요",
    "알려줘",
}


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

    def get_risk_factors_by_keywords(self, keywords: list[str]) -> list[dict]:
        query = """
        UNWIND $keywords AS kw
        MATCH (rf:RiskFactor)
        WHERE rf.keywords CONTAINS kw OR rf.description CONTAINS kw
        OPTIONAL MATCH (rf)-[:REGULATED_BY]->(law:Law)
        OPTIONAL MATCH (rf)-[:EVIDENCED_BY]->(case:Case)
        RETURN DISTINCT
            rf.factor_id   AS factor_id,
            rf.category    AS category,
            rf.description AS description,
            rf.severity    AS severity,
            rf.advice      AS advice,
            collect(DISTINCT law.name)  AS laws,
            collect(DISTINCT case.name) AS cases
        ORDER BY
            CASE rf.severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END
        """
        with self._driver.session() as session:
            return [dict(r) for r in session.run(query, keywords=keywords)]

    def get_context_by_question(self, question: str, limit: int = 5) -> list[dict]:
        """Return normalized graph context for chat/RAG.

        The public shape is intentionally generic so the rest of the RAG stack
        is insulated from future Neo4j label/relationship changes.
        """
        keywords = _extract_graph_keywords(question)
        if not keywords:
            return []

        try:
            current = self._get_current_schema_context(keywords=keywords, limit=limit)
            if current:
                return current
        except Exception:
            pass

        try:
            return self._get_generic_schema_context(keywords=keywords, limit=limit)
        except Exception:
            return []

    def _get_current_schema_context(self, keywords: list[str], limit: int) -> list[dict]:
        query = """
        UNWIND $keywords AS kw
        MATCH (rf:RiskFactor)
        WHERE rf.keywords CONTAINS kw OR rf.description CONTAINS kw OR rf.category CONTAINS kw
        OPTIONAL MATCH (rf)-[:REGULATED_BY]->(law:Law)
        OPTIONAL MATCH (rf)-[:EVIDENCED_BY]->(case:Case)
        RETURN DISTINCT
            rf.factor_id   AS source_id,
            rf.category    AS title,
            rf.description AS summary,
            rf.severity    AS severity,
            rf.advice      AS advice,
            collect(DISTINCT law.name)  AS laws,
            collect(DISTINCT case.name) AS cases,
            labels(rf) AS labels
        ORDER BY
            CASE rf.severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END
        LIMIT $limit
        """
        with self._driver.session() as session:
            return [
                {
                    "source_id": row["source_id"],
                    "title": row["title"] or row["source_id"],
                    "summary": row["summary"] or "",
                    "severity": row["severity"],
                    "advice": row["advice"],
                    "laws": row["laws"] or [],
                    "cases": row["cases"] or [],
                    "labels": row["labels"] or [],
                    "schema": "current_risk_factor",
                }
                for row in session.run(query, keywords=keywords, limit=limit)
            ]

    def _get_generic_schema_context(self, keywords: list[str], limit: int) -> list[dict]:
        query = """
        MATCH (n)
        WHERE any(kw IN $keywords
            WHERE any(k IN keys(n) WHERE toLower(toString(n[k])) CONTAINS toLower(kw)))
        WITH n
        LIMIT $limit
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN
            elementId(n) AS node_id,
            labels(n) AS labels,
            properties(n) AS props,
            collect(DISTINCT {
                relationship: type(r),
                labels: labels(m),
                properties: properties(m)
            })[0..5] AS neighbors
        """
        with self._driver.session() as session:
            contexts: list[dict] = []
            for row in session.run(query, keywords=keywords, limit=limit):
                props = dict(row["props"] or {})
                title = _first_value(props, "name", "title", "category", "risk_type", "id") or row["node_id"]
                summary = _first_value(props, "description", "summary", "content", "advice", "text") or ""
                neighbors = [item for item in row["neighbors"] or [] if item.get("properties")]
                contexts.append(
                    {
                        "source_id": row["node_id"],
                        "title": str(title),
                        "summary": str(summary),
                        "severity": props.get("severity"),
                        "advice": props.get("advice"),
                        "laws": _neighbor_names(neighbors, {"Law", "LegalBasis", "Article"}),
                        "cases": _neighbor_names(neighbors, {"Case", "Precedent", "Incident"}),
                        "labels": row["labels"] or [],
                        "neighbors": neighbors,
                        "schema": "generic_property_search",
                    }
                )
            return contexts

    def get_all_risk_factors(self) -> list[dict]:
        query = """
        MATCH (rf:RiskFactor)
        OPTIONAL MATCH (rf)-[:REGULATED_BY]->(law:Law)
        RETURN rf.factor_id AS factor_id, rf.category AS category,
               rf.description AS description, rf.severity AS severity,
               rf.keywords AS keywords, rf.advice AS advice,
               collect(DISTINCT law.name) AS laws
        ORDER BY rf.factor_id
        """
        with self._driver.session() as session:
            return [dict(r) for r in session.run(query)]

    def init_schema(self) -> None:
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:RiskFactor) REQUIRE n.factor_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Law) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Case) REQUIRE n.name IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (n:RiskFactor) ON (n.severity)",
        ]
        with self._driver.session() as session:
            for stmt in constraints:
                session.run(stmt)

    def seed_risk_factors(self) -> None:
        risk_factors = [
            {"factor_id": "RF001", "category": "전세가율",
             "description": "전세가율 80% 초과 — 집값 대비 전세금이 지나치게 높아 경매 시 보증금 회수 불가 위험",
             "severity": "HIGH", "keywords": "전세가율 보증금 매매가",
             "advice": "KB부동산·호갱노노에서 시세 확인 후 전세가율 80% 미만 매물 선택",
             "laws": ["주택임대차보호법 제3조의3"]},
            {"factor_id": "RF002", "category": "권리관계",
             "description": "근저당·가압류 과다 — 선순위 권리 합계가 보증금을 초과하면 경매 시 손실",
             "severity": "HIGH", "keywords": "근저당 가압류 저당권 선순위",
             "advice": "계약 전 등기부등본 발급, 선순위 권리 합산액 확인",
             "laws": ["민법 제356조", "주택임대차보호법 제8조"]},
            {"factor_id": "RF003", "category": "권리관계",
             "description": "미등기·무허가 건물 — 등기가 없으면 임차인의 대항력 취득 자체 불가",
             "severity": "HIGH", "keywords": "미등기 무허가 건축물대장",
             "advice": "건축물대장·등기부등본 일치 여부 반드시 확인",
             "laws": ["주택임대차보호법 제3조"]},
            {"factor_id": "RF004", "category": "절차",
             "description": "계약금 현금 요구 — 사기 가능성 신호",
             "severity": "HIGH", "keywords": "현금 계약금 직접 입금",
             "advice": "계좌 이체 후 영수증 보관, 임대인 본인 계좌 확인",
             "laws": ["공인중개사법 제33조"]},
            {"factor_id": "RF005", "category": "절차",
             "description": "임대인 신원 미확인 — 계약서상 임대인과 등기부 소유자가 다른 경우",
             "severity": "HIGH", "keywords": "임대인 소유자 신분증 대리인",
             "advice": "신분증·등기권리증 대조, 대리인 계약 시 위임장·인감증명서 필수",
             "laws": ["공인중개사법 제25조"]},
            {"factor_id": "RF006", "category": "전세가율",
             "description": "전세가율 70~80% — 주의 구간, 시세 변동에 취약",
             "severity": "MEDIUM", "keywords": "전세가율",
             "advice": "전세보증보험(HUG/SGI) 가입 검토",
             "laws": ["주택도시보증공사법"]},
            {"factor_id": "RF007", "category": "특약",
             "description": "불리한 특약 조항 — 과도한 의무 전가",
             "severity": "MEDIUM", "keywords": "특약 원상복구 수리 책임",
             "advice": "특약 조항 법률 검토 후 협의",
             "laws": ["주택임대차보호법 제10조"]},
            {"factor_id": "RF008", "category": "절차",
             "description": "확정일자·전입신고 미이행 — 대항력과 우선변제권 미취득",
             "severity": "MEDIUM", "keywords": "확정일자 전입신고 대항력",
             "advice": "입주 당일 전입신고 + 확정일자 동시 취득 필수",
             "laws": ["주택임대차보호법 제3조의2"]},
            {"factor_id": "RF009", "category": "권리관계",
             "description": "집주인의 다수 전세 계약 — 빌라왕 패턴",
             "severity": "HIGH", "keywords": "다수 전세 빌라왕 동일 건물",
             "advice": "등기부등본에서 임차권등기 다수 여부 확인",
             "laws": ["주택임대차보호법 제3조의3"]},
            {"factor_id": "RF010", "category": "절차",
             "description": "전세보증보험 미가입 — 보증금 반환 수단 없음",
             "severity": "MEDIUM", "keywords": "전세보증보험 HUG SGI",
             "advice": "HUG 전세보증금반환보증 또는 SGI서울보증 가입 권고",
             "laws": ["주택도시보증공사법 제16조"]},
        ]

        with self._driver.session() as session:
            for rf in risk_factors:
                session.run(
                    """
                    MERGE (rf:RiskFactor {factor_id: $factor_id})
                    SET rf.category    = $category,
                        rf.description = $description,
                        rf.severity    = $severity,
                        rf.keywords    = $keywords,
                        rf.advice      = $advice
                    """,
                    **{k: v for k, v in rf.items() if k != "laws"},
                )
                for law in rf.get("laws", []):
                    session.run(
                        """
                        MERGE (l:Law {name: $law})
                        WITH l
                        MATCH (rf:RiskFactor {factor_id: $factor_id})
                        MERGE (rf)-[:REGULATED_BY]->(l)
                        """,
                        law=law, factor_id=rf["factor_id"],
                    )
        print(f"✅ Neo4j 시드 데이터 적재 완료: {len(risk_factors)}개 위험 요소")


def _extract_graph_keywords(text: str) -> list[str]:
    normalized = (
        text.replace("?", " ")
        .replace("!", " ")
        .replace(",", " ")
        .replace(".", " ")
        .replace("/", " ")
    )
    keywords: list[str] = []
    for token in normalized.split():
        token = token.strip("()[]{}\"'")
        if len(token) < 2 or token in GRAPH_STOPWORDS:
            continue
        keywords.append(token)
    domain_terms = [
        "신탁",
        "신탁원부",
        "대항력",
        "우선변제",
        "확정일자",
        "전입신고",
        "선순위",
        "보증금",
        "다가구",
        "근저당",
        "가압류",
        "임차권등기",
        "특약",
        "전세가율",
    ]
    for term in domain_terms:
        if term in text and term not in keywords:
            keywords.append(term)
    return keywords[:12]


def _first_value(data: dict, *keys: str):
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _neighbor_names(neighbors: list[dict], target_labels: set[str]) -> list[str]:
    names: list[str] = []
    for item in neighbors:
        labels = set(item.get("labels") or [])
        if labels and not labels.intersection(target_labels):
            continue
        props = item.get("properties") or {}
        value = _first_value(props, "name", "title", "article", "case_number", "id")
        if value and str(value) not in names:
            names.append(str(value))
    return names
