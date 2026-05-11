"""
전세계약 위험 진단 에이전트 - Neo4j 그래프 스토어
역할: 위험 요소 / 법령 / 판례 간 관계 쿼리

그래프 노드 설계:
  (:RiskFactor)  - 위험 요소 (예: 전세가율_80초과)
  (:Law)         - 법령 (예: 주택임대차보호법 제3조)
  (:Case)        - 판례 (예: 대법원 2019다12345)
  (:CheckItem)   - 체크리스트 항목

관계:
  (RiskFactor)-[:REGULATED_BY]->(Law)
  (RiskFactor)-[:EVIDENCED_BY]->(Case)
  (RiskFactor)-[:DETECTED_BY]->(CheckItem)
  (Law)-[:CITED_IN]->(Case)
"""

from __future__ import annotations
from typing import Any
from neo4j import GraphDatabase, Driver

from app.config import Settings


class GraphStore:
    """Neo4j 그래프 DB 래퍼"""

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

    # ── 핵심 쿼리 ─────────────────────────────────────────

    def get_risk_factors_by_keywords(self, keywords: list[str]) -> list[dict]:
        """
        키워드와 연관된 위험 요소 + 관련 법령/판례 조회.

        Args:
            keywords: 계약서에서 추출한 키워드 목록
                      (예: ['전세가율', '근저당', '미등기'])

        Returns:
            [{"factor_id", "description", "severity", "laws", "cases"}, ...]
        """
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
            CASE rf.severity
                WHEN 'HIGH'   THEN 1
                WHEN 'MEDIUM' THEN 2
                ELSE 3
            END
        """
        with self._driver.session() as session:
            result = session.run(query, keywords=keywords)
            return [dict(record) for record in result]

    def get_related_cases(self, law_name: str) -> list[dict]:
        """특정 법령과 연관된 판례 조회"""
        query = """
        MATCH (law:Law {name: $law_name})<-[:CITED_IN]-(case:Case)
        RETURN case.name AS name, case.summary AS summary, case.url AS url
        LIMIT 5
        """
        with self._driver.session() as session:
            result = session.run(query, law_name=law_name)
            return [dict(record) for record in result]

    def get_checklist_by_risk(self, risk_factor_id: str) -> list[str]:
        """위험 요소별 체크리스트 항목 조회"""
        query = """
        MATCH (rf:RiskFactor {factor_id: $factor_id})-[:DETECTED_BY]->(ci:CheckItem)
        RETURN ci.description AS item
        ORDER BY ci.order
        """
        with self._driver.session() as session:
            result = session.run(query, factor_id=risk_factor_id)
            return [record["item"] for record in result]

    def get_all_risk_factors(self) -> list[dict]:
        """모든 위험 요소 목록 (초기 진단 기준 로딩)"""
        query = """
        MATCH (rf:RiskFactor)
        OPTIONAL MATCH (rf)-[:REGULATED_BY]->(law:Law)
        RETURN
            rf.factor_id   AS factor_id,
            rf.category    AS category,
            rf.description AS description,
            rf.severity    AS severity,
            rf.keywords    AS keywords,
            rf.advice      AS advice,
            collect(DISTINCT law.name) AS laws
        ORDER BY rf.factor_id
        """
        with self._driver.session() as session:
            result = session.run(query)
            return [dict(record) for record in result]

    # ── 그래프 초기화 (최초 1회) ──────────────────────────

    def init_schema(self) -> None:
        """제약 조건 + 인덱스 생성"""
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
        """전세사기 핵심 위험 요소 초기 데이터 적재"""
        risk_factors = [
            {
                "factor_id": "RF001",
                "category": "전세가율",
                "description": "전세가율 80% 초과 - 집값 대비 전세금이 지나치게 높아 경매 시 보증금 회수 불가 위험",
                "severity": "HIGH",
                "keywords": "전세가율 보증금 매매가",
                "advice": "KB부동산·호갱노노에서 시세 확인 후 전세가율 80% 미만 매물 선택",
                "laws": ["주택임대차보호법 제3조의3"],
            },
            {
                "factor_id": "RF002",
                "category": "권리관계",
                "description": "근저당·가압류 과다 - 선순위 권리 합계가 보증금을 초과하면 경매 시 손실 발생",
                "severity": "HIGH",
                "keywords": "근저당 가압류 저당권 선순위",
                "advice": "계약 전 등기부등본 발급·열람, 선순위 권리 합산액 확인",
                "laws": ["민법 제356조", "주택임대차보호법 제8조"],
            },
            {
                "factor_id": "RF003",
                "category": "권리관계",
                "description": "미등기·무허가 건물 - 등기가 없으면 임차인의 대항력 취득 자체가 불가",
                "severity": "HIGH",
                "keywords": "미등기 무허가 건축물대장",
                "advice": "건축물대장·등기부등본 일치 여부 반드시 확인",
                "laws": ["주택임대차보호법 제3조"],
            },
            {
                "factor_id": "RF004",
                "category": "절차",
                "description": "계약금 현금 요구 - 중개인 또는 임대인이 계약금을 현금으로만 요구하는 경우 사기 가능성",
                "severity": "HIGH",
                "keywords": "현금 계약금 직접 입금",
                "advice": "계좌 이체 후 영수증 보관, 임대인 본인 계좌 확인",
                "laws": ["공인중개사법 제33조"],
            },
            {
                "factor_id": "RF005",
                "category": "절차",
                "description": "임대인 신원 미확인 - 계약서상 임대인과 등기부 소유자가 다른 경우",
                "severity": "HIGH",
                "keywords": "임대인 소유자 신분증 대리인",
                "advice": "신분증·등기권리증 대조, 대리인 계약 시 위임장·인감증명서 필수",
                "laws": ["공인중개사법 제25조"],
            },
            {
                "factor_id": "RF006",
                "category": "전세가율",
                "description": "전세가율 70~80% - 주의 구간, 시세 변동에 취약",
                "severity": "MEDIUM",
                "keywords": "전세가율",
                "advice": "전세보증보험(HUG/SGI) 가입 검토",
                "laws": ["주택도시보증공사법"],
            },
            {
                "factor_id": "RF007",
                "category": "특약",
                "description": "불리한 특약 조항 - '원상복구 비용 전액 임차인 부담' 등 과도한 의무 전가",
                "severity": "MEDIUM",
                "keywords": "특약 원상복구 수리 책임",
                "advice": "특약 조항 법률 검토 후 협의, 분쟁조정위원회 상담 활용",
                "laws": ["주택임대차보호법 제10조"],
            },
            {
                "factor_id": "RF008",
                "category": "절차",
                "description": "확정일자·전입신고 미이행 - 대항력과 우선변제권을 얻지 못하는 경우",
                "severity": "MEDIUM",
                "keywords": "확정일자 전입신고 대항력",
                "advice": "입주 당일 전입신고 + 확정일자 동시 취득 필수",
                "laws": ["주택임대차보호법 제3조의2"],
            },
            {
                "factor_id": "RF009",
                "category": "권리관계",
                "description": "집주인의 다수 전세 계약 - 한 집주인이 동일 건물에 과도한 전세를 두는 빌라왕 패턴",
                "severity": "HIGH",
                "keywords": "다수 전세 빌라왕 동일 건물",
                "advice": "등기부등본에서 임차권등기 다수 여부 확인",
                "laws": ["주택임대차보호법 제3조의3"],
            },
            {
                "factor_id": "RF010",
                "category": "절차",
                "description": "전세보증보험 미가입 - 임대인 파산·잠적 시 보증금 반환 수단 없음",
                "severity": "MEDIUM",
                "keywords": "전세보증보험 HUG SGI",
                "advice": "HUG 전세보증금반환보증 또는 SGI서울보증 가입 권고",
                "laws": ["주택도시보증공사법 제16조"],
            },
        ]

        law_nodes = {
            "주택임대차보호법 제3조": "주택임대차보호법 제3조 (대항력)",
            "주택임대차보호법 제3조의2": "주택임대차보호법 제3조의2 (확정일자·우선변제권)",
            "주택임대차보호법 제3조의3": "주택임대차보호법 제3조의3 (임차권등기명령)",
            "주택임대차보호법 제8조": "주택임대차보호법 제8조 (최우선변제)",
            "주택임대차보호법 제10조": "주택임대차보호법 제10조 (강행규정)",
            "민법 제356조": "민법 제356조 (저당권의 효력)",
            "공인중개사법 제25조": "공인중개사법 제25조 (중개대상물 확인·설명)",
            "공인중개사법 제33조": "공인중개사법 제33조 (금지행위)",
            "주택도시보증공사법": "주택도시보증공사법",
            "주택도시보증공사법 제16조": "주택도시보증공사법 제16조 (보증업무)",
        }

        with self._driver.session() as session:
            # 법령 노드 생성
            for law_id, law_name in law_nodes.items():
                session.run(
                    "MERGE (l:Law {name: $name})",
                    name=law_id,
                )

            # 위험 요소 노드 + 관계 생성
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
                        MATCH (rf:RiskFactor {factor_id: $factor_id})
                        MATCH (l:Law {name: $law})
                        MERGE (rf)-[:REGULATED_BY]->(l)
                        """,
                        factor_id=rf["factor_id"],
                        law=law,
                    )

        print(f"✅ Neo4j 시드 데이터 적재 완료: {len(risk_factors)}개 위험 요소")
