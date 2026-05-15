import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from backend.agents.contract_extractor import ContractData
from backend.agents.model_agent import analyze_price_risk

# 테스트: 명륜2가 전세 2.5억
contract = ContractData(
    address="서울 종로구 명륜2가 35-12",
    deposit=25000,
    area_m2=42.0,
    contract_period="2025.03~2027.03",
)

print("=== model_agent 테스트 ===")
print(f"입력: {contract.address} / 전세금 {contract.deposit:,}만원 / {contract.area_m2}㎡\n")

result = analyze_price_risk(contract)

print(f"성공: {result.success}")
print(f"위험등급: {result.user_info.risk_level}")
print(f"위험점수: {result.user_info.risk_score}/100")
print(f"전세가율: {result.user_info.jeonse_ratio}%")
print(f"내 전세금 vs 평균: {result.user_info.deposit_vs_avg}%")
print(f"2027 예측 전세금: {result.user_info.predicted_deposit_2027:,}만원")
print(f"2027 예측 매매가: {result.user_info.predicted_sale_2027:,}만원" if result.user_info.predicted_sale_2027 else "매매가: 데이터 없음")
print(f"\n--- 진단 결과 ---")
print(result.diagnosis)
