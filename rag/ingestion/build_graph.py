"""
전세계약 위험 진단 에이전트 - Neo4j 지식 그래프 구축 스크립트 v2
역할: LangGraph 설계서 기반 8종 노드·15+종 관계 그래프 구축

그래프 노드 종류:
  (:Domain)           - 법률 도메인 (계약, 등기, 보증, 법적절차 등)
  (:DocumentCategory) - RAG 문서 카테고리 (판례, 법령, 서식, 사례집, 보고서 등)
  (:AgentScope)       - LangGraph 에이전트 담당 영역
  (:LegalConcept)     - 법률 개념 (대항력, 우선변제권, 확정일자 등)
  (:Procedure)        - 임차인 절차 (전입신고, 확정일자, 임차권등기명령 등)
  (:RiskFactor)       - 위험 요소 (RF001~RF012)
  (:Law)              - 개별 법령 조문
  (:Case)             - 판례 / 사례집 항목

주요 관계:
  REGULATED_BY, EVIDENCED_BY, MITIGATED_BY, BELONGS_TO, DETECTED_BY,
  CITES, CITED_IN, INVOLVES, DEMONSTRATES, REQUIRES, RELATED_TO,
  DEFINED_IN, RESOLVES, GOVERNED_BY, USED_BY, COVERS, IN_CATEGORY

실행: python rag/ingestion/build_graph.py
"""

from __future__ import annotations

import os
import re

import psycopg2
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

# ── Neo4j 연결 ────────────────────────────────────────────

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "jeonse1234")

driver = GraphDatabase.driver(uri=NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# ── PostgreSQL 연결 ───────────────────────────────────────

DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME",     "jeonse_risk"),
    "user":     os.getenv("DB_USER",     "postgres"),
    "password": os.getenv("DB_PASSWORD", "risk1234"),
}

# ── 법령 인식 패턴 ────────────────────────────────────────

LAW_PATTERN = re.compile(
    r"(주택임대차보호법|공인중개사법|민법|주택도시보증공사법|전세사기피해자\s*특별법|부동산등기법|민사집행법|소액사건심판법)"
    r"\s*(제\d+조(?:의\d+)?(?:\s*제\d+항)?)",
    re.IGNORECASE,
)

RISK_KEYWORD_MAP = {
    "전세가율":     "RF001",
    "깡통전세":     "RF001",
    "근저당":       "RF002",
    "가압류":       "RF002",
    "저당권":       "RF002",
    "미등기":       "RF003",
    "무허가":       "RF003",
    "현금":         "RF004",
    "계약금":       "RF004",
    "소유자":       "RF005",
    "임대인":       "RF005",
    "전세가율 70":  "RF006",
    "특약":         "RF007",
    "확정일자":     "RF008",
    "전입신고":     "RF008",
    "다수 전세":    "RF009",
    "빌라왕":       "RF009",
    "전세보증보험": "RF010",
    "HUG":          "RF010",
    "신탁등기":     "RF011",
    "계약갱신":     "RF012",
}

# ─────────────────────────────────────────────────────────
# 시드 데이터
# ─────────────────────────────────────────────────────────

DOMAINS = [
    {"name": "계약",       "description": "전세계약 체결·갱신·해지 관련 법률 영역"},
    {"name": "등기",       "description": "부동산 등기, 권리관계 분석 영역"},
    {"name": "보증",       "description": "전세보증보험, 보증기관 관련 영역"},
    {"name": "법적절차",   "description": "내용증명, 임차권등기명령, 소송 관련 영역"},
    {"name": "시장분석",   "description": "전세가율, 시세 분석 영역"},
    {"name": "특약검토",   "description": "계약서 특약조항 법률 검토 영역"},
    {"name": "사기피해",   "description": "전세사기 유형 및 피해 구제 영역"},
]

# 10개 문서 카테고리 (rag_agent_workflow_design.md 기준)
DOC_CATEGORIES = [
    {
        "name": "판례",
        "description": "법원 판결문 — 임차인 보호·전세사기 관련 판결",
        "source_type": "judicial",
        "domain": "법적절차",
    },
    {
        "name": "법령",
        "description": "주택임대차보호법·민법 등 법령 원문",
        "source_type": "legislative",
        "domain": "계약",
    },
    {
        "name": "서식",
        "description": "전세계약서 표준서식, 내용증명 양식 등",
        "source_type": "form",
        "domain": "계약",
    },
    {
        "name": "사례집",
        "description": "전세사기 피해 사례 모음 (국토부·소비자원 등)",
        "source_type": "case_collection",
        "domain": "사기피해",
    },
    {
        "name": "가이드",
        "description": "임차인 권리·절차 안내 가이드",
        "source_type": "guide",
        "domain": "계약",
    },
    {
        "name": "보고서",
        "description": "전세시장 분석 보고서, 정책 연구 보고서",
        "source_type": "report",
        "domain": "시장분석",
    },
    {
        "name": "보증약관",
        "description": "HUG·SGI 전세보증보험 약관 및 안내",
        "source_type": "insurance",
        "domain": "보증",
    },
    {
        "name": "질의응답",
        "description": "국민신문고·법률구조공단 Q&A",
        "source_type": "faq",
        "domain": "법적절차",
    },
    {
        "name": "정책자료",
        "description": "정부 전세사기 대책, 제도 변경 자료",
        "source_type": "policy",
        "domain": "사기피해",
    },
    {
        "name": "시세데이터",
        "description": "국토부 실거래가, KB 시세 통계",
        "source_type": "market_data",
        "domain": "시장분석",
    },
]

# 8개 에이전트 스코프 (rag_agent_workflow_design.md 기준)
AGENT_SCOPES = [
    {
        "name": "special_clause_agent",
        "display_name": "특약 검토 에이전트",
        "description": "계약서 특약조항 법적 유·불리 분석",
        "doc_categories": ["서식", "법령", "판례"],
        "domains": ["특약검토", "계약"],
    },
    {
        "name": "ownership_risk_agent",
        "display_name": "등기·권리 분석 에이전트",
        "description": "등기부등본 근저당·압류·미등기 위험 분석",
        "doc_categories": ["판례", "법령", "사례집"],
        "domains": ["등기", "사기피해"],
    },
    {
        "name": "market_risk_agent",
        "display_name": "시장 위험 분석 에이전트",
        "description": "전세가율·시세 분석으로 깡통전세 위험 평가",
        "doc_categories": ["시세데이터", "보고서"],
        "domains": ["시장분석"],
    },
    {
        "name": "insurance_risk_agent",
        "display_name": "보증보험 분석 에이전트",
        "description": "전세보증보험 가입 가능 여부·조건 분석",
        "doc_categories": ["보증약관", "정책자료"],
        "domains": ["보증"],
    },
    {
        "name": "required_check_agent",
        "display_name": "필수 확인사항 에이전트",
        "description": "전입신고·확정일자 등 임차인 필수 절차 점검",
        "doc_categories": ["가이드", "서식", "법령"],
        "domains": ["계약", "법적절차"],
    },
    {
        "name": "legal_basis_agent",
        "display_name": "법적 근거 제시 에이전트",
        "description": "위험 요소별 법령 조문 및 판례 근거 제시",
        "doc_categories": ["법령", "판례"],
        "domains": ["계약", "법적절차", "등기"],
    },
    {
        "name": "legal_rag_agent",
        "display_name": "법률 RAG 검색 에이전트",
        "description": "pgvector + Neo4j 하이브리드 검색으로 법률 문서 조회",
        "doc_categories": ["판례", "법령", "사례집", "가이드", "질의응답"],
        "domains": ["계약", "법적절차", "사기피해"],
    },
    {
        "name": "friendly_counselor_agent",
        "display_name": "친절 상담 에이전트",
        "description": "비전문가 임차인에게 이해하기 쉬운 언어로 종합 안내",
        "doc_categories": ["가이드", "질의응답", "사례집"],
        "domains": ["계약", "사기피해"],
    },
]

# 15개 법률 개념 노드
LEGAL_CONCEPTS = [
    {
        "name": "대항력",
        "definition": "임차인이 주택을 인도받고 전입신고를 완료한 익일부터 제3자에 대해 임차권을 주장할 수 있는 권리",
        "law_ref": "주택임대차보호법 제3조",
        "domain": "계약",
        "requires": ["전입신고"],
    },
    {
        "name": "우선변제권",
        "definition": "확정일자를 받은 임차인이 경매·공매 시 후순위 권리자보다 먼저 보증금을 변제받을 수 있는 권리",
        "law_ref": "주택임대차보호법 제3조의2",
        "domain": "계약",
        "requires": ["전입신고", "확정일자"],
    },
    {
        "name": "최우선변제권",
        "definition": "소액임차인이 선순위 담보권보다 우선하여 보증금 일부를 변제받을 수 있는 권리",
        "law_ref": "주택임대차보호법 제8조",
        "domain": "계약",
        "requires": ["전입신고"],
    },
    {
        "name": "전입신고",
        "definition": "임차인이 주민등록법에 따라 주소를 이전하는 행위. 대항력·우선변제권 취득의 전제조건",
        "law_ref": "주민등록법 제16조",
        "domain": "계약",
        "requires": [],
    },
    {
        "name": "확정일자",
        "definition": "임대차계약서에 법원·읍면동사무소 등이 날인하는 일자. 우선변제권 취득 기준일",
        "law_ref": "주택임대차보호법 제3조의2",
        "domain": "계약",
        "requires": [],
    },
    {
        "name": "임차권등기",
        "definition": "임차인의 임차권을 부동산 등기부에 공시하는 제도",
        "law_ref": "주택임대차보호법 제3조의3",
        "domain": "등기",
        "requires": ["전입신고"],
    },
    {
        "name": "임차권등기명령",
        "definition": "임대차 종료 후 보증금을 반환받지 못한 임차인이 법원에 신청하여 단독으로 임차권등기를 마칠 수 있는 제도",
        "law_ref": "주택임대차보호법 제3조의3 제1항",
        "domain": "법적절차",
        "requires": ["임차권등기"],
    },
    {
        "name": "보증금 반환",
        "definition": "임대차 종료 시 임대인이 임차인에게 보증금 전액을 반환할 의무",
        "law_ref": "민법 제618조",
        "domain": "계약",
        "requires": [],
    },
    {
        "name": "동시이행",
        "definition": "보증금 반환과 주택 인도가 동시에 이루어져야 하는 원칙",
        "law_ref": "민법 제536조",
        "domain": "계약",
        "requires": ["보증금 반환"],
    },
    {
        "name": "깡통전세",
        "definition": "전세가율이 80% 이상으로 경매 시 보증금 전액 회수가 불가능한 위험 상태",
        "law_ref": None,
        "domain": "시장분석",
        "requires": [],
    },
    {
        "name": "전세가율",
        "definition": "매매가 대비 전세보증금의 비율. 80% 초과 시 깡통전세 위험",
        "law_ref": None,
        "domain": "시장분석",
        "requires": [],
    },
    {
        "name": "계약갱신청구권",
        "definition": "임차인이 임대차 기간 만료 전 계약갱신을 청구할 수 있는 권리. 1회에 한해 행사 가능",
        "law_ref": "주택임대차보호법 제6조의3",
        "domain": "계약",
        "requires": [],
    },
    {
        "name": "내용증명",
        "definition": "우체국을 통해 발송한 문서의 내용과 발송 사실을 증명하는 제도. 분쟁 시 증거로 활용",
        "law_ref": "우편법 제15조",
        "domain": "법적절차",
        "requires": [],
    },
    {
        "name": "신탁등기",
        "definition": "부동산 소유자가 신탁회사에 소유권을 이전하는 등기. 임차인이 임대인으로 잘못 인식하는 위험 있음",
        "law_ref": "신탁법 제2조",
        "domain": "등기",
        "requires": [],
    },
    {
        "name": "점유",
        "definition": "임차인이 실제로 주택을 사용·수익하는 사실 상태. 대항력 취득의 전제",
        "law_ref": "민법 제192조",
        "domain": "계약",
        "requires": [],
    },
]

# 7개 절차 노드
PROCEDURES = [
    {
        "name": "전입신고",
        "order": 1,
        "timing": "입주 당일",
        "description": "주민센터 방문 또는 정부24 온라인 신청",
        "legal_concept": "대항력",
        "domain": "계약",
    },
    {
        "name": "확정일자 취득",
        "order": 2,
        "timing": "전입신고 당일",
        "description": "주민센터·법원·공증사무소 방문 또는 인터넷등기소 신청",
        "legal_concept": "우선변제권",
        "domain": "계약",
    },
    {
        "name": "전세보증보험 가입",
        "order": 3,
        "timing": "계약 후 1개월 이내",
        "description": "HUG 또는 SGI서울보증 신청",
        "legal_concept": "보증금 반환",
        "domain": "보증",
    },
    {
        "name": "등기부등본 확인",
        "order": 0,
        "timing": "계약 전",
        "description": "인터넷등기소에서 열람. 근저당·가압류·신탁등기 여부 확인",
        "legal_concept": "임차권등기",
        "domain": "등기",
    },
    {
        "name": "임차권등기명령 신청",
        "order": 5,
        "timing": "임대차 종료 후 미반환 시",
        "description": "관할 지방법원에 신청. 이사 후에도 대항력·우선변제권 유지",
        "legal_concept": "임차권등기명령",
        "domain": "법적절차",
    },
    {
        "name": "내용증명 발송",
        "order": 4,
        "timing": "계약 만료 6개월~2개월 전",
        "description": "보증금 반환 요청 내용증명 발송",
        "legal_concept": "내용증명",
        "domain": "법적절차",
    },
    {
        "name": "보증금 반환 소송",
        "order": 6,
        "timing": "내용증명 후 미반환 시",
        "description": "소액사건심판 또는 민사소송 제기",
        "legal_concept": "보증금 반환",
        "domain": "법적절차",
    },
]

# 12개 위험 요소 노드 (RF001~RF012)
RISK_FACTORS = [
    {
        "factor_id": "RF001",
        "category": "전세가율",
        "description": "전세가율 80% 초과 — 집값 대비 전세금이 지나치게 높아 경매 시 보증금 회수 불가 위험",
        "severity": "HIGH",
        "keywords": "전세가율 보증금 매매가 깡통전세",
        "advice": "KB부동산·호갱노노에서 시세 확인 후 전세가율 80% 미만 매물 선택",
        "laws": ["주택임대차보호법 제3조의3"],
        "legal_concepts": ["전세가율", "깡통전세"],
        "domains": ["시장분석"],
        "detected_by_agents": ["market_risk_agent"],
        "doc_categories": ["시세데이터", "보고서"],
    },
    {
        "factor_id": "RF002",
        "category": "권리관계",
        "description": "근저당·가압류 과다 — 선순위 권리 합계가 보증금을 초과하면 경매 시 손실",
        "severity": "HIGH",
        "keywords": "근저당 가압류 저당권 선순위",
        "advice": "계약 전 등기부등본 발급, 선순위 권리 합산액 확인",
        "laws": ["민법 제356조", "주택임대차보호법 제8조"],
        "legal_concepts": ["우선변제권", "최우선변제권"],
        "domains": ["등기"],
        "detected_by_agents": ["ownership_risk_agent"],
        "doc_categories": ["판례", "법령"],
    },
    {
        "factor_id": "RF003",
        "category": "권리관계",
        "description": "미등기·무허가 건물 — 등기가 없으면 임차인의 대항력 취득 자체 불가",
        "severity": "HIGH",
        "keywords": "미등기 무허가 건축물대장",
        "advice": "건축물대장·등기부등본 일치 여부 반드시 확인",
        "laws": ["주택임대차보호법 제3조"],
        "legal_concepts": ["대항력"],
        "domains": ["등기"],
        "detected_by_agents": ["ownership_risk_agent"],
        "doc_categories": ["판례", "사례집"],
    },
    {
        "factor_id": "RF004",
        "category": "절차",
        "description": "계약금 현금 요구 — 사기 가능성 신호",
        "severity": "HIGH",
        "keywords": "현금 계약금 직접 입금",
        "advice": "계좌 이체 후 영수증 보관, 임대인 본인 계좌 확인",
        "laws": ["공인중개사법 제33조"],
        "legal_concepts": ["보증금 반환"],
        "domains": ["사기피해"],
        "detected_by_agents": ["ownership_risk_agent", "required_check_agent"],
        "doc_categories": ["사례집", "정책자료"],
    },
    {
        "factor_id": "RF005",
        "category": "절차",
        "description": "임대인 신원 미확인 — 계약서상 임대인과 등기부 소유자가 다른 경우",
        "severity": "HIGH",
        "keywords": "임대인 소유자 신분증 대리인",
        "advice": "신분증·등기권리증 대조, 대리인 계약 시 위임장·인감증명서 필수",
        "laws": ["공인중개사법 제25조"],
        "legal_concepts": ["대항력"],
        "domains": ["계약", "사기피해"],
        "detected_by_agents": ["ownership_risk_agent", "required_check_agent"],
        "doc_categories": ["서식", "가이드"],
    },
    {
        "factor_id": "RF006",
        "category": "전세가율",
        "description": "전세가율 70~80% — 주의 구간, 시세 변동에 취약",
        "severity": "MEDIUM",
        "keywords": "전세가율 70 80",
        "advice": "전세보증보험(HUG/SGI) 가입 검토",
        "laws": ["주택도시보증공사법"],
        "legal_concepts": ["전세가율"],
        "domains": ["시장분석", "보증"],
        "detected_by_agents": ["market_risk_agent", "insurance_risk_agent"],
        "doc_categories": ["시세데이터", "보증약관"],
    },
    {
        "factor_id": "RF007",
        "category": "특약",
        "description": "불리한 특약 조항 — 과도한 원상복구·수리 책임 전가",
        "severity": "MEDIUM",
        "keywords": "특약 원상복구 수리 책임",
        "advice": "특약 조항 법률 검토 후 협의, 표준계약서 활용",
        "laws": ["주택임대차보호법 제10조"],
        "legal_concepts": ["계약갱신청구권"],
        "domains": ["특약검토"],
        "detected_by_agents": ["special_clause_agent"],
        "doc_categories": ["서식", "법령", "판례"],
    },
    {
        "factor_id": "RF008",
        "category": "절차",
        "description": "확정일자·전입신고 미이행 — 대항력과 우선변제권 미취득",
        "severity": "MEDIUM",
        "keywords": "확정일자 전입신고 대항력 우선변제권",
        "advice": "입주 당일 전입신고 + 확정일자 동시 취득 필수",
        "laws": ["주택임대차보호법 제3조의2"],
        "legal_concepts": ["대항력", "우선변제권", "확정일자", "전입신고"],
        "domains": ["계약"],
        "detected_by_agents": ["required_check_agent", "legal_basis_agent"],
        "doc_categories": ["가이드", "법령"],
    },
    {
        "factor_id": "RF009",
        "category": "권리관계",
        "description": "집주인의 다수 전세 계약 — 빌라왕 패턴, 보증금 돌려막기 위험",
        "severity": "HIGH",
        "keywords": "다수 전세 빌라왕 동일 건물 임차권등기",
        "advice": "등기부등본에서 임차권등기 다수 여부 확인",
        "laws": ["주택임대차보호법 제3조의3"],
        "legal_concepts": ["임차권등기"],
        "domains": ["사기피해", "등기"],
        "detected_by_agents": ["ownership_risk_agent"],
        "doc_categories": ["사례집", "정책자료"],
    },
    {
        "factor_id": "RF010",
        "category": "절차",
        "description": "전세보증보험 미가입 — 보증금 반환 수단 없음",
        "severity": "MEDIUM",
        "keywords": "전세보증보험 HUG SGI",
        "advice": "HUG 전세보증금반환보증 또는 SGI서울보증 가입 권고",
        "laws": ["주택도시보증공사법 제16조"],
        "legal_concepts": ["보증금 반환"],
        "domains": ["보증"],
        "detected_by_agents": ["insurance_risk_agent"],
        "doc_categories": ["보증약관", "가이드"],
    },
    {
        "factor_id": "RF011",
        "category": "권리관계",
        "description": "신탁등기 주택 임대 — 수탁자(신탁회사) 동의 없는 임대차는 무효 위험",
        "severity": "HIGH",
        "keywords": "신탁등기 신탁회사 수탁자 위탁자",
        "advice": "신탁원부 확인 및 수탁자 동의서 받기. 신탁 해지 후 계약 권고",
        "laws": ["신탁법 제2조", "주택임대차보호법 제3조"],
        "legal_concepts": ["신탁등기", "대항력"],
        "domains": ["등기"],
        "detected_by_agents": ["ownership_risk_agent", "legal_basis_agent"],
        "doc_categories": ["판례", "법령", "사례집"],
    },
    {
        "factor_id": "RF012",
        "category": "계약갱신",
        "description": "계약갱신청구권 미행사 — 2년 연장 기회 상실 위험",
        "severity": "MEDIUM",
        "keywords": "계약갱신청구권 갱신 거절 2년 연장",
        "advice": "임대차 만료 6개월~2개월 전에 서면으로 계약갱신청구권 행사",
        "laws": ["주택임대차보호법 제6조의3"],
        "legal_concepts": ["계약갱신청구권"],
        "domains": ["계약"],
        "detected_by_agents": ["special_clause_agent", "required_check_agent"],
        "doc_categories": ["법령", "가이드"],
    },
]


# ─────────────────────────────────────────────────────────
# 헬퍼 함수
# ─────────────────────────────────────────────────────────

def run_query(query: str, params=None):
    with driver.session() as session:
        # UNWIND $params 쿼리는 리스트를 {"params": [...]} 형태로 감싸야 함
        if isinstance(params, list):
            parameters = {"params": params}
        elif isinstance(params, dict):
            parameters = params
        else:
            parameters = {}
        result = session.run(query=query, parameters=parameters)
        return [r for r in result]


# ─────────────────────────────────────────────────────────
# Step 1: 스키마 초기화
# ─────────────────────────────────────────────────────────

def init_schema():
    print("[1/8] 스키마 초기화...")
    stmts = [
        # 고유 제약조건
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:RiskFactor)       REQUIRE n.factor_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Law)              REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Case)             REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:LegalConcept)     REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Domain)           REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:DocumentCategory) REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Procedure)        REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:AgentScope)       REQUIRE n.name IS UNIQUE",
        # 인덱스
        "CREATE INDEX IF NOT EXISTS FOR (n:RiskFactor) ON (n.severity)",
        "CREATE INDEX IF NOT EXISTS FOR (n:RiskFactor) ON (n.category)",
        "CREATE INDEX IF NOT EXISTS FOR (n:Case)       ON (n.doc_type)",
        "CREATE INDEX IF NOT EXISTS FOR (n:Law)        ON (n.domain)",
    ]
    for stmt in stmts:
        run_query(stmt)
    print("  ✅ 스키마 초기화 완료 (8 제약조건 + 4 인덱스)")


# ─────────────────────────────────────────────────────────
# Step 2: Domain 노드 시드
# ─────────────────────────────────────────────────────────

def seed_domains():
    print("[2/8] Domain 노드 시드...")
    query = """
    UNWIND $params AS p
    MERGE (d:Domain {name: p.name})
    SET d.description = p.description
    """
    run_query(query, params=DOMAINS)
    print(f"  ✅ Domain {len(DOMAINS)}개 적재 완료")


# ─────────────────────────────────────────────────────────
# Step 3: DocumentCategory + AgentScope 노드 시드 및 관계 연결
# ─────────────────────────────────────────────────────────

def seed_doc_categories_and_agents():
    print("[3/8] DocumentCategory + AgentScope 시드...")

    # DocumentCategory 노드 생성
    cat_query = """
    UNWIND $params AS p
    MERGE (dc:DocumentCategory {name: p.name})
    SET dc.description = p.description,
        dc.source_type = p.source_type
    WITH dc, p
    MATCH (d:Domain {name: p.domain})
    MERGE (dc)-[:BELONGS_TO]->(d)
    """
    run_query(cat_query, params=DOC_CATEGORIES)

    # AgentScope 노드 생성 + 관계 연결
    for agent in AGENT_SCOPES:
        agent_query = """
        MERGE (a:AgentScope {name: $name})
        SET a.display_name = $display_name,
            a.description  = $description
        """
        run_query(agent_query, params={
            "name": agent["name"],
            "display_name": agent["display_name"],
            "description": agent["description"],
        })

        # AgentScope -[:COVERS]-> DocumentCategory
        for cat_name in agent["doc_categories"]:
            run_query("""
            MATCH (a:AgentScope {name: $agent_name})
            MATCH (dc:DocumentCategory {name: $cat_name})
            MERGE (a)-[:COVERS]->(dc)
            """, params={"agent_name": agent["name"], "cat_name": cat_name})

        # AgentScope -[:GOVERNED_BY]-> Domain
        for domain_name in agent["domains"]:
            run_query("""
            MATCH (a:AgentScope {name: $agent_name})
            MATCH (d:Domain {name: $domain_name})
            MERGE (a)-[:GOVERNED_BY]->(d)
            """, params={"agent_name": agent["name"], "domain_name": domain_name})

    print(f"  ✅ DocumentCategory {len(DOC_CATEGORIES)}개 + AgentScope {len(AGENT_SCOPES)}개 적재 완료")


# ─────────────────────────────────────────────────────────
# Step 4: LegalConcept 노드 시드
# ─────────────────────────────────────────────────────────

def seed_legal_concepts():
    print("[4/8] LegalConcept 노드 시드...")

    for concept in LEGAL_CONCEPTS:
        # LegalConcept 노드 생성
        run_query("""
        MERGE (lc:LegalConcept {name: $name})
        SET lc.definition = $definition,
            lc.law_ref    = $law_ref
        """, params={
            "name": concept["name"],
            "definition": concept["definition"],
            "law_ref": concept.get("law_ref") or "",
        })

        # LegalConcept -[:BELONGS_TO]-> Domain
        run_query("""
        MATCH (lc:LegalConcept {name: $name})
        MATCH (d:Domain {name: $domain})
        MERGE (lc)-[:BELONGS_TO]->(d)
        """, params={"name": concept["name"], "domain": concept["domain"]})

        # LegalConcept -[:REQUIRES]-> LegalConcept
        for req in concept.get("requires", []):
            run_query("""
            MATCH (lc:LegalConcept {name: $name})
            MERGE (req:LegalConcept {name: $req_name})
            MERGE (lc)-[:REQUIRES]->(req)
            """, params={"name": concept["name"], "req_name": req})

        # LegalConcept -[:DEFINED_IN]-> Law (법령 참조가 있는 경우)
        if concept.get("law_ref"):
            run_query("""
            MATCH (lc:LegalConcept {name: $name})
            MERGE (l:Law {name: $law_name})
            MERGE (lc)-[:DEFINED_IN]->(l)
            """, params={"name": concept["name"], "law_name": concept["law_ref"]})

    print(f"  ✅ LegalConcept {len(LEGAL_CONCEPTS)}개 적재 완료")


# ─────────────────────────────────────────────────────────
# Step 5: Procedure 노드 시드
# ─────────────────────────────────────────────────────────

def seed_procedures():
    print("[5/8] Procedure 노드 시드...")

    for proc in PROCEDURES:
        # Procedure 노드 생성
        run_query("""
        MERGE (p:Procedure {name: $name})
        SET p.order       = $order,
            p.timing      = $timing,
            p.description = $description
        """, params={
            "name": proc["name"],
            "order": proc["order"],
            "timing": proc["timing"],
            "description": proc["description"],
        })

        # Procedure -[:BELONGS_TO]-> Domain
        run_query("""
        MATCH (p:Procedure {name: $proc_name})
        MATCH (d:Domain {name: $domain})
        MERGE (p)-[:BELONGS_TO]->(d)
        """, params={"proc_name": proc["name"], "domain": proc["domain"]})

        # Procedure -[:RELATED_TO]-> LegalConcept
        run_query("""
        MATCH (p:Procedure {name: $proc_name})
        MATCH (lc:LegalConcept {name: $concept})
        MERGE (p)-[:RELATED_TO]->(lc)
        """, params={"proc_name": proc["name"], "concept": proc["legal_concept"]})

    print(f"  ✅ Procedure {len(PROCEDURES)}개 적재 완료")


# ─────────────────────────────────────────────────────────
# Step 6: RiskFactor 노드 시드 + 다중 관계 연결
# ─────────────────────────────────────────────────────────

def seed_risk_factors():
    print("[6/8] RiskFactor 시드 및 관계 연결...")

    for rf in RISK_FACTORS:
        # RiskFactor 노드 생성
        run_query("""
        MERGE (rf:RiskFactor {factor_id: $factor_id})
        SET rf.category    = $category,
            rf.description = $description,
            rf.severity    = $severity,
            rf.keywords    = $keywords,
            rf.advice      = $advice
        """, params={
            "factor_id":   rf["factor_id"],
            "category":    rf["category"],
            "description": rf["description"],
            "severity":    rf["severity"],
            "keywords":    rf["keywords"],
            "advice":      rf["advice"],
        })

        # RiskFactor -[:REGULATED_BY]-> Law
        for law_name in rf.get("laws", []):
            run_query("""
            MATCH (rf:RiskFactor {factor_id: $factor_id})
            MERGE (l:Law {name: $law_name})
            MERGE (rf)-[:REGULATED_BY]->(l)
            """, params={"factor_id": rf["factor_id"], "law_name": law_name})

        # RiskFactor -[:RELATED_TO]-> LegalConcept
        for concept_name in rf.get("legal_concepts", []):
            run_query("""
            MATCH (rf:RiskFactor {factor_id: $factor_id})
            MATCH (lc:LegalConcept {name: $concept_name})
            MERGE (rf)-[:RELATED_TO]->(lc)
            """, params={"factor_id": rf["factor_id"], "concept_name": concept_name})

        # RiskFactor -[:BELONGS_TO]-> Domain
        for domain_name in rf.get("domains", []):
            run_query("""
            MATCH (rf:RiskFactor {factor_id: $factor_id})
            MATCH (d:Domain {name: $domain_name})
            MERGE (rf)-[:BELONGS_TO]->(d)
            """, params={"factor_id": rf["factor_id"], "domain_name": domain_name})

        # AgentScope -[:DETECTED_BY]-> RiskFactor
        for agent_name in rf.get("detected_by_agents", []):
            run_query("""
            MATCH (rf:RiskFactor {factor_id: $factor_id})
            MATCH (a:AgentScope {name: $agent_name})
            MERGE (a)-[:DETECTED_BY]->(rf)
            """, params={"factor_id": rf["factor_id"], "agent_name": agent_name})

        # RiskFactor -[:IN_CATEGORY]-> DocumentCategory
        for cat_name in rf.get("doc_categories", []):
            run_query("""
            MATCH (rf:RiskFactor {factor_id: $factor_id})
            MATCH (dc:DocumentCategory {name: $cat_name})
            MERGE (rf)-[:IN_CATEGORY]->(dc)
            """, params={"factor_id": rf["factor_id"], "cat_name": cat_name})

    print(f"  ✅ RiskFactor {len(RISK_FACTORS)}개 + 관계 적재 완료")


# ─────────────────────────────────────────────────────────
# Step 7: PostgreSQL 판례·사례집 → Case 노드 추출
# ─────────────────────────────────────────────────────────

def extract_cases_from_db(pg_conn):
    print("[7/8] DB 판례·사례집 → Case 노드 추출...")

    cur = pg_conn.cursor()

    # ── 판례 처리 ──────────────────────────────────────
    cur.execute("""
        SELECT title, chunk_text
        FROM rag_documents
        WHERE doc_type = '판례'
          AND LENGTH(chunk_text) > 50
        ORDER BY title, chunk_index
    """)
    case_rows = cur.fetchall()
    print(f"  판례 청크 {len(case_rows)}개 처리 중...")

    case_law_map: dict[str, set] = {}
    for title, chunk_text in case_rows:
        case_name = title.replace(".pdf", "").strip()
        for law_base, article in LAW_PATTERN.findall(chunk_text):
            law_name = f"{law_base.strip()} {article.strip()}"
            case_law_map.setdefault(case_name, set()).add(law_name)

    # Case 노드 생성 (판례)
    if case_law_map:
        run_query("""
        UNWIND $params AS p
        MERGE (c:Case {name: p.name})
        SET c.doc_type = '판례'
        """, params=[{"name": n} for n in case_law_map])

    # Case -[:CITES]-> Law + Law -[:CITED_IN]-> Case
    cite_params = []
    for case_name, laws in case_law_map.items():
        for law_name in laws:
            cite_params.append({"case_name": case_name, "law_name": law_name})

    if cite_params:
        run_query("""
        UNWIND $params AS p
        MERGE (l:Law {name: p.law_name})
        WITH l, p
        MATCH (c:Case {name: p.case_name})
        MERGE (c)-[:CITES]->(l)
        MERGE (l)-[:CITED_IN]->(c)
        """, params=cite_params)

    # Case -[:INVOLVES]-> RiskFactor (키워드 매핑)
    cur.execute("""
        SELECT title, chunk_text
        FROM rag_documents
        WHERE doc_type = '판례'
          AND LENGTH(chunk_text) > 50
    """)
    all_case_rows = cur.fetchall()
    involve_params = []
    for title, chunk_text in all_case_rows:
        case_name = title.replace(".pdf", "").strip()
        seen = set()
        for keyword, factor_id in RISK_KEYWORD_MAP.items():
            if keyword in chunk_text and (case_name, factor_id) not in seen:
                involve_params.append({"case_name": case_name, "factor_id": factor_id})
                seen.add((case_name, factor_id))

    if involve_params:
        run_query("""
        UNWIND $params AS p
        MATCH (c:Case {name: p.case_name})
        MATCH (rf:RiskFactor {factor_id: p.factor_id})
        MERGE (c)-[:INVOLVES]->(rf)
        MERGE (rf)-[:EVIDENCED_BY]->(c)
        """, params=involve_params)

    print(f"  ✅ 판례 노드 {len(case_law_map)}개 + 인용 관계 {len(cite_params)}건")

    # ── 사례집 처리 ────────────────────────────────────
    cur.execute("""
        SELECT id, title, chunk_text
        FROM rag_documents
        WHERE doc_type = '사례집'
          AND LENGTH(chunk_text) > 50
        LIMIT 500
    """)
    study_rows = cur.fetchall()
    print(f"  사례집 청크 {len(study_rows)}개 처리 중...")

    study_params = [
        {"name": f"사례_{row_id}", "summary": chunk_text[:200], "title": title}
        for row_id, title, chunk_text in study_rows
    ]

    if study_params:
        run_query("""
        UNWIND $params AS p
        MERGE (c:Case {name: p.name})
        SET c.doc_type = '사례집',
            c.summary  = p.summary,
            c.title    = p.title
        """, params=study_params)

    # Case(사례집) -[:INVOLVES]-> RiskFactor
    study_rel_params = []
    for row_id, title, chunk_text in study_rows:
        case_name = f"사례_{row_id}"
        seen = set()
        for keyword, factor_id in RISK_KEYWORD_MAP.items():
            if keyword in chunk_text and (case_name, factor_id) not in seen:
                study_rel_params.append({"case_name": case_name, "factor_id": factor_id})
                seen.add((case_name, factor_id))

    if study_rel_params:
        run_query("""
        UNWIND $params AS p
        MATCH (c:Case {name: p.case_name})
        MATCH (rf:RiskFactor {factor_id: p.factor_id})
        MERGE (c)-[:INVOLVES]->(rf)
        MERGE (rf)-[:EVIDENCED_BY]->(c)
        """, params=study_rel_params)

    # Case(사례집) -[:IN_CATEGORY]-> DocumentCategory
    if study_params:
        run_query("""
        UNWIND $params AS p
        MATCH (c:Case {name: p.name})
        MATCH (dc:DocumentCategory {name: '사례집'})
        MERGE (c)-[:IN_CATEGORY]->(dc)
        """, params=study_params)

    # Case(판례) -[:IN_CATEGORY]-> DocumentCategory
    if case_law_map:
        run_query("""
        UNWIND $params AS p
        MATCH (c:Case {name: p.name})
        MATCH (dc:DocumentCategory {name: '판례'})
        MERGE (c)-[:IN_CATEGORY]->(dc)
        """, params=[{"name": n} for n in case_law_map])

    # 키워드 미매칭 포함 모든 사례집 Case → IN_CATEGORY 연결 (고아 노드 방지)
    run_query("""
    MATCH (c:Case)
    WHERE c.doc_type = '사례집' AND NOT (c)-[:IN_CATEGORY]->()
    MATCH (dc:DocumentCategory {name: '사례집'})
    MERGE (c)-[:IN_CATEGORY]->(dc)
    """)

    cur.close()
    print(f"  ✅ 사례집 노드 {len(study_rows)}개 + 위험 요소 관계 {len(study_rel_params)}건")


# ─────────────────────────────────────────────────────────
# Step 8: Law 노드 Domain 연결
# ─────────────────────────────────────────────────────────

def link_law_domains():
    print("[8/8] Law 노드 → Domain 관계 연결...")

    LAW_DOMAIN_MAP = [
        ("주택임대차보호법", "계약"),
        ("민법",            "계약"),
        ("공인중개사법",    "계약"),
        ("부동산등기법",    "등기"),
        ("신탁법",          "등기"),
        ("주택도시보증공사법", "보증"),
        ("민사집행법",      "법적절차"),
        ("소액사건심판법",  "법적절차"),
        ("전세사기피해자 특별법", "사기피해"),
        ("우편법",          "법적절차"),
        ("주민등록법",      "계약"),
    ]

    for law_prefix, domain_name in LAW_DOMAIN_MAP:
        run_query("""
        MATCH (l:Law)
        WHERE l.name STARTS WITH $prefix
        MATCH (d:Domain {name: $domain})
        MERGE (l)-[:BELONGS_TO]->(d)
        """, params={"prefix": law_prefix, "domain": domain_name})

    print(f"  ✅ Law → Domain 관계 {len(LAW_DOMAIN_MAP)}개 패턴 연결 완료")


# ─────────────────────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────────────────────

def run():
    print("=" * 60)
    print("  Neo4j 지식 그래프 구축 v2 시작")
    print("  (8 노드 타입 / 15+ 관계 타입)")
    print("=" * 60)

    # Neo4j 연결 확인
    try:
        driver.verify_connectivity()
        print("✅ Neo4j 연결 성공\n")
    except Exception as e:
        print(f"❌ Neo4j 연결 실패: {e}")
        return

    # PostgreSQL 연결
    try:
        pg_conn = psycopg2.connect(**DB_CONFIG)
        print("✅ PostgreSQL 연결 성공\n")
    except Exception as e:
        print(f"❌ PostgreSQL 연결 실패: {e}")
        return

    init_schema()
    seed_domains()
    seed_doc_categories_and_agents()
    seed_legal_concepts()
    seed_procedures()
    seed_risk_factors()
    extract_cases_from_db(pg_conn)
    link_law_domains()

    pg_conn.close()
    driver.close()

    print("\n" + "=" * 60)
    print("  🎉 Neo4j 지식 그래프 v2 구축 완료!")
    print("  노드: Domain(7) + DocumentCategory(10) + AgentScope(8)")
    print("        LegalConcept(15) + Procedure(7) + RiskFactor(12)")
    print("        + Law + Case (DB 기반 동적 생성)")
    print("=" * 60)


if __name__ == "__main__":
    run()
