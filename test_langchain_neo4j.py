"""
LangChain ↔ Neo4j 통합 테스트
Neo4j 그래프가 LangChain RAG 파이프라인에서 올바르게 활용되는지 검증

실행: python test_langchain_neo4j.py [--verbose]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from dotenv import load_dotenv

load_dotenv()

VERBOSE = "--verbose" in sys.argv
PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

results = []

def check(name: str, passed: bool, detail: str = ""):
    icon = PASS if passed else FAIL
    results.append((icon, name, detail))
    print(f"  {icon}  {name}" + (f"\n      └─ {detail}" if (VERBOSE or not passed) and detail else ""))

def section(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ─────────────────────────────────────────────────────────
# 공통 setup
# ─────────────────────────────────────────────────────────
sys.path.insert(0, "backend")

try:
    from rag_server.config import Settings
    from rag_server.core.graph_store import GraphStore
    from rag_server.core.vector_store import VectorStore
    from rag_server.core.rag_pipeline import RAGPipeline

    settings = Settings()
    graph_store  = GraphStore(settings)
    vector_store = VectorStore(settings)
    pipeline     = RAGPipeline(settings, vector_store, graph_store)
    SETUP_OK = True
except Exception as e:
    print(f"\n{FAIL} 모듈 로드 실패: {e}")
    print("  → backend/ 경로 확인 또는 docker compose up -d 실행 필요")
    SETUP_OK = False


# ─────────────────────────────────────────────────────────
# 레벨 1: GraphStore 직접 호출 테스트
# ─────────────────────────────────────────────────────────
section("레벨 1. GraphStore 직접 호출")

if not SETUP_OK:
    check("setup 실패로 건너뜀", False)
else:
    # 1-1. 연결 상태
    check("Neo4j 연결", graph_store.is_ready())

    # 1-2. 키워드 → RiskFactor
    risks = graph_store.get_risk_factors_by_keywords(["근저당", "전입신고", "전세가율"])
    check(
        f"키워드 검색 → RiskFactor {len(risks)}개 반환",
        len(risks) > 0,
        str([r["factor_id"] for r in risks]) if VERBOSE else "",
    )
    if risks and VERBOSE:
        r = risks[0]
        print(f"      상위 결과: {r['factor_id']} | {r['category']} | {r['severity']}")
        print(f"      법령: {r.get('laws', [])}")
        print(f"      법률개념: {r.get('legal_concepts', [])}")

    # 1-3. 에이전트별 문서 카테고리
    AGENTS = [
        ("ownership_risk_agent",  ["판례", "법령", "사례집"]),
        ("market_risk_agent",     ["시세데이터", "보고서"]),
        ("insurance_risk_agent",  ["보증약관", "정책자료"]),
        ("special_clause_agent",  ["서식", "법령", "판례"]),
    ]
    for agent_name, expected_cats in AGENTS:
        cats = graph_store.get_document_categories_for_agent(agent_name)
        cat_names = [c["name"] for c in cats]
        overlap = [c for c in expected_cats if c in cat_names]
        check(
            f"{agent_name} → doc_categories {cat_names}",
            len(overlap) == len(expected_cats),
            f"기대={expected_cats} 실제={cat_names}",
        )

    # 1-4. LegalConcept 선후관계
    concepts = graph_store.get_legal_concepts(["대항력"])
    req_targets = [c["target"] for c in concepts if c["relation"] == "requires"]
    check(
        "대항력 → REQUIRES → 전입신고",
        "전입신고" in req_targets,
        f"REQUIRES targets: {req_targets}",
    )

    # 1-5. 에이전트 컨텍스트
    ctx = graph_store.get_context_for_agent("ownership_risk_agent", keywords=["근저당"])
    check(
        f"ownership_risk_agent 컨텍스트 {len(ctx)}건",
        len(ctx) > 0,
        str(ctx[:2]) if VERBOSE else "",
    )

    # 1-6. full graph_context [{node, relation, target}] 형식 검증
    full_ctx = graph_store.get_full_graph_context(["근저당", "전입신고", "확정일자"])
    valid_format = all(
        {"node", "relation", "target"} <= set(item.keys())
        for item in full_ctx
    )
    check(
        f"graph_context 형식 검증 ({len(full_ctx)}건, {{node/relation/target}})",
        valid_format and len(full_ctx) > 0,
        str(full_ctx[:3]) if VERBOSE else "",
    )


# ─────────────────────────────────────────────────────────
# 레벨 2: RAG 파이프라인 통합 — graph_context 포함 여부
# ─────────────────────────────────────────────────────────
section("레벨 2. RAG 파이프라인 graph_context 포함 검증")

if not SETUP_OK:
    check("setup 실패로 건너뜀", False)
else:
    TEST_QUESTIONS = [
        {
            "question":  "근저당이 많은 집에 전세 들어가면 어떤 위험이 있나요?",
            "keywords":  ["근저당", "전세"],
            "expect_rf": ["RF002"],
        },
        {
            "question":  "전입신고와 확정일자를 꼭 해야 하는 이유가 뭔가요?",
            "keywords":  ["전입신고", "확정일자"],
            "expect_rf": ["RF008"],
        },
        {
            "question":  "신탁등기 집에 전세 계약해도 되나요?",
            "keywords":  ["신탁등기"],
            "expect_rf": ["RF011"],
        },
    ]

    async def run_chat_tests():
        for tc in TEST_QUESTIONS:
            t0 = time.time()
            try:
                result = await pipeline.chat(
                    session_id="test-session",
                    question=tc["question"],
                    history=[],
                )
                elapsed = time.time() - t0

                # graph_context 필드 존재 확인
                has_graph_ctx = "graph_context" in result and len(result["graph_context"]) > 0
                check(
                    f"graph_context 포함: '{tc['question'][:30]}...'",
                    has_graph_ctx,
                    f"{len(result.get('graph_context', []))}건, {elapsed:.1f}s",
                )

                # graph_context에 기대 RF 포함 여부
                if has_graph_ctx:
                    ctx_nodes = [c["node"] for c in result["graph_context"]]
                    ctx_targets = [c["target"] for c in result["graph_context"]]
                    for rf_id in tc["expect_rf"]:
                        found = rf_id in ctx_nodes or rf_id in ctx_targets
                        check(
                            f"  └─ {rf_id} graph_context에 포함",
                            found,
                            f"nodes={ctx_nodes[:5]}",
                        )

                if VERBOSE:
                    print(f"\n      [답변 미리보기]")
                    print(f"      {result['answer'][:200]}...")
                    print(f"      [graph_context 상위 3개]")
                    for c in result["graph_context"][:3]:
                        print(f"        {c['node']} --[{c['relation']}]--> {c['target']}")
                    print(f"      [참조 문서] {[r.doc_type for r in result.get('references', [])]}")

            except Exception as e:
                check(f"chat 실행 실패: {tc['question'][:30]}", False, str(e))

    asyncio.run(run_chat_tests())


# ─────────────────────────────────────────────────────────
# 레벨 3: graph_context vs 없을 때 답변 비교
# ─────────────────────────────────────────────────────────
section("레벨 3. graph_context 활용 품질 검증")

if not SETUP_OK:
    check("setup 실패로 건너뜀", False)
else:
    QUALITY_CHECKS = [
        {
            "name":     "근저당 질문 → 법령 언급 여부",
            "question": "근저당이 많으면 왜 위험한가요?",
            "keywords": ["근저당"],
            "expect_in_answer": ["민법", "주택임대차보호법", "등기부", "선순위"],
        },
        {
            "name":     "전입신고 질문 → 대항력 개념 언급 여부",
            "question": "전입신고를 안 하면 어떻게 되나요?",
            "keywords": ["전입신고"],
            "expect_in_answer": ["대항력", "전입신고", "보증금"],
        },
    ]

    async def run_quality_tests():
        for tc in QUALITY_CHECKS:
            try:
                result = await pipeline.chat(
                    session_id="quality-test",
                    question=tc["question"],
                    history=[],
                )
                answer = result.get("answer", "")
                found_terms = [kw for kw in tc["expect_in_answer"] if kw in answer]
                ratio = len(found_terms) / len(tc["expect_in_answer"])

                check(
                    f"{tc['name']} (키워드 {len(found_terms)}/{len(tc['expect_in_answer'])} 포함)",
                    ratio >= 0.5,
                    f"포함된 키워드: {found_terms}",
                )

                if VERBOSE:
                    print(f"\n      [답변]\n      {answer[:300]}...")

            except Exception as e:
                check(f"{tc['name']} 실패", False, str(e))

    asyncio.run(run_quality_tests())


# ─────────────────────────────────────────────────────────
# 레벨 4: 진단 API graph_context 포함 검증
# ─────────────────────────────────────────────────────────
section("레벨 4. 진단 API graph_context 포함 검증")

SAMPLE_CONTRACT = """
전세계약서

임대인: 홍길동 (주민등록번호: 800101-XXXXXXX)
임차인: 김철수
소재지: 서울시 강남구 역삼동 123-4 빌라 3층 302호
보증금: 250,000,000원 (이억오천만원)
계약기간: 2024년 3월 1일 ~ 2026년 2월 28일

특약사항:
1. 임차인은 원상복구 의무를 진다.
2. 집주인 요청 시 즉시 퇴거한다.

등기부현황: 근저당 1억원 (KB국민은행)
"""

if not SETUP_OK:
    check("setup 실패로 건너뜀", False)
else:
    async def run_diagnosis_test():
        try:
            keywords = ["근저당", "원상복구", "보증금", "특약", "전입신고"]
            result = await pipeline.diagnose(
                session_id="diag-test",
                contract_text=SAMPLE_CONTRACT,
                contract_keywords=keywords,
            )

            check("진단 결과 반환", "risk_score" in result)
            check(
                f"risk_factors {len(result.get('risk_factors', []))}개 감지",
                len(result.get("risk_factors", [])) > 0,
            )
            check(
                f"진단에 graph_context 포함 ({len(result.get('graph_context', []))}건)",
                len(result.get("graph_context", [])) > 0,
            )

            if VERBOSE:
                print(f"\n      risk_score:  {result.get('risk_score')}")
                print(f"      risk_level:  {result.get('risk_level')}")
                print(f"      risk_factors: {[rf.factor_id for rf in result.get('risk_factors', [])]}")
                print(f"      graph_context 상위 3개:")
                for c in result.get("graph_context", [])[:3]:
                    print(f"        {c['node']} --[{c['relation']}]--> {c['target']}")

        except Exception as e:
            check("진단 API 실행 실패", False, str(e))

    asyncio.run(run_diagnosis_test())


# ─────────────────────────────────────────────────────────
# 최종 요약
# ─────────────────────────────────────────────────────────
if SETUP_OK:
    graph_store.close()

print(f"\n{'='*60}")
total  = len(results)
passed = sum(1 for r in results if r[0] == PASS)
failed = total - passed
warned = sum(1 for r in results if r[0] == WARN)

print(f"  결과: {passed}/{total} 통과  |  실패: {failed}건")
if failed > 0:
    print(f"\n  [실패 항목]")
    for icon, name, detail in results:
        if icon == FAIL:
            print(f"    {FAIL}  {name}")
            if detail:
                print(f"        → {detail}")
print(f"{'='*60}\n")

sys.exit(0 if failed == 0 else 1)
