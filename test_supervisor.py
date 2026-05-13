"""Supervisor Agent 통합 테스트.

세 가지 입력 시나리오로 라우팅이 올바르게 동작하는지 확인합니다.

실행:
    python test_supervisor.py
    python test_supervisor.py --case 1   # 계약서 진단만
    python test_supervisor.py --case 2   # 법률 상담만
    python test_supervisor.py --case 3   # RPG 방어 훈련만
    python test_supervisor.py --case 4   # 키워드 분류 테스트
"""
from __future__ import annotations

import argparse
import json
import sys
import os
from dataclasses import asdict, is_dataclass
from typing import Any

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common.graphs.supervisor_graph import run_supervisor


# ── 헬퍼 ─────────────────────────────────────────────────────────────

def _json_default(v: Any) -> Any:
    if is_dataclass(v):
        return asdict(v)
    return str(v)


def _print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _print_routing(result: dict) -> None:
    """라우팅 결과 요약 출력."""
    final = result.get("final_response", {})
    print(f"  ✅ 라우팅 타입   : {final.get('type', '?').upper()}")
    print(f"  ✅ 분류 방법     : {result.get('classification_method', '?')}")
    print(f"  ✅ 라우팅 이유   : {result.get('routing_reason', '?')}")
    errors = result.get("errors", [])
    if errors:
        print(f"  ⚠️  오류        : {errors}")
    print("-" * 60)


def _assert_intent(result: dict, expected: str, case_name: str) -> bool:
    actual = result.get("intent", "")
    if actual == expected:
        print(f"  ✅ [{case_name}] intent='{actual}' (정상)")
        return True
    else:
        print(f"  ❌ [{case_name}] 기대={expected}, 실제={actual}")
        return False


# ── 테스트 케이스 ─────────────────────────────────────────────────────

def test_case1_diagnosis() -> bool:
    """Case 1: 계약서 파일 경로 → DiagnosisGraph 라우팅."""
    _print_header("Case 1: 계약서 진단 라우팅 테스트")

    result = run_supervisor(
        contract_file="docs/가상계약서.docx",
        session_id="test-case1",
    )
    _print_routing(result)

    ok = _assert_intent(result, "diagnosis", "계약서 파일")
    final = result.get("final_response", {})
    print(f"  응답 타입: {final.get('type')}")
    return ok


def test_case2_legal() -> bool:
    """Case 2: 법률 질문 메시지 → LegalConsultationGraph 라우팅."""
    _print_header("Case 2: 법률 질문 라우팅 테스트")

    questions = [
        "보증금 반환은 다음 임차인 입주 이후에 한다는 특약이 위험한가요?",
        "근저당이 설정된 집의 전세계약, 어떻게 확인해야 하나요?",
        "전입신고와 확정일자를 같이 받아야 대항력이 생기나요?",
    ]

    all_ok = True
    for i, q in enumerate(questions, 1):
        print(f"\n  질문 {i}: {q[:40]}...")
        result = run_supervisor(user_message=q, session_id=f"test-case2-{i}")
        _print_routing(result)
        ok = _assert_intent(result, "legal", f"법률질문{i}")
        all_ok = all_ok and ok

    return all_ok


def test_case3_defense() -> bool:
    """Case 3: RPG 카테고리 → DefenseSimulationGraph 라우팅."""
    _print_header("Case 3: RPG 방어 훈련 라우팅 테스트")

    # 3-1. category_id 직접 전달
    print("\n  [3-1] category_id 직접 전달")
    result = run_supervisor(
        category_id="RIGHTS_CONCEALMENT",
        user_message="/도움말",
        session_id="test-case3-1",
    )
    _print_routing(result)
    ok1 = _assert_intent(result, "defense", "category_id 직접")

    # 3-2. RPG 키워드 메시지
    print("\n  [3-2] RPG 키워드 메시지")
    result = run_supervisor(
        user_message="전세사기 방어 RPG 훈련을 시작하고 싶어요. 시나리오를 보여주세요.",
        session_id="test-case3-2",
    )
    _print_routing(result)
    ok2 = _assert_intent(result, "defense", "RPG 키워드")

    return ok1 and ok2


def test_case4_keyword_routing() -> bool:
    """Case 4: 다양한 키워드 입력 → 라우팅 분류 검증."""
    _print_header("Case 4: 키워드 기반 라우팅 분류 테스트")

    test_inputs = [
        # (메시지, 기대 intent, 설명)
        ("특약에 임차인이 모든 수리비 부담한다는 조항이 있어요", "legal", "특약 키워드"),
        ("등기부에 가압류가 있는데 계약해도 될까요?", "legal", "등기부+가압류"),
        ("게임 시작! 사기꾼 NPC가 압박하고 있어요", "defense", "게임/사기꾼 키워드"),
        ("/힌트 주세요", "defense", "RPG 명령어"),
        ("보증보험 가입이 가능한지 알고 싶어요", "legal", "보증보험 키워드"),
        ("전세사기 방어 훈련 시나리오 시작해주세요", "defense", "훈련+시나리오 키워드"),
    ]

    all_ok = True
    for msg, expected, desc in test_inputs:
        print(f"\n  입력: '{msg[:45]}...' [{desc}]")
        result = run_supervisor(user_message=msg, session_id="test-case4")
        actual = result.get("intent", "?")
        method = result.get("classification_method", "?")
        if actual == expected:
            print(f"  ✅ {desc}: intent='{actual}' (방법={method})")
        else:
            print(f"  ❌ {desc}: 기대={expected}, 실제={actual} (방법={method})")
            all_ok = False

    return all_ok


def test_case5_no_input() -> bool:
    """Case 5: 빈 입력 → legal 기본 라우팅."""
    _print_header("Case 5: 빈 입력 기본 라우팅 테스트")

    result = run_supervisor(session_id="test-case5")
    _print_routing(result)
    ok = _assert_intent(result, "legal", "빈 입력")
    return ok


# ── 메인 실행 ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Supervisor Agent 테스트")
    parser.add_argument(
        "--case", type=int, choices=[1, 2, 3, 4, 5],
        help="실행할 테스트 케이스 번호 (기본: 전체)"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="sub-graph 결과 전체 JSON 출력"
    )
    args = parser.parse_args()

    print("\n🚀 Supervisor Agent 통합 테스트 시작")
    print("   (sub-graph는 실제 실행되므로 환경 설정에 따라 mock 결과가 나올 수 있습니다)")

    results: dict[int, bool] = {}

    case_map = {
        1: test_case1_diagnosis,
        2: test_case2_legal,
        3: test_case3_defense,
        4: test_case4_keyword_routing,
        5: test_case5_no_input,
    }

    if args.case:
        results[args.case] = case_map[args.case]()
    else:
        for num, fn in case_map.items():
            results[num] = fn()

    # ── 결과 요약 ─────────────────────────────────────────────────
    _print_header("테스트 결과 요약")
    case_names = {
        1: "계약서 진단 라우팅",
        2: "법률 질문 라우팅",
        3: "RPG 방어 훈련 라우팅",
        4: "키워드 분류",
        5: "빈 입력 기본 라우팅",
    }
    passed = sum(results.values())
    total = len(results)
    for num, ok in results.items():
        icon = "✅" if ok else "❌"
        print(f"  {icon} Case {num}: {case_names.get(num, '')}")

    print(f"\n  결과: {passed}/{total} 통과")
    if passed == total:
        print("  🎉 모든 테스트 통과!")
    else:
        print("  ⚠️  일부 테스트 실패 — 환경(Ollama, DB) 연결 확인 필요")


if __name__ == "__main__":
    main()
