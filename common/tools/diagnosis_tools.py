"""Diagnosis agent-specific tools following the v7 RAG contract."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

try:
    from langchain_core.tools import tool
except ImportError:  # pragma: no cover
    def tool(func):
        return func

from common.schemas.shared import ContextPack, RiskFinding
from common.tools.adaptive_rag import adaptive_rag


def _evidence_refs(pack: ContextPack) -> list[dict[str, Any]]:
    return [
        {
            "source_id": context.source_id,
            "title": context.title,
            "doc_type": context.doc_type,
            "score": context.score,
            "chunk_text": context.text[:500],
        }
        for context in pack.contexts
    ]


def search_special_clause_rag(query: str, top_k: int = 5) -> ContextPack:
    return adaptive_rag(
        "special_clause_analysis",
        query,
        filters={
            "task_type": "special_clause_analysis",
            "tables": ["special_clause_examples", "law_documents", "public_guides", "case_documents"],
            "domain": ["special_clause", "lease_contract", "tenant_protection"],
            "source_type": ["checklist", "law", "case", "public_guide", "form"],
            "evidence_type": ["CHECKLIST", "STANDARD_CONTRACT", "LEGAL_GUIDE", "CASEBOOK", "LAW"],
            "include_graph_context": True,
        },
        top_k=top_k,
    )


def compare_standard_contract(special_terms: list[str]) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    for term in special_terms:
        text = str(term)
        if any(token in text for token in ["수리비", "원상복구", "하자"]):
            comparisons.append(
                {
                    "clause": text,
                    "standard_gap": "통상 사용 손모까지 임차인에게 전가하는지 확인 필요",
                    "suggestion": "임차인의 고의/과실로 인한 파손으로 책임 범위를 제한하세요.",
                }
            )
        if any(token in text for token in ["다음 임차인", "입주 이후", "입주 후"]) or ("보증금" in text and "반환" in text and "이후" in text):
            comparisons.append(
                {
                    "clause": text,
                    "standard_gap": "보증금 반환 기한이 새 임차인 입주에 종속될 수 있음",
                    "suggestion": "임대차 종료 및 목적물 인도와 동시에 반환하도록 명확히 쓰세요.",
                }
            )
    return comparisons


def classify_clause_risk(special_terms: list[str], comparisons: list[dict[str, Any]] | None = None) -> list[RiskFinding]:
    joined = "\n".join(str(term) for term in special_terms)
    findings: list[RiskFinding] = []
    patterns = [
        (
            "CLAUSE_REPAIR_ALL",
            "수리비 전액 임차인 부담",
            ["수리비", "전액", "임차인"],
            "통상 손모까지 임차인에게 전가될 수 있는 특약입니다.",
            "통상 손모는 제외하고 임차인의 고의/과실 범위로 제한하세요.",
            15,
        ),
        (
            "CLAUSE_DEPOSIT_NEXT_TENANT",
            "다음 임차인 입주 조건부 보증금 반환",
            ["보증금", "반환"],
            "보증금 반환이 새 임차인 입주나 임대인 자금 사정에 종속될 수 있습니다.",
            "반환 기한을 임대차 종료일 또는 목적물 인도일 기준으로 명확히 수정하세요.",
            15,
        ),
        (
            "CLAUSE_OWNER_NO_RESPONSIBILITY",
            "임대인 책임 제한 특약",
            ["책임지지", "권리", "변동"],
            "권리 변동이나 하자에 대한 임대인 책임을 배제할 수 있는 문구입니다.",
            "임대인의 권리관계 고지 및 담보책임을 배제하지 않도록 수정하세요.",
            15,
        ),
    ]
    for code, title, tokens, description, action, score in patterns:
        if code == "CLAUSE_DEPOSIT_NEXT_TENANT":
            matched = "보증금" in joined and "반환" in joined and any(token in joined for token in ["이후", "입주 후", "입주 이후", "다음 임차인", "새 임차인"])
        else:
            matched = all(token in joined for token in tokens)
        if matched:
            findings.append(
                RiskFinding(
                    code=code,
                    title=title,
                    severity="HIGH",
                    score_delta=score,
                    description=description,
                    evidence=[str(term) for term in special_terms],
                    required_action=action,
                    source="special_clause_agent:classify_clause_risk_tool",
                )
            )

    if "잔금" not in joined or "권리변동" not in joined:
        findings.append(
            RiskFinding(
                code="MISSING_NO_NEW_LIEN",
                title="잔금 전후 권리변동 금지 특약 부족",
                severity="MEDIUM",
                score_delta=10,
                description="잔금일 전후 임대인이 근저당권 등 새 제한물권을 설정하지 않는다는 방어 특약이 부족합니다.",
                required_action="잔금일 다음날까지 근저당권 등 제한물권을 설정하지 않는다는 특약을 추가 검토하세요.",
                source="special_clause_agent:classify_clause_risk_tool",
            )
        )
    return findings


def search_registry_rag(query: str, top_k: int = 5) -> ContextPack:
    return adaptive_rag(
        "registry_risk_analysis",
        query,
        filters={
            "task_type": "registry_risk_analysis",
            "tables": ["registry_guides", "contract_checklists", "law_documents", "case_documents", "public_guides"],
            "domain": ["registry", "senior_debt", "trust_registration", "tenant_protection"],
            "source_type": ["checklist", "law", "case", "public_guide"],
            "risk_category": ["REGISTRY_RISK", "TRUST_REGISTRATION", "IDENTITY_AUTHORITY"],
            "evidence_type": ["CHECKLIST", "CASEBOOK", "LAW", "LEGAL_GUIDE"],
            "include_graph_context": True,
        },
        top_k=top_k,
    )


def search_market_rag(query: str, top_k: int = 5) -> ContextPack:
    return adaptive_rag(
        "market_risk_analysis",
        query,
        filters={
            "task_type": "market_risk_analysis",
            "tables": ["market_risk_guides", "public_guides", "case_documents"],
            "domain": ["market_risk", "jeonse_ratio", "market_analysis"],
            "source_type": ["market_data", "public_guide", "case"],
            "include_graph_context": True,
        },
        top_k=top_k,
    )


def search_insurance_rag(query: str, top_k: int = 5) -> ContextPack:
    return adaptive_rag(
        "insurance_risk_analysis",
        query,
        filters={
            "task_type": "insurance_risk_analysis",
            "tables": ["insurance_guides", "public_guides", "law_documents"],
            "domain": ["insurance", "HUG", "HF", "SGI"],
            "source_type": ["insurance", "public_guide", "law"],
            "include_graph_context": True,
        },
        top_k=top_k,
    )


def search_required_check_rag(query: str, top_k: int = 5) -> ContextPack:
    return adaptive_rag(
        "required_check_analysis",
        query,
        filters={
            "task_type": "required_check_analysis",
            "tables": ["contract_checklists", "public_guides", "registry_guides", "insurance_guides"],
            "domain": ["lease_contract", "registry", "insurance", "required_check"],
            "source_type": ["checklist", "public_guide", "insurance"],
            "include_graph_context": True,
        },
        top_k=top_k,
    )


def search_legal_basis_rag(query: str, top_k: int = 5) -> ContextPack:
    return adaptive_rag(
        "legal_basis",
        query,
        filters={
            "task_type": "legal_basis",
            "tables": ["law_documents", "case_documents", "public_guides", "procedure_guides"],
            "domain": ["lease_contract", "tenant_protection", "procedure"],
            "source_type": ["law", "case", "dispute_case", "public_guide"],
            "include_graph_context": True,
        },
        top_k=top_k,
    )


def check_owner_landlord_match(fields: dict[str, Any], registry_fields: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    landlord = fields.get("landlord")
    registry_owner = (registry_fields or {}).get("owner_name")
    if not registry_fields:
        return [{"status": "MISSING", "check": "REGISTRY_OWNER", "message": "등기부등본이 없어 소유자와 임대인 일치 여부를 확인할 수 없습니다."}]
    if landlord and registry_owner and str(landlord) == str(registry_owner):
        return [{"status": "PASS", "check": "REGISTRY_OWNER", "message": "임대인과 등기부상 소유자가 일치합니다."}]
    return [{"status": "FAIL", "check": "REGISTRY_OWNER", "message": "임대인과 등기부상 소유자 불일치 가능성이 있습니다."}]


def check_proxy_contract(fields: dict[str, Any]) -> list[dict[str, Any]]:
    text = "\n".join(str(value) for value in fields.values() if value is not None)
    if any(token in text for token in ["대리인", "위임장", "인감"]):
        return [{"status": "REVIEW", "check": "PROXY_AUTHORITY", "message": "대리 계약 정황이 있어 위임장과 인감증명서 확인이 필요합니다."}]
    return [{"status": "MISSING", "check": "PROXY_AUTHORITY", "message": "대리인 계약 여부는 계약서만으로 확정하기 어렵습니다."}]


def classify_ownership_risk(
    fields: dict[str, Any],
    owner_checks: list[dict[str, Any]],
    proxy_checks: list[dict[str, Any]],
) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    for check in owner_checks + proxy_checks:
        if check["status"] == "FAIL":
            findings.append(
                RiskFinding(
                    code="OWNER_MISMATCH",
                    title="임대인과 소유자 불일치 위험",
                    severity="HIGH",
                    score_delta=20,
                    description=check["message"],
                    required_action="등기부상 소유자, 신분증, 위임장, 인감증명서를 대조하세요.",
                    source="ownership_risk_agent:classify_ownership_risk_tool",
                )
            )
        elif check["status"] in {"MISSING", "REVIEW"}:
            findings.append(
                RiskFinding(
                    code=f"REQUIRED_{check['check']}",
                    title=check["message"],
                    severity="MEDIUM",
                    score_delta=10,
                    description="PDF 계약서만으로는 권리관계와 계약 권한을 확정할 수 없습니다.",
                    required_action="계약 전 등기부등본, 신분증, 위임장/인감증명서 등 원본 확인 자료를 제출받으세요.",
                    source="ownership_risk_agent:classify_ownership_risk_tool",
                )
            )
    special_terms = "\n".join(str(term) for term in fields.get("special_terms") or [])
    if "신탁" in special_terms or "신탁" in str(fields.get("address") or ""):
        findings.append(
            RiskFinding(
                code="TRUST_REGISTRATION_AUTHORITY",
                title="신탁등기 계약 권한 확인 필요",
                severity="HIGH",
                score_delta=20,
                description="신탁 부동산은 위탁자나 임대인 명의만으로 계약 권한이 충분하지 않을 수 있습니다.",
                required_action="신탁원부와 수탁자 동의 또는 임대 권한을 확인하세요.",
                source="ownership_risk_agent:classify_ownership_risk_tool",
            )
        )
    return findings


@tool
def search_special_clause_rag_tool(query: str, top_k: int = 5) -> ContextPack:
    """Search RAG evidence dedicated to special-clause risk analysis."""
    return search_special_clause_rag(query, top_k)


@tool
def compare_standard_contract_tool(special_terms: list[str]) -> list[dict[str, Any]]:
    """Compare special terms against standard lease-contract expectations."""
    return compare_standard_contract(special_terms)


@tool
def classify_clause_risk_tool(special_terms: list[str], comparisons: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Classify special-clause risks and return serializable findings."""
    return [asdict(finding) for finding in classify_clause_risk(special_terms, comparisons)]


@tool
def search_registry_rag_tool(query: str, top_k: int = 5) -> ContextPack:
    """Search RAG evidence dedicated to ownership/registry risk analysis."""
    return search_registry_rag(query, top_k)


@tool
def check_owner_landlord_match_tool(fields: dict[str, Any], registry_fields: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Check owner-landlord consistency when registry fields are available."""
    return check_owner_landlord_match(fields, registry_fields)


@tool
def check_proxy_contract_tool(fields: dict[str, Any]) -> list[dict[str, Any]]:
    """Check whether proxy-contract evidence is required."""
    return check_proxy_contract(fields)


@tool
def classify_ownership_risk_tool(
    fields: dict[str, Any],
    owner_checks: list[dict[str, Any]],
    proxy_checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Classify ownership and contract-authority risk findings."""
    return [asdict(finding) for finding in classify_ownership_risk(fields, owner_checks, proxy_checks)]


@tool
def search_market_rag_tool(query: str, top_k: int = 5) -> ContextPack:
    """Search RAG evidence dedicated to market/jeonse-ratio risk analysis."""
    return search_market_rag(query, top_k)


@tool
def search_insurance_rag_tool(query: str, top_k: int = 5) -> ContextPack:
    """Search RAG evidence dedicated to deposit-insurance risk analysis."""
    return search_insurance_rag(query, top_k)


@tool
def search_required_check_rag_tool(query: str, top_k: int = 5) -> ContextPack:
    """Search RAG evidence dedicated to required document/checklist analysis."""
    return search_required_check_rag(query, top_k)


@tool
def search_legal_basis_rag_tool(query: str, top_k: int = 5) -> ContextPack:
    """Search RAG evidence dedicated to legal basis packaging."""
    return search_legal_basis_rag(query, top_k)
