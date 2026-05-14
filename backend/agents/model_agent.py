"""
model_agent — 가격 위험도 분석 에이전트

입력: ContractData (contract_extractor 결과)
처리: 2027 예측 데이터와 비교 → 전세가율/위험도 판정
출력:
  - user_info: 수치 데이터 구조화 저장 (챗봇 참조용)
  - diagnosis: LLM이 생성한 진단 결과 문장
"""

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from backend.config import get_llm
from backend.agents.contract_extractor import ContractData
from backend.data_loader import lookup_prediction, area_bucket


# ── 데이터 모델 ──────────────────────────────────────────

class UserInfo(BaseModel):
    """사용자 계약 정보 + 예측 수치 (구조화 저장용)"""
    address: str
    dong_name: str
    deposit: int
    area_m2: float | None = None
    contract_period: str | None = None
    area_bucket: str | None = None
    predicted_deposit_2027: int | None = None
    predicted_sale_2027: int | None = None
    jeonse_ratio: float | None = None
    deposit_vs_avg: float | None = None
    cagr_jeonse: float | None = None
    cagr_sale: float | None = None
    risk_level: str = "미상"
    risk_score: int = 0


class ModelAgentResult(BaseModel):
    """model_agent 최종 반환"""
    success: bool
    user_info: UserInfo
    diagnosis: str = ""


# ── 동 이름 추출 ─────────────────────────────────────────

def extract_dong_name(address: str) -> str:
    """주소에서 동 이름 추출 (종로구 XX동)"""
    parts = address.replace("서울특별시", "").replace("서울시", "").replace("서울", "").strip()
    tokens = parts.split()
    for token in tokens:
        if token.endswith("동") or token.endswith("가"):
            dong = token
            # "명륜2가" → "명륜2가" 그대로
            return dong
    # 못 찾으면 마지막 토큰
    return tokens[-1] if tokens else address


# ── 위험도 점수 계산 ─────────────────────────────────────

def calc_risk_score(jeonse_ratio: float | None, deposit_vs_avg: float | None) -> int:
    """0~100 위험 점수 (높을수록 위험)"""
    score = 50  # 기본

    if jeonse_ratio is not None:
        if jeonse_ratio >= 90:
            score += 30
        elif jeonse_ratio >= 80:
            score += 20
        elif jeonse_ratio >= 70:
            score += 10
        else:
            score -= 10

    if deposit_vs_avg is not None:
        if deposit_vs_avg >= 120:
            score += 20
        elif deposit_vs_avg >= 110:
            score += 10
        elif deposit_vs_avg <= 90:
            score -= 10

    return max(0, min(100, score))


# ── LLM 진단 문장 생성 ──────────────────────────────────

DIAGNOSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 전세계약 위험 진단 전문가입니다.
아래 분석 데이터를 바탕으로 사용자에게 전달할 진단 결과를 작성하세요.

작성 규칙:
- 핵심 위험 요인을 먼저 명확히 짚어주세요
- 구체적인 숫자를 근거로 제시하세요
- 사용자가 취해야 할 행동을 권고하세요
- 존댓말로, 이해하기 쉽게 작성하세요
- 3~5문장으로 간결하게 작성하세요"""),
    ("human", """분석 대상: {address}
전세금: {deposit:,}만원
전용면적: {area_m2}㎡
면적구간: {area_bucket}

예측 데이터 (2027년):
- 해당 지역 평균 전세금: {predicted_deposit_2027:,}만원
- 해당 지역 예측 매매가: {predicted_sale_2027}만원
- 전세가율: {jeonse_ratio}%
- 내 전세금 vs 지역 평균: {deposit_vs_avg}%
- 전세 연평균 상승률: {cagr_jeonse}%

위험 등급: {risk_level}
위험 점수: {risk_score}/100""")
])


# ── 핵심 로직 ────────────────────────────────────────────

def analyze_price_risk(contract: ContractData) -> ModelAgentResult:
    """계약 정보로 가격 위험도 분석"""

    dong = extract_dong_name(contract.address)
    bucket = area_bucket(contract.area_m2) if contract.area_m2 else None

    # 예측 데이터 조회
    pred = lookup_prediction(dong, contract.area_m2)

    # user_info 구성
    user_info = UserInfo(
        address=contract.address,
        dong_name=dong,
        deposit=contract.deposit,
        area_m2=contract.area_m2,
        contract_period=contract.contract_period,
        area_bucket=bucket,
    )

    if pred is None:
        user_info.risk_level = "미상"
        user_info.risk_score = 0
        return ModelAgentResult(
            success=False,
            user_info=user_info,
            diagnosis=f"'{dong}' 지역의 거래 데이터가 부족하여 가격 위험도를 분석할 수 없습니다. 주소를 다시 확인해 주세요."
        )

    # 수치 채우기
    user_info.predicted_deposit_2027 = pred["predicted_deposit_2027"]
    user_info.predicted_sale_2027 = pred.get("predicted_sale_2027")
    user_info.jeonse_ratio = pred.get("jeonse_ratio_2027")
    user_info.cagr_jeonse = pred.get("cagr_jeonse")
    user_info.cagr_sale = pred.get("cagr_sale")
    user_info.area_bucket = pred.get("area_bucket", bucket)

    # 내 전세금 vs 지역 평균 비율
    if user_info.predicted_deposit_2027 and user_info.predicted_deposit_2027 > 0:
        user_info.deposit_vs_avg = round(
            contract.deposit / user_info.predicted_deposit_2027 * 100, 1
        )

    # 전세가율 재계산 (내 전세금 기준)
    if user_info.predicted_sale_2027 and user_info.predicted_sale_2027 > 0:
        user_info.jeonse_ratio = round(
            contract.deposit / user_info.predicted_sale_2027 * 100, 1
        )

    # 위험도 판정
    user_info.risk_score = calc_risk_score(user_info.jeonse_ratio, user_info.deposit_vs_avg)

    if user_info.risk_score >= 70:
        user_info.risk_level = "위험"
    elif user_info.risk_score >= 50:
        user_info.risk_level = "주의"
    else:
        user_info.risk_level = "안전"

    # LLM 진단 문장 생성
    llm = get_llm(temperature=0.3)
    chain = DIAGNOSIS_PROMPT | llm

    response = chain.invoke({
        "address": contract.address,
        "deposit": contract.deposit,
        "area_m2": contract.area_m2 or "미상",
        "area_bucket": user_info.area_bucket or "미상",
        "predicted_deposit_2027": user_info.predicted_deposit_2027 or 0,
        "predicted_sale_2027": user_info.predicted_sale_2027 or "데이터 없음",
        "jeonse_ratio": user_info.jeonse_ratio or "산출 불가",
        "deposit_vs_avg": user_info.deposit_vs_avg or "산출 불가",
        "cagr_jeonse": user_info.cagr_jeonse or "산출 불가",
        "risk_level": user_info.risk_level,
        "risk_score": user_info.risk_score,
    })

    diagnosis = response.content.strip()

    return ModelAgentResult(
        success=True,
        user_info=user_info,
        diagnosis=diagnosis,
    )
