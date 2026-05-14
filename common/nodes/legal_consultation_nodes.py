"""LangGraph state nodes for the case-based legal consultation graph."""
from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any


from common.agents.legal_consultation_agents import (
    classify_legal_question_with_llm,
    generate_legal_answer_with_llm,
    run_case_based_answer_react_agent,
    run_legal_case_retriever_agent,
    run_legal_law_guide_retriever_agent,
)
from common.schemas.legal_consultation import (
    CitedCase,
    CitedLaw,
    EvidenceQuality,
    ExternalSource,
    LegalConsultationState,
)
from common.schemas.shared import AgentTrace, ContextPack
from common.tools.adaptive_rag import adaptive_rag
from common.tools.external_search import search_external_sources

DISCLAIMER = "본 답변은 법률 자문이 아니라 판례와 공공자료 기반 정보 제공입니다. 실제 판단은 계약서 문구와 증거에 따라 달라질 수 있습니다."


def legal_intake_node(state: LegalConsultationState) -> LegalConsultationState:
    question = (state.get("question") or state.get("user_question") or "").strip()
    errors = list(state.get("errors", []))
    if not question:
        errors.append("question is required")
    normalized = _build_query(question, state.get("related_finding"), state.get("contract_context"))
    return _merge(state, question=question, normalized_query=normalized, errors=errors, trace=_trace("Legal Intake Agent", "normalize_legal_question", {"question": question}, {"has_error": bool(errors)}))


def question_classifier_node(state: LegalConsultationState) -> LegalConsultationState:
    question = state.get("normalized_query", state.get("question", ""))
    qtype = _classify_question(question)
    return _merge(state, question_type=qtype, trace=_trace("Question Classifier Agent", "classify_question_type", {"question": state.get("question", "")}, {"question_type": qtype}))


def internal_case_retriever_node(state: LegalConsultationState) -> LegalConsultationState:
    query = state.get("normalized_query", state.get("question", ""))
    react_summary = run_legal_case_retriever_agent(state.get("question_type"), query)
    pack = adaptive_rag(
        "legal_case_search",
        query,
        filters={"doc_type": ["판례", "사례집"], "question_type": state.get("question_type")},
        top_k=5,
    )
    outputs = {"context_count": len(pack.contexts), "react_agent_used": bool(react_summary)}
    if react_summary:
        outputs["react_agent_summary"] = react_summary[:500]
    return _merge(state, internal_case_context=pack, trace=_trace("Internal Case Retriever ReAct Agent", "retrieve_internal_cases", {"question_type": state.get("question_type")}, outputs))


def internal_law_guide_retriever_node(state: LegalConsultationState) -> LegalConsultationState:
    query = state.get("normalized_query", state.get("question", ""))
    react_summary = run_legal_law_guide_retriever_agent(state.get("question_type"), query)
    pack = adaptive_rag(
        "legal_law_guide_search",
        query,
        filters={"doc_type": ["법령", "사례집"], "question_type": state.get("question_type")},
        top_k=5,
    )
    outputs = {"context_count": len(pack.contexts), "react_agent_used": bool(react_summary)}
    if react_summary:
        outputs["react_agent_summary"] = react_summary[:500]
    return _merge(state, internal_law_context=pack, trace=_trace("Internal Law/Guide Retriever ReAct Agent", "retrieve_internal_law_guides", {"question_type": state.get("question_type")}, outputs))


def evidence_grader_node(state: LegalConsultationState) -> LegalConsultationState:
    case_pack = state.get("internal_case_context")
    law_pack = state.get("internal_law_context")
    case_contexts = _matching_contexts(case_pack, _is_case_context)
    law_contexts = _matching_contexts(law_pack, _is_law_context)
    case_count = len(case_contexts)
    law_count = len(law_contexts)
    case_score = _evidence_score(case_contexts, "case")
    law_score = _evidence_score(law_contexts, "law")

    if case_count >= 1 and law_count >= 1:
        score = round(min(0.95, 0.55 + case_score * 0.25 + law_score * 0.20), 2)
        quality = EvidenceQuality(score >= 0.65, score, "MIXED", "case and law/guide evidence found with metadata-aware quality score")
    elif case_count >= 1:
        score = round(min(0.90, 0.45 + case_score * 0.35), 2)
        quality = EvidenceQuality(score >= 0.65, score, "INTERNAL_CASE", "case evidence found with metadata-aware quality score")
    elif law_count >= 1:
        score = round(min(0.80, 0.35 + law_score * 0.35), 2)
        quality = EvidenceQuality(score >= 0.60, score, "INTERNAL_LAW", "law/guide evidence found with metadata-aware quality score")
    else:
        quality = EvidenceQuality(False, 0.0, "INSUFFICIENT", "no useful internal evidence found")

    return _merge(state, evidence_quality=quality, needs_external_search=not quality.sufficient, basis_type=quality.basis_type, confidence=_confidence_from_quality(quality.score), trace=_trace("Evidence Grader Agent", "grade_internal_evidence", {"case_count": case_count, "law_count": law_count, "case_score": case_score, "law_score": law_score}, asdict(quality)))


def external_search_node(state: LegalConsultationState) -> LegalConsultationState:
    if not state.get("needs_external_search", False):
        return _merge(state, used_external_search=False, external_sources=[], trace=_trace("External Search Agent", "skip_external_search", {}, {"reason": "internal evidence sufficient"}))

    sources = search_external_sources(state.get("normalized_query", state.get("question", "")), state.get("question_type", "UNKNOWN"))
    return _merge(state, used_external_search=True, external_sources=sources, basis_type="EXTERNAL_SOURCE" if state.get("basis_type") == "INSUFFICIENT" else "MIXED", trace=_trace("External Search Agent", "collect_external_sources", {"question_type": state.get("question_type")}, {"source_count": len(sources)}))


def citation_collector_node(state: LegalConsultationState) -> LegalConsultationState:
    cited_cases = _extract_cases(state.get("internal_case_context"))
    cited_laws = _extract_laws(state.get("internal_law_context"))
    return _merge(state, cited_cases=cited_cases, cited_laws=cited_laws, trace=_trace("External Citation Collector Agent", "structure_citations", {}, {"case_count": len(cited_cases), "law_count": len(cited_laws), "external_count": len(state.get("external_sources", []))}))


def case_based_answer_node(state: LegalConsultationState) -> LegalConsultationState:
    answer = _generate_answer(state)
    actions = _recommended_actions(state)
    return _merge(state, answer_draft=answer, recommended_actions=actions, trace=_trace("Case-Based Answer Agent", "draft_case_based_answer", {"basis_type": state.get("basis_type")}, {"answer_length": len(answer), "action_count": len(actions)}))


def legal_guardrail_node(state: LegalConsultationState) -> LegalConsultationState:
    guarded = _apply_guardrails(state.get("answer_draft", ""))
    if state.get("used_external_search"):
        guarded = "내부 자료에서 충분한 근거를 찾지 못해 외부 공신력 자료를 함께 참고했습니다.\n\n" + guarded
    if DISCLAIMER not in guarded:
        guarded = guarded.rstrip() + "\n\n" + DISCLAIMER
    return _merge(state, final_answer=guarded, disclaimer=DISCLAIMER, trace=_trace("Legal Guardrail Agent", "remove_overconfident_legal_advice", {}, {"answer_length": len(guarded)}))


def consultation_report_node(state: LegalConsultationState) -> LegalConsultationState:
    report_trace = _trace("Consultation Report Agent", "package_legal_consultation_report", {}, {"sections": ["answer", "basis_type", "used_external_search", "confidence", "question_type", "cited_cases", "cited_laws", "external_sources", "recommended_actions", "disclaimer", "agent_trace"]})
    full_trace = list(state.get("agent_trace", [])) + [report_trace]
    report = {
        "answer": state.get("final_answer", ""),
        "basis_type": state.get("basis_type", "INSUFFICIENT"),
        "used_external_search": state.get("used_external_search", False),
        "confidence": state.get("confidence", "LOW"),
        "question_type": state.get("question_type", "UNKNOWN"),
        "cited_cases": [asdict(case) for case in state.get("cited_cases", [])],
        "cited_laws": [asdict(law) for law in state.get("cited_laws", [])],
        "external_sources": [asdict(source) for source in state.get("external_sources", [])],
        "recommended_actions": state.get("recommended_actions", []),
        "disclaimer": state.get("disclaimer", DISCLAIMER),
        "agent_trace": [asdict(trace) for trace in full_trace],
    }
    return _merge(state, report=report, trace=report_trace)


def _classify_question(question: str) -> str:
    try:
        qtype = classify_legal_question_with_llm(question)
        if qtype:
            return qtype
    except Exception:
        pass

    text = question.lower()
    if "보증금" in question and ("반환" in question or "돌려" in question):
        return "DEPOSIT_RETURN"
    if "특약" in question or "조항" in question:
        return "SPECIAL_CLAUSE"
    if "전입" in question or "대항력" in question:
        return "OPPOSING_POWER"
    if "확정일자" in question or "우선변제" in question:
        return "PREFERRED_PAYMENT"
    if "근저당" in question or "등기" in question:
        return "REGISTRY_RISK"
    if "신탁" in question:
        return "TRUST_REGISTRATION"
    if "세금" in question or "체납" in question:
        return "TAX_ARREARS"
    return "UNKNOWN"


def _generate_answer(state: LegalConsultationState) -> str:
    cases = state.get("cited_cases", [])
    laws = state.get("cited_laws", [])
    external = state.get("external_sources", [])
    question = state.get("question", "")

    prompt = _answer_prompt(state)
    react_answer = run_case_based_answer_react_agent(prompt)
    if react_answer:
        return react_answer

    try:
        llm_answer = generate_legal_answer_with_llm(prompt)
        if llm_answer:
            return llm_answer
    except Exception:
        pass

    lines = [f"질문하신 내용은 {state.get('question_type', 'UNKNOWN')} 유형의 전세계약 쟁점으로 볼 수 있습니다."]
    if cases:
        case = cases[0]
        lines.append(f"내부 판례 자료에서 '{case.issue or case.summary}' 관련 근거가 확인되었습니다.")
        lines.append(f"{case.court or '내부 판례 자료'} {case.case_number or ''} 자료의 취지는 {case.summary}")
        lines.append(f"이 사안과의 관련성은 {case.relevance}")
    if laws:
        law = laws[0]
        lines.append(f"법령/가이드 근거로는 {law.title} 자료가 함께 확인됩니다. {law.summary}")
    if external:
        lines.append("내부 자료가 충분하지 않아 외부 공신력 자료도 함께 참고했습니다.")
        lines.append(f"참고 외부 자료: {external[0].publisher} - {external[0].title}")
    lines.append("따라서 임차인에게 유리한 근거로 활용될 가능성은 있으나, 실제 판단은 계약서 문구와 증거관계에 따라 달라질 수 있습니다.")
    return "\n\n".join(lines)


def _answer_prompt(state: LegalConsultationState) -> str:
    return f"""
사용자 질문에 대해 판례/법령 근거 중심으로 한국어 답변을 작성해.
금지: 승소 가능합니다, 무조건 이깁니다, 법적으로 문제 없습니다, 반드시 돌려받을 수 있습니다.
반드시 포함: 결론 요약, 근거 판례/법령, 사안과의 관련성, 추가 확인사항, 법률 자문 아님 고지.

질문: {state.get('question')}
질문 유형: {state.get('question_type')}
관련 finding: {state.get('related_finding')}
계약 문맥: {state.get('contract_context')}
내부 판례: {[asdict(case) for case in state.get('cited_cases', [])]}
내부 법령/가이드: {[asdict(law) for law in state.get('cited_laws', [])]}
외부 자료 사용 여부: {state.get('used_external_search')}
외부 자료: {[asdict(source) for source in state.get('external_sources', [])]}
""".strip()


def _apply_guardrails(answer: str) -> str:
    replacements = {
        "승소 가능합니다": "임차인 주장이 받아들여질 가능성을 뒷받침하는 근거가 있습니다",
        "무조건 이깁니다": "유리한 근거가 있을 수 있습니다",
        "법적으로 문제 없습니다": "분쟁 가능성이 낮다고 단정하기는 어렵습니다",
        "반드시 돌려받을 수 있습니다": "반환 청구 근거로 활용될 가능성이 있습니다",
        "이 계약은 무효입니다": "이 계약 조항은 다툼의 여지가 있습니다",
    }
    guarded = answer
    for bad, safe in replacements.items():
        guarded = guarded.replace(bad, safe)
    return guarded


def _extract_cases(pack: ContextPack | None) -> list[CitedCase]:
    if not pack:
        return []
    cases: list[CitedCase] = []
    for context in pack.contexts:
        if not _is_case_context(context.doc_type, context.metadata):
            continue
        meta = _merged_context_metadata(context)
        title_case_info = _case_info_from_title(context.title)
        cases.append(CitedCase(
            court=_first_meta(meta, "court", "court_name", "법원명") or title_case_info.get("court"),
            case_number=_first_meta(meta, "case_number", "case_no", "사건번호") or title_case_info.get("case_number"),
            issue=_first_meta(meta, "issue", "쟁점", "risk_type") or context.title,
            summary=context.text,
            relevance=_first_meta(meta, "relevance") or "사용자 질문과 관련된 전세계약 위험 쟁점의 RAG 판례/사례 근거입니다.",
            source_id=context.source_id,
        ))
    return cases


def _extract_laws(pack: ContextPack | None) -> list[CitedLaw]:
    if not pack:
        return []
    laws: list[CitedLaw] = []
    for context in pack.contexts:
        if not _is_law_context(context.doc_type, context.metadata):
            continue
        meta = _merged_context_metadata(context)
        title = _first_meta(meta, "law", "law_name", "article", "조문명") or context.title
        laws.append(CitedLaw(title=title, summary=context.text, source_id=context.source_id))
    return laws


def _is_case_context(doc_type: str, metadata: dict[str, Any]) -> bool:
    value = f"{doc_type} {metadata.get('doc_type', '')} {metadata.get('type', '')}".lower()
    raw = metadata.get("raw_reference")
    if isinstance(raw, dict):
        value += f" {raw.get('doc_type', '')} {raw.get('type', '')}".lower()
    return any(token in value for token in ["case", "judgement", "판례", "판결", "사례"])


def _is_law_context(doc_type: str, metadata: dict[str, Any]) -> bool:
    value = f"{doc_type} {metadata.get('doc_type', '')} {metadata.get('type', '')}".lower()
    raw = metadata.get("raw_reference")
    if isinstance(raw, dict):
        value += f" {raw.get('doc_type', '')} {raw.get('type', '')}".lower()
    return any(token in value for token in ["law", "guide", "checklist", "법령", "가이드", "체크리스트", "표준계약서"])


def _case_info_from_title(title: str) -> dict[str, str]:
    info: dict[str, str] = {}
    court_match = re.search(
        r"(대법원|헌법재판소|[가-힣]+(?:지방법원|고등법원|지법|고법))",
        title,
    )
    if court_match:
        info["court"] = court_match.group(1)

    case_match = re.search(r"(\d{4}\s*[가-힣]{1,4}\s*\d+)", title)
    if case_match:
        info["case_number"] = re.sub(r"\s+", "", case_match.group(1))
    return info


def _matching_contexts(pack: ContextPack | None, predicate: Any) -> list[RetrievedContext]:
    if not pack:
        return []
    return [context for context in pack.contexts if predicate(context.doc_type, context.metadata)]


def _evidence_score(contexts: list[RetrievedContext], kind: str) -> float:
    if not contexts:
        return 0.0

    relevance = sum(_clamp(context.score) for context in contexts) / len(contexts)
    metadata_bonus = 0.0
    text_bonus = 0.0
    source_bonus = min(0.08, len({context.source_id for context in contexts}) * 0.03)

    for context in contexts:
        meta = _merged_context_metadata(context)
        parsed_case_info = _case_info_from_title(context.title)
        if kind == "case" and (
            _first_meta(meta, "case_number", "case_no", "사건번호", "court", "court_name", "법원명")
            or parsed_case_info.get("case_number")
            or parsed_case_info.get("court")
        ):
            metadata_bonus = max(metadata_bonus, 0.12)
        if kind == "law" and _first_meta(meta, "law", "law_name", "article", "조문명", "source_id"):
            metadata_bonus = max(metadata_bonus, 0.10)
        if len(context.text.strip()) >= 120:
            text_bonus = max(text_bonus, 0.05)

    return round(min(1.0, relevance + metadata_bonus + text_bonus + source_bonus), 2)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _merged_context_metadata(context: Any) -> dict[str, Any]:
    meta = dict(getattr(context, "metadata", {}) or {})
    raw = meta.get("raw_reference")
    if isinstance(raw, dict):
        raw_meta = raw.get("metadata")
        if isinstance(raw_meta, dict):
            meta.update(raw_meta)
        for key, value in raw.items():
            meta.setdefault(key, value)
    return meta


def _first_meta(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _recommended_actions(state: LegalConsultationState) -> list[str]:
    actions = ["계약서 원문 특약과 반환 기한을 명확히 확인하세요."]
    if state.get("question_type") in {"DEPOSIT_RETURN", "SPECIAL_CLAUSE"}:
        actions.append("보증금 반환 기한과 지연 시 책임을 특약에 명확히 쓰도록 수정 요청하세요.")
    actions.append("등기부등본, 임대인 신분, 체납 여부 등 계약서 외 자료를 함께 확인하세요.")
    actions.append("분쟁 가능성이 크면 대한법률구조공단, 주택임대차분쟁조정위원회 또는 변호사 상담을 권장합니다.")
    return actions


def _build_query(question: str, related_finding: dict[str, Any] | None, contract_context: dict[str, Any] | None) -> str:
    parts = [question]
    if related_finding:
        parts.append(f"관련 진단 항목: {related_finding}")
    if contract_context:
        parts.append(f"계약 문맥: {contract_context}")
    return "\n".join(parts)


def _confidence_from_quality(score: float) -> str:
    if score >= 0.75:
        return "HIGH"
    if score >= 0.45:
        return "MEDIUM"
    return "LOW"


def _merge(state: LegalConsultationState, *, trace: AgentTrace | None = None, **updates: Any) -> LegalConsultationState:
    next_state: LegalConsultationState = dict(state)
    next_state.update(updates)
    if trace:
        traces = list(next_state.get("agent_trace", []))
        traces.append(trace)
        next_state["agent_trace"] = traces
    return next_state


def _trace(agent: str, action: str, inputs: dict[str, Any], outputs: dict[str, Any]) -> AgentTrace:
    return AgentTrace(agent=agent, action=action, inputs=inputs, outputs=outputs)


# ──────────────────────────────────────────────────────────────────────────────
# v7 추가 노드: legal_consultation_graph.py import 호환용
# ──────────────────────────────────────────────────────────────────────────────

def legal_supervisor_node(state: LegalConsultationState) -> LegalConsultationState:
    """LLM supervisor: question type 판단 후 legal_rag / counselor 라우팅 결정."""
    try:
        from common.agents.legal_supervisor_agent import run_legal_supervisor_agent
        question = state.get("user_question") or state.get("question", "")
        history = state.get("conversation_history", [])
        decision = run_legal_supervisor_agent(question, history)
        route = decision.route.value if hasattr(decision.route, "value") else str(decision.route)
        intent = decision.intent.value if hasattr(decision.intent, "value") else str(decision.intent)
        needs_rag = route in {"LEGAL_RAG", "BOTH"}
        return _merge(
            state,
            route=route,
            intent=intent,
            needs_rag=needs_rag,
            reason=getattr(decision, "reason", ""),
            supervisor_status="classified",
            current_agent="legal_supervisor",
            trace=_trace("Legal Supervisor", "classify_and_route", {"question": question[:100]}, {"route": route, "intent": intent}),
        )
    except Exception as exc:
        # Deterministic fallback
        question = state.get("user_question") or state.get("question", "")
        needs_rag = any(kw in question for kw in ["법", "판례", "법령", "조항", "특약", "등기", "보증", "전입", "대항력"])
        route = "BOTH" if needs_rag else "COUNSELOR"
        return _merge(
            state,
            route=route,
            intent="LEGAL_RAG_REQUIRED" if needs_rag else "GENERAL_CHAT",
            needs_rag=needs_rag,
            supervisor_status="fallback",
            reason=f"LLM unavailable: {exc}",
            current_agent="legal_supervisor",
            trace=_trace("Legal Supervisor", "deterministic_fallback", {"question": question[:100]}, {"route": route}),
        )


def route_after_legal_supervisor(state: LegalConsultationState) -> str:
    """라우팅: LEGAL_RAG/BOTH → legal_rag_agent, 나머지 → friendly_counselor_agent."""
    route = state.get("route", "COUNSELOR")
    if route in {"LEGAL_RAG", "BOTH"}:
        return "legal_rag_agent"
    return "friendly_counselor_agent"


def legal_rag_agent_node(state: LegalConsultationState) -> LegalConsultationState:
    """RAG 검색 + ReAct: 법령·판례 근거로 답변 초안 생성."""
    question = state.get("user_question") or state.get("question", "")
    qtype = state.get("question_type") or _classify_question(question)

    # RAG 검색
    pack = adaptive_rag(
        "legal_rag_search",
        question,
        filters={"doc_type": ["법령", "판례", "사례집"]},
        top_k=6,
    )

    # 초안 답변
    cases = _extract_cases(pack)
    laws = _extract_laws(pack)
    draft = _generate_answer_from_rag(question, cases, laws, pack)

    refs = list(state.get("evidence_refs", []))
    for ctx in pack.contexts:
        refs.append({"source_id": ctx.source_id, "title": ctx.title, "doc_type": ctx.doc_type, "score": ctx.score})

    return _merge(
        state,
        question_type=qtype,
        internal_case_context=pack,
        cited_cases=cases,
        cited_laws=laws,
        answer_draft=draft,
        draft_answer=draft,
        evidence_refs=refs,
        current_agent="legal_rag_agent",
        legal_rag_result={"draft": draft, "case_count": len(cases), "law_count": len(laws)},
        trace=_trace("Legal RAG Agent", "search_and_draft", {"question": question[:100]}, {"case_count": len(cases), "law_count": len(laws)}),
    )


def route_after_legal_rag(state: LegalConsultationState) -> str:
    """RAG 결과가 충분하면 review로, 아니면 counselor 보완."""
    refs = state.get("evidence_refs", [])
    route = state.get("route", "BOTH")
    if route == "BOTH" or not refs:
        return "friendly_counselor_agent"
    return "legal_review_node"


def counselor_agent_node(state: LegalConsultationState) -> LegalConsultationState:
    """친절한 상담사 톤으로 답변 재작성 / 보완."""
    draft = state.get("answer_draft") or state.get("draft_answer", "")
    question = state.get("user_question") or state.get("question", "")

    try:
        from common.agents.counselor_agent import run_counselor_agent
        result = run_counselor_agent(question=question, draft_answer=draft, state=state)
        counselor_answer = result.get("answer", draft)
    except Exception:
        counselor_answer = draft or f"'{question}' 에 대한 답변을 준비 중입니다. 전문가 상담을 권장합니다."

    return _merge(
        state,
        answer_draft=counselor_answer,
        draft_answer=counselor_answer,
        current_agent="friendly_counselor_agent",
        counselor_result={"answer": counselor_answer},
        trace=_trace("Friendly Counselor Agent", "rewrite_for_user", {"question": question[:80]}, {"answer_length": len(counselor_answer)}),
    )


def legal_review_node(state: LegalConsultationState) -> LegalConsultationState:
    """답변 품질 검토: RAG 근거 충분성 / 법률 과신 문구 점검."""
    try:
        from common.agents.review_supervisor_agent import review_agent_output
        result = review_agent_output(
            current_task=state.get("question_type"),
            current_agent=state.get("current_agent"),
            claims=state.get("claims", []),
            evidence_refs=state.get("evidence_refs", []),
            graph_context=state.get("graph_context", []),
            draft_answer=state.get("draft_answer", ""),
            mode="legal",
        )
        status = result.status.value if hasattr(result.status, "value") else str(result.status)
    except Exception:
        status = "PASS"

    review_count = state.get("review_count", 0) + 1
    return _merge(
        state,
        review_count=review_count,
        review_result={"status": status},
        last_review_status=status,
        current_agent="legal_review_node",
        trace=_trace("Legal Review Supervisor", "review_legal_output", {}, {"status": status, "review_count": review_count}),
    )


def route_after_legal_review(state: LegalConsultationState) -> str:
    """리뷰 결과에 따라 다음 노드 결정."""
    status = (state.get("review_result") or {}).get("status", "PASS")
    review_count = state.get("review_count", 0)
    max_reviews = state.get("max_review_count", 2)

    if status == "PASS" or review_count >= max_reviews:
        return "legal_guardrail"
    if status == "NEED_MORE_EVIDENCE":
        return "extra_rag_search"
    if status == "NEED_GRAPH_CONTEXT":
        return "graph_context_node"
    if status == "NEED_COUNSELOR_REWRITE":
        return "friendly_counselor_agent"
    if status in ("REVISION_REQUIRED",):
        return "legal_rag_agent"
    if status == "FAIL":
        return "safe_fallback"
    return "legal_guardrail"


def extra_legal_rag_search_node(state: LegalConsultationState) -> LegalConsultationState:
    """추가 RAG 검색: 근거 부족 시 보완 검색."""
    question = state.get("user_question") or state.get("question", "")
    extra_pack = adaptive_rag(
        "extra_legal_search",
        question,
        filters={"doc_type": ["법령", "판례", "사례집"]},
        top_k=5,
    )
    cases = _extract_cases(extra_pack)
    laws = _extract_laws(extra_pack)
    refs = list(state.get("evidence_refs", []))
    for ctx in extra_pack.contexts:
        refs.append({"source_id": ctx.source_id, "title": ctx.title, "doc_type": ctx.doc_type, "score": ctx.score})

    return _merge(
        state,
        evidence_refs=refs,
        cited_cases=list(state.get("cited_cases", [])) + cases,
        cited_laws=list(state.get("cited_laws", [])) + laws,
        last_review_status="PASS",
        trace=_trace("Extra Legal RAG", "additional_legal_search", {"question": question[:80]}, {"added_contexts": len(extra_pack.contexts)}),
    )


def route_after_extra_legal_rag(state: LegalConsultationState) -> str:
    """추가 검색 후 legal_rag_agent로 재시도."""
    return "legal_rag_agent"


def legal_graph_context_node(state: LegalConsultationState) -> LegalConsultationState:
    """Neo4j 그래프 컨텍스트 조회 (관계 기반 법률 검증)."""
    graph_ctx = list(state.get("graph_context", []))
    try:
        from common.tools.v7_contracts import fetch_graph_context  # type: ignore
        question = state.get("user_question") or state.get("question", "")
        new_ctx = fetch_graph_context({"question": question})
        graph_ctx.extend(new_ctx)
    except Exception:
        pass

    return _merge(
        state,
        graph_context=graph_ctx,
        last_review_status="PASS",
        trace=_trace("Legal Graph Context", "fetch_graph_context", {}, {"context_count": len(graph_ctx)}),
    )


def route_after_legal_graph_context(state: LegalConsultationState) -> str:
    """그래프 컨텍스트 조회 후 legal_rag_agent로 재시도."""
    return "legal_rag_agent"


def safe_legal_fallback_node(state: LegalConsultationState) -> LegalConsultationState:
    """폴백: 안전한 일반 안내 답변 생성."""
    question = state.get("user_question") or state.get("question", "")
    safe_answer = (
        f"'{question[:50]}' 에 대한 정확한 법적 답변을 제공하기 어렵습니다. "
        "전세사기 피해가 우려되시면 법률구조공단(132) 또는 주택도시보증공사(1566-9009)에 문의하시길 권장합니다.\n\n"
        + DISCLAIMER
    )
    return _merge(
        state,
        answer_draft=safe_answer,
        draft_answer=safe_answer,
        safe_answer=safe_answer,
        safe_fallback={"answer": safe_answer, "reason": "max_review_exceeded_or_fail"},
        trace=_trace("Safe Legal Fallback", "generate_safe_answer", {}, {"answer_length": len(safe_answer)}),
    )


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _generate_answer_from_rag(question: str, cases: list, laws: list, pack: Any) -> str:
    """RAG 컨텍스트 기반 답변 초안 생성."""
    try:
        from common.tools.llm import build_chat_llm
        ctx_text = "\n\n".join(
            f"[{i+1}] {ctx.title}\n{ctx.text[:500]}"
            for i, ctx in enumerate(pack.contexts[:5])
        ) if hasattr(pack, "contexts") else ""
        llm = build_chat_llm(temperature=0.1)
        prompt = f"질문: {question}\n\n참고 자료:\n{ctx_text}\n\n위 자료를 바탕으로 친절하고 명확하게 답변해 주세요."
        response = llm.invoke([("human", prompt)])
        return response.content if hasattr(response, "content") else str(response)
    except Exception:
        case_titles = ", ".join(c.case_name for c in cases[:3]) if cases else "관련 판례 없음"
        law_titles = ", ".join(l.article for l in laws[:3]) if laws else "관련 법령 없음"
        return (
            f"'{question}' 에 대한 검색 결과:\n"
            f"- 관련 판례: {case_titles}\n"
            f"- 관련 법령: {law_titles}\n\n"
            "정확한 법률 해석을 위해서는 전문가 상담을 권장합니다."
        )

