"""
LangGraph 기반 전세계약 위험 진단 워크플로우

파이프라인:
  계약서 입력 → contract_extractor → [model_agent, special_terms_agent] → report_writer → 최종 리포트

상태 관리: TypedDict 기반 그래프 상태
"""

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END

from backend.agents.contract_extractor import (
    ContractData, ExtractionResult, extract_contract, create_manual_input,
)
from backend.agents.model_agent import ModelAgentResult, analyze_price_risk
from backend.agents.special_terms_agent import SpecialTermsResult, analyze_special_terms
from backend.agents.report_writer import ReportWriterResult, write_report


# ── 그래프 상태 정의 ─────────────────────────────────────

class WorkflowState(TypedDict):
    # 입력
    file_bytes: bytes | None
    filename: str | None
    manual_address: str | None
    manual_deposit: int | None
    manual_area: float | None
    manual_period: str | None

    # 에이전트 결과
    extraction: ExtractionResult | None
    contract: ContractData | None
    model_result: ModelAgentResult | None
    terms_result: SpecialTermsResult | None
    report_result: ReportWriterResult | None

    # 흐름 제어
    error: str | None


# ── 노드 함수 ────────────────────────────────────────────

def node_extract(state: WorkflowState) -> dict:
    """계약서 추출 노드"""
    if state.get("file_bytes") and state.get("filename"):
        result = extract_contract(state["file_bytes"], state["filename"])
    elif state.get("manual_address") and state.get("manual_deposit"):
        result = create_manual_input(
            address=state["manual_address"],
            deposit=state["manual_deposit"],
            area_m2=state.get("manual_area"),
            contract_period=state.get("manual_period"),
        )
    else:
        return {
            "extraction": None,
            "error": "계약서 파일 또는 주소/전세금 정보를 입력해 주세요.",
        }

    if not result.success:
        return {"extraction": result, "error": result.message}

    return {"extraction": result, "contract": result.data}


def node_model(state: WorkflowState) -> dict:
    """가격 위험도 분석 노드"""
    contract = state.get("contract")
    if not contract:
        return {"model_result": None}

    result = analyze_price_risk(contract)
    return {"model_result": result}


def node_terms(state: WorkflowState) -> dict:
    """특약 분석 노드"""
    contract = state.get("contract")
    if not contract or not contract.special_terms:
        return {"terms_result": SpecialTermsResult(
            success=True,
            overall_diagnosis="특약 조항이 없습니다."
        )}

    result = analyze_special_terms(contract.special_terms)
    return {"terms_result": result}


def node_report(state: WorkflowState) -> dict:
    """리포트 생성 노드"""
    model_result = state.get("model_result")
    if not model_result:
        return {"report_result": None, "error": "가격 분석 결과가 없습니다."}

    terms_result = state.get("terms_result")
    result = write_report(model_result, terms_result)
    return {"report_result": result}


# ── 라우터 ───────────────────────────────────────────────

def should_continue(state: WorkflowState) -> str:
    if state.get("error"):
        return "end"
    return "analyze"


# ── 그래프 빌드 ──────────────────────────────────────────

def build_workflow() -> StateGraph:
    workflow = StateGraph(WorkflowState)

    workflow.add_node("extract", node_extract)
    workflow.add_node("model", node_model)
    workflow.add_node("terms", node_terms)
    workflow.add_node("report", node_report)

    workflow.set_entry_point("extract")

    workflow.add_conditional_edges(
        "extract",
        should_continue,
        {"analyze": "model", "end": END},
    )

    workflow.add_edge("model", "terms")
    workflow.add_edge("terms", "report")
    workflow.add_edge("report", END)

    return workflow.compile()


# 컴파일된 그래프 (싱글톤)
diagnosis_graph = build_workflow()


def run_diagnosis(file_bytes: bytes = None, filename: str = None,
                  address: str = None, deposit: int = None,
                  area_m2: float = None, contract_period: str = None) -> dict:
    """진단 파이프라인 실행 (간편 인터페이스)"""
    initial_state = {
        "file_bytes": file_bytes,
        "filename": filename,
        "manual_address": address,
        "manual_deposit": deposit,
        "manual_area": area_m2,
        "manual_period": contract_period,
        "extraction": None,
        "contract": None,
        "model_result": None,
        "terms_result": None,
        "report_result": None,
        "error": None,
    }

    result = diagnosis_graph.invoke(initial_state)

    if result.get("error"):
        return {
            "success": False,
            "error": result["error"],
        }

    report_result = result.get("report_result")
    return {
        "success": True,
        "final_report": report_result.final_report if report_result else "",
        "saved_path": report_result.saved_path if report_result else "",
        "model_result": result.get("model_result"),
        "terms_result": result.get("terms_result"),
        "report": report_result.report if report_result else None,
    }
