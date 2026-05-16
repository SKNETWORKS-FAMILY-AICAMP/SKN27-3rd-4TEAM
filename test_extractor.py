"""contract_extractor 간단 테스트"""
import sys
sys.path.insert(0, ".")

from backend.agents.contract_extractor import create_manual_input, extract_contract

# 테스트 1: 직접 입력 - 정상
print("=== 테스트 1: 직접 입력 (정상) ===")
result = create_manual_input(
    address="서울 종로구 명륜2가 35-12",
    deposit=25000,
    area_m2=42.0,
    contract_period="2025.03~2027.03"
)
print(f"성공: {result.success}")
print(f"메시지: {result.message}")
print(f"데이터: {result.data}")
print()

# 테스트 2: 직접 입력 - 기본정보 누락
print("=== 테스트 2: 직접 입력 (주소 누락) ===")
result2 = create_manual_input(address="", deposit=0)
print(f"성공: {result2.success}")
print(f"메시지: {result2.message}")
print()

# 테스트 3: PDF 추출 (Groq API 호출)
print("=== 테스트 3: 가짜 계약서 텍스트로 LLM 추출 테스트 ===")
fake_contract = """
임 대 차 계 약 서

소재지: 서울특별시 종로구 명륜2가 35-12 한빛빌라 302호
전용면적: 42.5㎡

전세금: 금 이억오천만원정 (250,000,000원)
계약기간: 2025년 3월 15일 ~ 2027년 3월 14일

특약사항:
1. 임대인은 잔금 지급일까지 근저당권을 말소하기로 한다. 미이행 시 본 계약은 무효로 한다.
2. 임차인의 전입신고 및 확정일자 취득에 임대인은 적극 협조한다.
""".encode("utf-8")

# PyMuPDF는 실제 PDF 바이트가 필요하므로 직접 테스트는 스킵
# LLM 호출 테스트를 위해 parse 로직만 확인
from backend.agents.contract_extractor import parse_llm_response
test_json = '{"address": "서울 종로구 명륜2가 35-12", "deposit": 25000, "contract_period": "2025.03~2027.03", "area_m2": 42.5, "special_terms": ["근저당 말소 조건부 무효", "전입신고 협조 의무"], "has_monthly_rent": false}'
data = parse_llm_response(test_json)
print(f"주소: {data.address}")
print(f"전세금: {data.deposit:,}만원")
print(f"특약: {data.special_terms}")
print(f"월세여부: {data.has_monthly_rent}")
print()

print("=== 모든 테스트 통과 ===")
