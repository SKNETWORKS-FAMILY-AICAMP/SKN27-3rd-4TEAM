"""Document diagnosis agents.

This module follows the document side of the sequence diagram:

supervisor -> contract_extract_agent -> model_agent -> special_terms_agent
-> report_writer -> diagnosis_json_writer
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rag_server.models.schemas import ContractInfo, DiagnosisResponse, RiskFactor

if TYPE_CHECKING:
    from rag_server.config import Settings
    from rag_server.services.market_price_service import MarketPriceService


@dataclass
class SupervisorDecision:
    can_diagnose: bool
    missing_fields: list[str]
    reason: str = ""


class ContractSupervisor:
    """Checks whether extracted contract data is enough to continue diagnosis."""

    REQUIRED_FIELDS = {
        "lessor_name": "임대사업자(임대인)",
        "lessee_name": "임차인",
        "address": "소재지",
        "deposit_amount": "보증금",
        "contract_start": "계약 시작일",
        "contract_end": "계약 종료일",
    }

    def inspect(self, contract_info: ContractInfo) -> SupervisorDecision:
        missing = []
        for field, label in self.REQUIRED_FIELDS.items():
            value = getattr(contract_info, field, None)
            if value in (None, "", 0):
                missing.append(label)
        if contract_info.address and not _looks_like_valid_address(contract_info.address):
            missing.append("소재지")
        return SupervisorDecision(
            can_diagnose=not missing,
            missing_fields=list(dict.fromkeys(missing)),
            reason=", ".join(missing),
        )


class ModelAgent:
    """Analyzes price, senior lien, and guarantee-insurance risks."""

    def __init__(self, market_service: "MarketPriceService | None" = None):
        self._market = market_service

    def analyze(self, contract_info: ContractInfo) -> list[RiskFactor]:
        text = contract_info.raw_text or ""
        risks: list[RiskFactor] = []

        deposit_manwon = contract_info.deposit_amount
        deposit = _contract_amount_to_won(deposit_manwon)
        senior_lien = _extract_money_krw(text, ["채권최고액", "선순위", "근저당", "설정금액"])
        guaranteed = _extract_money_krw(text, ["보증대상 금액", "보증대상금액", "보증보험"])
        ratio_risk = self._analyze_market_ratio(contract_info, deposit_manwon)
        if ratio_risk:
            risks.append(ratio_risk)
        elif deposit_manwon:
            risks.append(
                RiskFactor(
                    factor_id="MODEL-MARKET-DATA-MISSING",
                    category="가격위험",
                    description="전세금 대비 가격위험을 계산할 매매 실거래가 또는 계약서상 매매시세를 찾지 못했습니다.",
                    severity="MEDIUM",
                    legal_basis=None,
                    advice="예상 매매가와 전세가율이 비어 있으면 실거래가를 직접 확인해야 합니다. 매매가 확인 전에는 보증금 회수 위험 판단이 불완전합니다.",
                )
            )

        if senior_lien:
            risks.append(
                RiskFactor(
                    factor_id="MODEL-SENIOR-LIEN",
                    category="권리관계",
                    description=f"선순위 근저당권이 확인됩니다. 채권최고액은 약 {_format_won(senior_lien)}입니다.",
                    severity="HIGH",
                    legal_basis="민법 제356조, 주택임대차보호법 제8조",
                    advice="잔금 지급 전 말소 또는 감액 등기 완료 여부를 등기부로 재확인하고, 말소 전 입금은 피하세요.",
                )
            )

        if deposit and guaranteed and guaranteed < deposit:
            uncovered = deposit - guaranteed
            risks.append(
                RiskFactor(
                    factor_id="MODEL-GUARANTEE-PARTIAL",
                    category="보증보험",
                    description=f"보증보험이 보증금 전액을 보장하지 않습니다. 미보장 금액은 약 {_format_won(uncovered)}입니다.",
                    severity="HIGH",
                    legal_basis="HUG 전세보증금반환보증 심사 기준",
                    advice="보증보험 전액 가입 가능 여부를 확인하고, 일부 가입 조건이면 계약 조건을 재협상하세요.",
                )
            )

        if not ratio_risk and any(token in text for token in ["전세가율", "매매시세 대비", "시세 대비", "깡통전세"]):
            risks.append(
                RiskFactor(
                    factor_id="MODEL-MARKET-RATIO",
                    category="가격위험",
                    description="계약서에 전세가율 또는 매매시세 대비 보증금 위험 문구가 포함되어 있습니다.",
                    severity="HIGH",
                    legal_basis="주택임대차보호법 제3조의3",
                    advice="실거래가, 공시가격, 인근 전세가를 함께 확인해 보증금 회수 가능성을 재검토하세요.",
                )
            )

        return risks

    def _analyze_market_ratio(self, contract_info: ContractInfo, deposit_manwon: int | None) -> RiskFactor | None:
        if not deposit_manwon:
            return None

        ratio = None
        estimated_sale_price = None
        sample_count = None
        dong = _extract_dong(contract_info.address or "")

        if self._market and dong:
            try:
                result = self._market.calculate_jeonse_ratio(
                    deposit_amount=deposit_manwon,
                    dong_name=dong,
                    housing_type=None,
                    area_m2=contract_info.area_m2,
                )
            except Exception as exc:
                print(f"[ModelAgent] market ratio lookup failed: {exc}")
                result = None
            if result:
                ratio = float(result.jeonse_ratio)
                estimated_sale_price = int(result.estimated_sale_price)
                sample_count = int(result.sample_count)

        if estimated_sale_price is None:
            estimated_sale_price = _extract_sale_price_manwon(contract_info.raw_text or "")
            if estimated_sale_price:
                ratio = round(deposit_manwon / estimated_sale_price * 100, 1)

        if estimated_sale_price is None or ratio is None:
            return None

        contract_info.estimated_sale_price = estimated_sale_price
        contract_info.jeonse_ratio = ratio

        if ratio >= 80:
            severity = "HIGH"
            advice = "전세가율이 80%를 넘으면 경매 또는 가격 하락 시 보증금 회수 여력이 부족할 수 있습니다. 보증보험 가입 가능 여부와 선순위 권리를 반드시 확인하세요."
        elif ratio >= 70:
            severity = "MEDIUM"
            advice = "전세가율이 주의 구간입니다. 인근 실거래가와 보증보험 가능 여부를 추가 확인하세요."
        else:
            severity = "LOW"
            advice = "전세가율은 상대적으로 낮지만 등기부, 선순위 권리, 특약은 별도로 확인해야 합니다."

        sample_text = f", 실거래 표본 {sample_count}건" if sample_count else ""
        return RiskFactor(
            factor_id="MODEL-JEONSE-RATIO",
            category="가격위험",
            description=(
                f"전세금 {deposit_manwon:,}만원과 예상 매매가 {estimated_sale_price:,}만원 기준 "
                f"전세가율은 {ratio:.1f}%입니다{sample_text}."
            ),
            severity=severity,
            legal_basis="주택임대차보호법 제3조의3",
            advice=advice,
        )


class SpecialTermsAgent:
    """Analyzes special clauses only when special terms exist."""

    def analyze(self, contract_info: ContractInfo) -> list[RiskFactor]:
        special_terms = (contract_info.special_terms or "").strip()
        if not special_terms:
            return []

        risks: list[RiskFactor] = []
        text = f"{special_terms}\n{contract_info.raw_text or ''}"

        if any(token in text for token in ["위험을 인지", "이의를 제기하지 않는다", "책임을 부담"]):
            risks.append(
                RiskFactor(
                    factor_id="TERMS-RISK-WAIVER",
                    category="특약",
                    description="임차인이 위험을 인지했거나 이의를 제기하지 않는다는 취지의 특약이 확인됩니다.",
                    severity="HIGH",
                    legal_basis="민법 제103조, 약관의 규제에 관한 법률 제6조",
                    advice="보증금 회수 위험을 임차인에게 전가하는 문구는 삭제하거나 명확히 수정하세요.",
                )
            )

        if any(token in text for token in ["사업 운영자금", "사업자금", "운영자금"]):
            risks.append(
                RiskFactor(
                    factor_id="TERMS-OWNER-FUNDING",
                    category="특약",
                    description="임대인이 보증금을 사업 운영자금으로 사용할 수 있다는 특약이 있습니다.",
                    severity="HIGH",
                    legal_basis="민법 제618조, 주택임대차보호법 제3조",
                    advice="보증금 용도 제한, 반환 재원, 담보 제공 조건을 명시하지 않으면 계약을 보류하세요.",
                )
            )

        if any(token in text for token in ["법정 한도", "5%를 초과", "5% 초과", "월세 인상"]):
            risks.append(
                RiskFactor(
                    factor_id="TERMS-RENT-INCREASE",
                    category="특약",
                    description="차임 또는 월세를 법정 한도보다 높게 인상할 수 있다는 특약이 포함되어 있습니다.",
                    severity="MEDIUM",
                    legal_basis="주택임대차보호법 제7조",
                    advice="갱신 시 증액 한도와 산정 기준을 법정 범위 안으로 수정하세요.",
                )
            )

        if any(token in text for token in ["말소", "잔금일로부터", "30일 이내"]):
            risks.append(
                RiskFactor(
                    factor_id="TERMS-DELAYED-CANCEL",
                    category="권리관계",
                    description="선순위 권리 말소가 잔금 지급과 동시에 이뤄지지 않을 가능성이 있습니다.",
                    severity="HIGH",
                    legal_basis="주택임대차보호법 제3조, 민법 제356조",
                    advice="근저당 말소는 잔금 지급과 동시 이행으로 바꾸고, 등기 접수증 확인 후 지급하세요.",
                )
            )

        return risks


class ReportWriter:
    """Builds the final document-diagnosis report."""

    def build(
        self,
        session_id: str,
        contract_info: ContractInfo,
        supervisor: SupervisorDecision,
        model_risks: list[RiskFactor],
        terms_risks: list[RiskFactor],
    ) -> DiagnosisResponse:
        if not supervisor.can_diagnose:
            missing = ", ".join(supervisor.missing_fields)
            risks = [
                RiskFactor(
                    factor_id="SUPERVISOR-MISSING-BASIC",
                    category="기본정보 추출",
                    description=f"계약서 핵심 정보가 부족합니다: {missing}",
                    severity="MEDIUM",
                    legal_basis=None,
                    advice="원본 계약서를 선명하게 다시 업로드하거나 누락된 정보를 포함한 텍스트로 재진단하세요.",
                )
            ]
            return DiagnosisResponse(
                session_id=session_id,
                contract_info=contract_info,
                risk_score=0.0,
                risk_level="재업로드 필요",
                risk_factors=risks,
                summary=f"기본 정보({missing})가 없어 정확한 계약서 진단을 중단했습니다.",
                references=[],
                graph_context=[],
                agent_trace=[
                    "supervisor:document",
                    "contract_extract_agent",
                    "contract_supervisor:missing_basic_info",
                    "report_writer",
                    "diagnosis_json_writer",
                ],
            )

        risk_factors = _dedupe_risks(model_risks + terms_risks)
        risk_score, risk_level = self._score(risk_factors)

        return DiagnosisResponse(
            session_id=session_id,
            contract_info=contract_info,
            risk_score=risk_score,
            risk_level=risk_level,
            risk_factors=risk_factors,
            summary=self._summary(contract_info, risk_factors),
            references=[],
            graph_context=[],
            agent_trace=[
                "supervisor:document",
                "contract_extract_agent",
                "contract_supervisor:basic_info_ok",
                "model_agent",
                "special_terms_agent" if contract_info.special_terms else "special_terms_agent:skipped",
                "report_writer",
                "diagnosis_json_writer",
            ],
        )

    def _score(self, risk_factors: list[RiskFactor]) -> tuple[float, str]:
        weight = {"HIGH": 25.0, "MEDIUM": 10.0, "LOW": 3.0}
        score = min(sum(weight.get(rf.severity, 5.0) for rf in risk_factors), 100.0)
        if score >= 80:
            return round(score, 1), "위험"
        if score >= 50:
            return round(score, 1), "주의"
        return round(score, 1), "안전"

    def _summary(self, contract_info: ContractInfo, risk_factors: list[RiskFactor]) -> str:
        address = contract_info.address or "주소 미상"
        deposit = _format_contract_amount(contract_info.deposit_amount) if contract_info.deposit_amount else "보증금 미상"
        high_count = sum(1 for risk in risk_factors if risk.severity == "HIGH")
        med_count = sum(1 for risk in risk_factors if risk.severity == "MEDIUM")
        ratio_text = (
            f" 예상 매매가 {_format_contract_amount(contract_info.estimated_sale_price)} 기준 전세가율 {contract_info.jeonse_ratio:.1f}%입니다."
            if contract_info.estimated_sale_price and contract_info.jeonse_ratio is not None
            else ""
        )
        return f"{address} 계약서는 {deposit} 기준으로 고위험 {high_count}건, 주의 {med_count}건이 확인되었습니다.{ratio_text}"


async def run_contract_diagnosis_flow(
    session_id: str,
    contract_info: ContractInfo,
    settings: "Settings | None" = None,
) -> DiagnosisResponse:
    supervisor = ContractSupervisor().inspect(contract_info)
    market_service = None
    if settings:
        from rag_server.services.market_price_service import MarketPriceService

        market_service = MarketPriceService(settings)
    model_risks = ModelAgent(market_service).analyze(contract_info) if supervisor.can_diagnose else []
    terms_risks = SpecialTermsAgent().analyze(contract_info) if supervisor.can_diagnose else []
    return ReportWriter().build(
        session_id=session_id,
        contract_info=contract_info,
        supervisor=supervisor,
        model_risks=model_risks,
        terms_risks=terms_risks,
    )


def _dedupe_risks(risk_factors: list[RiskFactor]) -> list[RiskFactor]:
    seen: set[str] = set()
    deduped: list[RiskFactor] = []
    for risk in risk_factors:
        key = risk.factor_id or f"{risk.category}:{risk.description[:40]}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(risk)
    return deduped[:12]


def _extract_money_krw(text: str, anchors: list[str]) -> int | None:
    if not text:
        return None
    for anchor in anchors:
        idx = text.find(anchor)
        if idx < 0:
            continue
        value = _parse_money(text[idx : idx + 140])
        if value:
            return value
    return None


def _extract_dong(address: str) -> str | None:
    match = re.search(r"([가-힣]+(?:동|읍|면|리|가))\b", address)
    return match.group(1) if match else None


def _looks_like_valid_address(address: str) -> bool:
    if "[" in address or "]" in address:
        return False
    if not re.search(r"(서울특별시|경기도|인천광역시|부산광역시|대구광역시|광주광역시|대전광역시|울산광역시|세종특별자치시|제주특별자치도)", address):
        return False
    return bool(re.search(r"(동|읍|면|리|가)\s*[0-9]", address) or re.search(r"제?\s*\d+\s*호", address))


def _extract_sale_price_manwon(text: str) -> int | None:
    for anchor in ["예상 매매가", "매매시세", "매매 시세", "주택가격", "시세"]:
        idx = text.find(anchor)
        if idx < 0:
            continue
        amount = _parse_money(text[idx : idx + 160])
        if amount:
            return amount // 10_000 if amount >= 10_000 else amount
    return None


def _parse_money(text: str) -> int | None:
    match = re.search(r"([0-9,]+)\s*원", text)
    if match:
        return int(match.group(1).replace(",", ""))

    eok_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*억", text)
    man_match = re.search(r"([0-9,]+)\s*만", text)
    total = 0
    if eok_match:
        total += int(float(eok_match.group(1)) * 100_000_000)
    if man_match:
        total += int(man_match.group(1).replace(",", "")) * 10_000
    return total or None


def _contract_amount_to_won(value: int | None) -> int | None:
    if value is None:
        return None
    if value < 1_000_000:
        return value * 10_000
    return value


def _format_contract_amount(value: int | None) -> str:
    return _format_won(_contract_amount_to_won(value))


def _format_won(value: int | None) -> str:
    if value is None:
        return "-"
    if value >= 100_000_000:
        return f"{value / 100_000_000:g}억 원"
    if value >= 10_000:
        return f"{value // 10_000:,}만 원"
    return f"{value:,}원"
