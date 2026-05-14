"""LangGraph state nodes for the jeonse diagnosis workflow."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any


from common.agents.diagnosis_agents import analyze_special_clauses_with_llm, run_special_clause_react_agent
from common.schemas.diagnosis import DiagnosisState
from common.schemas.shared import AgentTrace, ContextPack, RiskFinding
from common.tools.adaptive_rag import adaptive_rag
from common.tools.document import extract_contract_fields, parse_contract_file
from common.tools.market import analyze_market


def contract_intake_node(state: DiagnosisState) -> DiagnosisState:
    file_path = state.get("contract_file")
    missing = list(state.get("missing_inputs", []))
    errors = list(state.get("errors", []))

    if file_path:
        suffix = Path(file_path).suffix.lower()
        if suffix not in {".pdf", ".txt", ".md", ".png", ".jpg", ".jpeg"}:
            errors.append(f"지원하지 않는 계약서 형식입니다: {suffix}")
    else:
        missing.append("contract_file: 테스트용 mock 계약서로 진행")

    return _merge(state, analysis_ready=not errors, missing_inputs=missing, errors=errors, trace=_trace("Contract Intake Agent", "validate_contract_input", {"contract_file": file_path}, {"analysis_ready": not errors}))


def contract_parser_node(state: DiagnosisState) -> DiagnosisState:
    text, pages, confidence = parse_contract_file(state.get("contract_file"))
    return _merge(state, contract_text=text, page_texts=pages, ocr_confidence=confidence, trace=_trace("Contract Parser Agent", "parse_pdf_or_text", {"contract_file": state.get("contract_file")}, {"text_length": len(text), "pages": len(pages)}))


def contract_field_extractor_node(state: DiagnosisState) -> DiagnosisState:
    fields = extract_contract_fields(state.get("contract_text", ""))
    return _merge(state, contract_fields=fields, trace=_trace("Contract Field Extractor Agent", "extract_structured_fields", {}, {"fields": fields}))


def special_clause_analysis_node(state: DiagnosisState) -> DiagnosisState:
    fields = state.get("contract_fields", {})
    terms = fields.get("special_terms") or []
    query = "\n".join(str(term) for term in terms) or state.get("contract_text", "")[:1500]
    context_pack = adaptive_rag("special_clause_analysis", query, filters={"doc_type": ["사례집", "법령", "판례", "서식"]}, top_k=5)
    react_summary = run_special_clause_react_agent(query)

    findings: list[RiskFinding] = []
    revisions: list[str] = []
    missing_defensive: list[RiskFinding] = []

    joined = "\n".join(str(term) for term in terms)
    structured = _analyze_special_clauses_with_llm(terms, context_pack)
    findings = structured["findings"]
    revisions = structured["revisions"]
    missing_defensive = structured["missing_defensive"]

    if not findings:
        findings, revisions = _fallback_clause_findings(terms)
    if findings and not revisions:
        revisions = _revisions_from_findings(findings)

    if not missing_defensive:
        missing_defensive = _fallback_missing_defensive_clauses(joined)

    packs = dict(state.get("context_packs", {}))
    packs["special_clause_analysis"] = context_pack
    outputs = {"finding_count": len(findings), "missing_defensive_count": len(missing_defensive), "react_agent_used": bool(react_summary), "analysis_mode": structured["mode"]}
    if react_summary:
        outputs["react_agent_summary"] = react_summary[:500]
    return _merge(state, context_packs=packs, clause_findings=findings, missing_defensive_clauses=missing_defensive, recommended_revisions=revisions, trace=_trace("Special Clause Analyzer ReAct Agent", "analyze_special_terms_with_rag", {"term_count": len(terms)}, outputs))


def _analyze_special_clauses_with_llm(terms: list[Any], context_pack: ContextPack) -> dict[str, Any]:
    if not terms:
        return {"findings": [], "missing_defensive": [], "revisions": [], "mode": "empty_terms"}

    context_text = _context_text(context_pack)
    try:
        data = analyze_special_clauses_with_llm(terms, context_text)
        findings = [_finding_from_llm(item, terms) for item in data.get("findings", []) if isinstance(item, dict)]
        findings = [finding for finding in findings if finding is not None]
        missing = [_missing_from_llm(item) for item in data.get("missing_defensive_clauses", []) if isinstance(item, dict)]
        missing = [finding for finding in missing if finding is not None]
        revisions = [str(item) for item in data.get("recommended_revisions", []) if str(item).strip()]
        return {"findings": findings, "missing_defensive": missing, "revisions": revisions, "mode": "rag_llm_structured"}
    except Exception:
        return {"findings": [], "missing_defensive": [], "revisions": [], "mode": "fallback_keyword_rule"}


def _fallback_clause_findings(terms: list[Any]) -> tuple[list[RiskFinding], list[str]]:
    findings: list[RiskFinding] = []
    revisions: list[str] = []
    joined = "\n".join(str(term) for term in terms)
    risky_patterns = [
        ("CLAUSE_REPAIR_ALL", "수리비 전액 임차인 부담", "수리비를 임차인이 전액 부담하는 문구는 통상적인 사용 손모까지 임차인에게 전가할 수 있어 위험합니다.", ["수리비", "전액", "임차인"]),
        ("CLAUSE_LATE_RETURN", "보증금 반환 지연 가능 특약", "보증금 반환 시점을 과도하게 늦추는 문구는 반환 위험을 키울 수 있습니다.", ["보증금", "반환", "이후"]),
        ("CLAUSE_NO_OWNER_RESP", "임대인 책임 제한 특약", "권리 변동이나 하자에 대한 임대인 책임을 배제하는 문구는 위험합니다.", ["책임지지", "권리", "변동"]),
    ]
    for code, title, description, tokens in risky_patterns:
        if all(token in joined for token in tokens):
            findings.append(RiskFinding(code=code, title=title, severity="HIGH", score_delta=15, description=description, evidence=[str(term) for term in terms], required_action="특약 삭제 또는 책임 범위를 명확히 제한하는 수정 문구를 요청하세요.", source="special_clause_analyzer:fallback"))
            revisions.append(f"{title}: 임차인의 통상 사용으로 인한 손모는 제외하고, 임대인의 수선 의무와 보증금 반환 기한을 명확히 쓰는 방향으로 수정 권장")
    return findings, revisions


def _revisions_from_findings(findings: list[RiskFinding]) -> list[str]:
    revisions: list[str] = []
    for finding in findings:
        if finding.required_action:
            revisions.append(f"{finding.title}: {finding.required_action}")
        else:
            revisions.append(f"{finding.title}: RAG 근거를 바탕으로 해당 특약의 삭제 또는 책임 범위 명확화를 요청하세요.")
    return revisions


def _fallback_missing_defensive_clauses(joined_terms: str) -> list[RiskFinding]:
    if "잔금" in joined_terms and "권리변동" in joined_terms:
        return []
    return [
        RiskFinding(
            code="MISSING_NO_NEW_LIEN",
            title="잔금 전후 권리변동 금지 특약 부족",
            severity="MEDIUM",
            score_delta=10,
            description="잔금일 전후 임대인이 근저당권 등 새로운 권리를 설정하지 않는다는 방어 특약이 보이지 않습니다.",
            required_action="잔금일 다음날까지 근저당권 등 제한물권을 설정하지 않는다는 특약을 추가 검토하세요.",
            source="special_clause_analyzer:fallback",
        )
    ]


def _finding_from_llm(item: dict[str, Any], terms: list[Any]) -> RiskFinding | None:
    title = str(item.get("title") or "").strip()
    description = str(item.get("description") or "").strip()
    if not title or not description:
        return None
    severity = str(item.get("severity") or "MEDIUM").upper()
    if severity not in {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        severity = "MEDIUM"
    score_delta = _safe_int(item.get("score_delta"), 10)
    evidence = item.get("evidence")
    evidence_list = [str(value) for value in evidence] if isinstance(evidence, list) else [str(term) for term in terms]
    return RiskFinding(
        code=str(item.get("code") or _slug_code(title)),
        title=title,
        severity=severity,  # type: ignore[arg-type]
        score_delta=max(0, min(score_delta, 25)),
        description=description,
        evidence=evidence_list,
        required_action=str(item.get("required_action") or "계약 전 해당 특약의 삭제 또는 수정을 요청하세요."),
        source="special_clause_analyzer:rag_llm",
    )


def _missing_from_llm(item: dict[str, Any]) -> RiskFinding | None:
    title = str(item.get("title") or "").strip()
    description = str(item.get("description") or "").strip()
    if not title or not description:
        return None
    severity = str(item.get("severity") or "MEDIUM").upper()
    if severity not in {"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        severity = "MEDIUM"
    return RiskFinding(
        code=str(item.get("code") or _slug_code(title).replace("CLAUSE_", "MISSING_")),
        title=title,
        severity=severity,  # type: ignore[arg-type]
        score_delta=max(0, min(_safe_int(item.get("score_delta"), 10), 20)),
        description=description,
        evidence=[],
        required_action=str(item.get("required_action") or "계약 전 해당 방어 특약 추가를 요청하세요."),
        source="special_clause_analyzer:rag_llm",
    )


def _context_text(context_pack: ContextPack) -> str:
    if not context_pack.contexts:
        return "검색된 RAG 근거가 없습니다."
    return "\n\n".join(
        f"[{idx}] {ctx.title} ({ctx.doc_type}, score={ctx.score})\n{ctx.text}"
        for idx, ctx in enumerate(context_pack.contexts, 1)
    )


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _slug_code(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value.upper())
    return f"CLAUSE_{cleaned[:40].strip('_') or 'RISK'}"


def market_analysis_node(state: DiagnosisState) -> DiagnosisState:
    analysis, findings = analyze_market(state.get("contract_fields", {}))
    return _merge(state, market_analysis=analysis, market_findings=findings, trace=_trace("Market Analyzer Agent", "compare_jeonse_and_sale_data", asdict(analysis), {"finding_count": len(findings)}))


def required_check_node(state: DiagnosisState) -> DiagnosisState:
    fields = state.get("contract_fields", {})
    query = f"전세계약서만 입력된 상태에서 추가 확인이 필요한 위험 항목. 주소={fields.get('address')} 유형={fields.get('housing_type')}"
    context_pack = adaptive_rag("required_check_analysis", query, filters={"doc_type": ["사례집", "법령", "서식"]}, top_k=5)

    findings = [
        RiskFinding("REQUIRED_REGISTRY", "등기부 권리관계 확인 필요", "HIGH", 20, "계약서만으로는 근저당권, 압류, 가압류, 신탁 등 권리관계를 확인할 수 없습니다.", required_action="계약 직전 등기부등본 갑구/을구를 확인하세요.", source="required_check_analyzer"),
        RiskFinding("REQUIRED_OWNER_MATCH", "임대인과 소유자 일치 확인 필요", "HIGH", 15, "계약서상 임대인이 실제 등기부 소유자인지 계약서만으로 확정할 수 없습니다.", required_action="등기부 소유자와 신분증/위임장을 대조하세요.", source="required_check_analyzer"),
        RiskFinding("REQUIRED_TAX", "체납 세금 확인 필요", "MEDIUM", 10, "국세/지방세 체납은 보증금 회수 위험과 연결될 수 있으나 계약서만으로 알 수 없습니다.", required_action="납세증명서 또는 관련 확인 절차를 요청하세요.", source="required_check_analyzer"),
    ]
    if fields.get("housing_type") in {"단독다가구", "단독", "다가구"}:
        findings.append(RiskFinding("REQUIRED_SENIOR_TENANTS", "다가구 선순위 보증금 확인 필요", "HIGH", 20, "단독/다가구는 다른 세입자의 선순위 보증금 규모가 중요하지만 계약서만으로 확인하기 어렵습니다.", required_action="전입세대확인서, 확정일자 부여 현황, 임대인 고지 내용을 확인하세요.", source="required_check_analyzer"))

    packs = dict(state.get("context_packs", {}))
    packs["required_check_analysis"] = context_pack
    return _merge(state, context_packs=packs, required_check_findings=findings, trace=_trace("Required Check Analyzer Agent", "list_contract_only_unknown_risks", {}, {"finding_count": len(findings)}))


def risk_judge_node(state: DiagnosisState) -> DiagnosisState:
    findings: list[RiskFinding] = []
    findings.extend(state.get("clause_findings", []))
    findings.extend(state.get("missing_defensive_clauses", []))
    findings.extend(state.get("market_findings", []))
    findings.extend(state.get("required_check_findings", []))

    score = min(100, sum(max(0, finding.score_delta) for finding in findings))
    if score >= 75:
        level = "CRITICAL"
    elif score >= 50:
        level = "HIGH"
    elif score >= 25:
        level = "MEDIUM"
    else:
        level = "LOW"

    return _merge(state, risk_findings=findings, risk_score=score, risk_level=level, trace=_trace("Risk Judge Agent", "aggregate_rule_based_score", {"finding_count": len(findings)}, {"risk_score": score, "risk_level": level}))


def report_writer_node(state: DiagnosisState) -> DiagnosisState:
    context_pack = adaptive_rag("report_generation", "전세계약 위험 진단 결과 리포트 작성", filters={"doc_type": ["사례집", "법령"]}, top_k=3)
    packs = dict(state.get("context_packs", {}))
    packs["report_generation"] = context_pack

    report_trace = _trace("Report Writer Agent", "compose_user_report", {}, {"sections": ["title", "disclaimer", "risk_score", "risk_level", "contract_fields", "market_analysis", "findings", "recommended_revisions", "next_checks", "rag_references", "agent_trace"]})
    full_trace = list(state.get("agent_trace", [])) + [report_trace]

    report = {
        "title": "전세계약 위험 진단 리포트",
        "disclaimer": "본 결과는 법률 자문이 아니라 계약 전 위험 확인을 돕는 보조 정보입니다.",
        "contract_file": state.get("contract_file"),
        "contract_source": "uploaded_file" if state.get("contract_file") else "mock_contract",
        "risk_score": state.get("risk_score", 0),
        "risk_level": state.get("risk_level", "UNKNOWN"),
        "contract_fields": state.get("contract_fields", {}),
        "market_analysis": asdict(state.get("market_analysis")) if state.get("market_analysis") else None,
        "findings": [asdict(finding) for finding in state.get("risk_findings", [])],
        "recommended_revisions": state.get("recommended_revisions", []),
        "next_checks": [finding.required_action for finding in state.get("risk_findings", []) if finding.required_action],
        "rag_references": _summarize_context_packs(packs),
        "agent_trace": [asdict(trace) for trace in full_trace],
    }
    return _merge(state, context_packs=packs, report=report, trace=report_trace)


def _summarize_context_packs(packs: dict[str, ContextPack]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for task_type, pack in packs.items():
        for context in pack.contexts:
            refs.append({"task_type": task_type, "title": context.title, "doc_type": context.doc_type, "source_id": context.source_id, "score": context.score})
    return refs


def _merge(state: DiagnosisState, *, trace: AgentTrace | None = None, **updates: Any) -> DiagnosisState:
    next_state: DiagnosisState = dict(state)
    next_state.update(updates)
    if trace:
        traces = list(next_state.get("agent_trace", []))
        traces.append(trace)
        next_state["agent_trace"] = traces
    return next_state


def _trace(agent: str, action: str, inputs: dict[str, Any], outputs: dict[str, Any]) -> AgentTrace:
    return AgentTrace(agent=agent, action=action, inputs=inputs, outputs=outputs)


# ──────────────────────────────────────────────────────────────────────────────
# v7 task-queue nodes (added to match diagnosis_graph.py imports)
# ──────────────────────────────────────────────────────────────────────────────

_TASK_ORDER = ["special_clause", "market_risk", "ownership_risk", "insurance_risk", "required_check", "legal_basis"]


def contract_supervisor_node(state: DiagnosisState) -> DiagnosisState:
    """Task-queue supervisor: initialises pending_tasks or marks current task done."""
    pending = list(state.get("pending_tasks", []))
    completed = list(state.get("completed_tasks", []))

    if not pending and not completed:
        # First call – build task queue based on contract content
        fields = state.get("contract_fields", {})
        queue: list[str] = []
        if fields.get("special_terms"):
            queue.append("special_clause")
        queue.extend(["market_risk", "required_check", "ownership_risk", "insurance_risk", "legal_basis"])
        pending = [t for t in queue if t not in completed]

    return _merge(
        state,
        pending_tasks=pending,
        completed_tasks=completed,
        trace=_trace(
            "Contract Supervisor",
            "manage_task_queue",
            {"completed": completed},
            {"pending": pending},
        ),
    )


def route_after_supervisor(state: DiagnosisState) -> str:
    """Route to next pending task or to risk_judge when all done."""
    pending = state.get("pending_tasks", [])
    if not pending:
        return "judge"
    return pending[0]


def contract_review_node(state: DiagnosisState) -> DiagnosisState:
    """Simple review gate: checks if the last agent produced findings."""
    review_count = state.get("review_count", 0) + 1
    last_task = (state.get("pending_tasks") or [None])[0]

    # Determine review status deterministically
    has_evidence = bool(state.get("evidence_refs") or state.get("context_packs"))
    status = "PASS" if has_evidence else "NEED_MORE_EVIDENCE"

    # Mark task complete and advance queue
    pending = list(state.get("pending_tasks", []))
    completed = list(state.get("completed_tasks", []))
    if pending:
        done = pending.pop(0)
        if done not in completed:
            completed.append(done)

    return _merge(
        state,
        review_count=review_count,
        last_review_status=status,
        last_reviewed_task=last_task,
        pending_tasks=pending,
        completed_tasks=completed,
        trace=_trace(
            "Contract Review Supervisor",
            "review_agent_output",
            {"task": last_task, "review_count": review_count},
            {"status": status},
        ),
    )


def route_after_review(state: DiagnosisState) -> str:
    """Decide what to do after review."""
    status = state.get("last_review_status", "PASS")
    review_count = state.get("review_count", 0)
    max_reviews = state.get("max_review_count", 2)

    if status == "PASS" or review_count >= max_reviews:
        return "supervisor"
    if status == "NEED_MORE_EVIDENCE":
        return "extra_rag"
    if status == "NEED_GRAPH_CONTEXT":
        return "graph_context"
    if status in ("REVISION_REQUIRED", "FAIL"):
        return "fallback"
    return "supervisor"


def extra_rag_search_node(state: DiagnosisState) -> DiagnosisState:
    """Additional RAG search when initial evidence is insufficient."""
    last_task = state.get("last_reviewed_task") or "general"
    query = state.get("contract_text", "")[:1000] or "전세계약 위험 확인"
    context_pack = adaptive_rag(f"extra_{last_task}", query, filters={"doc_type": ["사례집", "법령", "판례"]}, top_k=5)
    packs = dict(state.get("context_packs", {}))
    packs[f"extra_{last_task}"] = context_pack

    refs = list(state.get("evidence_refs", []))
    for ctx in context_pack.contexts:
        refs.append({"source_id": ctx.source_id, "title": ctx.title, "doc_type": ctx.doc_type, "score": ctx.score})

    return _merge(
        state,
        context_packs=packs,
        evidence_refs=refs,
        last_review_status="PASS",
        trace=_trace("Extra RAG Search", "additional_rag_retrieval", {"task": last_task}, {"added_contexts": len(context_pack.contexts)}),
    )


def route_after_extra_rag(state: DiagnosisState) -> str:
    """After extra RAG, re-route to the task that needed more evidence."""
    last_task = state.get("last_reviewed_task")
    if last_task and last_task in _TASK_ORDER:
        return last_task
    return "fallback"


def graph_context_node(state: DiagnosisState) -> DiagnosisState:
    """Fetch graph-DB context for relationship-based validation."""
    # Lightweight stub – attempts Neo4j if available, else returns empty context
    graph_ctx = list(state.get("graph_context", []))
    try:
        from common.tools.v7_contracts import fetch_graph_context  # type: ignore
        fields = state.get("contract_fields", {})
        new_ctx = fetch_graph_context(fields)
        graph_ctx.extend(new_ctx)
    except Exception:
        pass

    return _merge(
        state,
        graph_context=graph_ctx,
        last_review_status="PASS",
        trace=_trace("Graph Context Agent", "fetch_neo4j_context", {}, {"context_count": len(graph_ctx)}),
    )


def route_after_graph_context(state: DiagnosisState) -> str:
    """After graph context fetch, re-route to the task that needed it."""
    last_task = state.get("last_reviewed_task")
    if last_task and last_task in _TASK_ORDER:
        return last_task
    return "fallback"


def safe_contract_fallback_node(state: DiagnosisState) -> DiagnosisState:
    """Fallback: clear review loop and add a generic warning finding."""
    fallback_finding = RiskFinding(
        code="FALLBACK_INCOMPLETE_REVIEW",
        title="일부 항목 검토 미완료",
        severity="MEDIUM",
        score_delta=5,
        description="RAG 근거 부족으로 일부 항목을 완전히 검토하지 못했습니다. 전문가 상담을 권장합니다.",
        required_action="공인중개사 또는 법률 전문가의 추가 확인을 받으세요.",
        source="safe_fallback",
    )
    existing = list(state.get("risk_findings", []))
    codes = {f.code for f in existing}
    if fallback_finding.code not in codes:
        existing.append(fallback_finding)

    # Clear pending to break loops
    return _merge(
        state,
        pending_tasks=[],
        review_count=0,
        last_review_status="PASS",
        risk_findings=existing,
        trace=_trace("Safe Fallback", "inject_fallback_finding", {}, {"finding": fallback_finding.code}),
    )


# ── Agent node aliases (rename wrappers for graph compatibility) ───────────────

def special_clause_agent_node(state: DiagnosisState) -> DiagnosisState:
    """ReAct wrapper: special clause analysis → updates evidence_refs."""
    state = special_clause_analysis_node(state)
    refs = list(state.get("evidence_refs", []))
    for pack in state.get("context_packs", {}).values():
        for ctx in pack.contexts:
            refs.append({"source_id": ctx.source_id, "title": ctx.title, "doc_type": ctx.doc_type, "score": ctx.score})
    return _merge(state, evidence_refs=refs)


def market_risk_agent_node(state: DiagnosisState) -> DiagnosisState:
    """ReAct wrapper: market price risk analysis with market RAG evidence."""
    state = market_analysis_node(state)
    fields = state.get("contract_fields", {})
    analysis = state.get("market_analysis")
    ratio = getattr(analysis, "estimated_jeonse_ratio", None) if analysis else None
    query = (
        "전세 가격 위험도 전세가율 깡통전세 보증금 반환 위험 "
        f"동={fields.get('dong_name') or ''} "
        f"유형={fields.get('housing_type') or ''} "
        f"보증금={fields.get('deposit_amount') or ''} "
        f"면적={fields.get('exclusive_area_m2') or ''} "
        f"전세가율={ratio if ratio is not None else ''}"
    )
    context_pack = adaptive_rag(
        "market_risk_analysis",
        query,
        filters={
            "tables": ["market_risk_guides", "public_guides", "case_documents"],
            "domain": ["market_risk", "jeonse_ratio", "market_analysis"],
            "source_type": ["market_data", "public_guide", "case"],
            "include_graph_context": True,
        },
        top_k=5,
    )
    packs = dict(state.get("context_packs", {}))
    packs["market_risk_analysis"] = context_pack
    refs = list(state.get("evidence_refs", []))
    for ctx in context_pack.contexts:
        ref = {"source_id": ctx.source_id, "title": ctx.title, "doc_type": ctx.doc_type, "score": ctx.score}
        if ref not in refs:
            refs.append(ref)
    graph_context = list(state.get("graph_context", []))
    graph_context.extend(context_pack.graph_context)
    return _merge(
        state,
        context_packs=packs,
        evidence_refs=refs,
        graph_context=graph_context,
        trace=_trace(
            "Market Risk Agent",
            "analyze_market_with_rag",
            {"deposit": fields.get("deposit_amount"), "dong": fields.get("dong_name")},
            {
                "finding_count": len(state.get("market_findings", [])),
                "context_count": len(context_pack.contexts),
                "graph_context_count": len(context_pack.graph_context),
            },
        ),
    )


def ownership_risk_agent_node(state: DiagnosisState) -> DiagnosisState:
    """Ownership / registry risk analysis (RAG-based)."""
    fields = state.get("contract_fields", {})
    query = (
        f"등기부 권리관계 확인 위험: 주소={fields.get('address')}, "
        f"임대인={fields.get('landlord_name')}, 유형={fields.get('housing_type')}"
    )
    context_pack = adaptive_rag("ownership_risk", query, filters={"doc_type": ["사례집", "법령", "판례"]}, top_k=5)

    findings: list[RiskFinding] = [
        RiskFinding(
            code="OWNERSHIP_REGISTRY_CHECK",
            title="등기부 권리관계 현장 확인 필요",
            severity="HIGH",
            score_delta=20,
            description="근저당권·압류·가압류·신탁·가등기 등 권리제한 사항은 등기부등본으로만 확인 가능합니다.",
            required_action="잔금 전일 등기부등본을 직접 발급·열람하여 갑구·을구를 확인하세요.",
            source="ownership_risk_agent",
        )
    ]

    packs = dict(state.get("context_packs", {}))
    packs["ownership_risk"] = context_pack
    refs = list(state.get("evidence_refs", []))
    for ctx in context_pack.contexts:
        refs.append({"source_id": ctx.source_id, "title": ctx.title, "doc_type": ctx.doc_type, "score": ctx.score})

    return _merge(
        state,
        context_packs=packs,
        evidence_refs=refs,
        risk_findings=list(state.get("risk_findings", [])) + findings,
        trace=_trace("Ownership Risk Agent", "analyze_registry_risk", {"address": fields.get("address")}, {"finding_count": len(findings)}),
    )


def insurance_risk_agent_node(state: DiagnosisState) -> DiagnosisState:
    """Deposit insurance / HUG coverage risk analysis."""
    fields = state.get("contract_fields", {})
    query = f"전세보증보험 가입 가능성 분석: 보증금={fields.get('deposit_amount')}, 유형={fields.get('housing_type')}"
    context_pack = adaptive_rag("insurance_risk", query, filters={"doc_type": ["사례집", "법령"]}, top_k=5)

    deposit = fields.get("deposit_amount") or 0
    findings: list[RiskFinding] = []
    if isinstance(deposit, (int, float)) and deposit > 0:
        findings.append(
            RiskFinding(
                code="INSURANCE_HUG_CHECK",
                title="전세보증보험 가입 가능 여부 확인 필요",
                severity="MEDIUM",
                score_delta=8,
                description="HUG·SGI·HF 보증보험 가입 가능 여부를 사전에 확인해야 보증금 미반환 리스크를 줄일 수 있습니다.",
                required_action="전세보증보험 가입 조건(전세가율·주택 유형·채권최고액 등)을 계약 전 확인하세요.",
                source="insurance_risk_agent",
            )
        )

    packs = dict(state.get("context_packs", {}))
    packs["insurance_risk"] = context_pack
    refs = list(state.get("evidence_refs", []))
    for ctx in context_pack.contexts:
        refs.append({"source_id": ctx.source_id, "title": ctx.title, "doc_type": ctx.doc_type, "score": ctx.score})

    return _merge(
        state,
        context_packs=packs,
        evidence_refs=refs,
        risk_findings=list(state.get("risk_findings", [])) + findings,
        trace=_trace("Insurance Risk Agent", "analyze_deposit_insurance", {"deposit": deposit}, {"finding_count": len(findings)}),
    )


def legal_basis_agent_node(state: DiagnosisState) -> DiagnosisState:
    """Legal basis validation: cross-checks contract terms against statutes."""
    fields = state.get("contract_fields", {})
    query = f"주택임대차보호법 위반 여부 확인: 계약 기간={fields.get('contract_period')}, 보증금={fields.get('deposit_amount')}"
    context_pack = adaptive_rag("legal_basis", query, filters={"doc_type": ["법령", "판례"]}, top_k=5)

    findings: list[RiskFinding] = []
    period = fields.get("contract_period") or ""
    if period and "1년" in str(period):
        findings.append(
            RiskFinding(
                code="LEGAL_MIN_PERIOD",
                title="임대차 최단 기간 미달 가능성",
                severity="MEDIUM",
                score_delta=10,
                description="주택임대차보호법상 최단 임대차 기간은 2년입니다. 1년 계약은 임차인이 2년을 주장할 수 있습니다.",
                required_action="계약 기간을 2년으로 명시하거나 법적 최단 기간 보호를 숙지하세요.",
                source="legal_basis_agent",
            )
        )

    packs = dict(state.get("context_packs", {}))
    packs["legal_basis"] = context_pack
    refs = list(state.get("evidence_refs", []))
    for ctx in context_pack.contexts:
        refs.append({"source_id": ctx.source_id, "title": ctx.title, "doc_type": ctx.doc_type, "score": ctx.score})

    return _merge(
        state,
        context_packs=packs,
        evidence_refs=refs,
        risk_findings=list(state.get("risk_findings", [])) + findings,
        trace=_trace("Legal Basis Agent", "validate_contract_legality", {"period": period}, {"finding_count": len(findings)}),
    )


def required_check_agent_node(state: DiagnosisState) -> DiagnosisState:
    """Alias: required check items (계약서 외 추가 확인 사항)."""
    return required_check_node(state)



