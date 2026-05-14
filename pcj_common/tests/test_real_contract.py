"""
가상계약서.docx 실계약서 검사 테스트

검사자 관점에서:
  1. 파일 파싱이 올바르게 되는지 (파싱 검사)
  2. LLM이 7개 필드를 정확히 추출하는지 (추출 정확도 검사)
  3. 에이전트 전체 흐름이 success 를 반환하는지 (흐름 검사)

실행:
  # mock 테스트 (LLM 없이)
  pytest pcj_common/tests/test_real_contract.py -v -m "not live"

  # 실제 LLM 테스트
  pytest pcj_common/tests/test_real_contract.py -v -m live
"""
from __future__ import annotations

import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from pcj_common.tools.contract_tools import parse_contract_document, check_required_fields

CONTRACT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "docs", "가상계약서.docx")
)

# ─────────────────────────────────────────────
# 검사자가 계약서를 직접 읽어 확인한 정답값
# ─────────────────────────────────────────────
EXPECTED = {
    "landlord":     "오성호",
    "tenant":       "최유진",
    "address":      "서울특별시 종로구 평창동 329-2",   # 핵심 키워드
    "area":         "84.84",
    "housing_type": "다세대주택",
    "deposit":      400_000_000,
    "period_start": "2025",
    "period_end":   "2027",
}


# ===========================================================
# 1단계: 파싱 검사 — LLM 없이 파일 자체가 올바르게 읽히는지
# ===========================================================

class TestContractFileParsing:
    """parse_contract_document 도구가 계약서 원문을 올바르게 추출하는지 검사"""

    def setup_method(self):
        self.text = parse_contract_document.invoke({"file_path": CONTRACT_PATH})

    def test_file_exists(self):
        assert os.path.exists(CONTRACT_PATH), f"계약서 파일이 없습니다: {CONTRACT_PATH}"

    def test_parsed_text_is_not_empty(self):
        assert len(self.text.strip()) > 100, "파싱 결과가 너무 짧음 — 파싱 실패 의심"

    def test_no_error_prefix(self):
        assert not self.text.startswith("[오류]"), f"파싱 오류 발생: {self.text}"

    def test_landlord_name_present(self):
        """임대인 이름이 원문에 존재하는지"""
        assert EXPECTED["landlord"] in self.text, \
            f"임대인 '{EXPECTED['landlord']}' 가 파싱 결과에 없음"

    def test_tenant_name_present(self):
        """임차인 이름이 원문에 존재하는지"""
        assert EXPECTED["tenant"] in self.text, \
            f"임차인 '{EXPECTED['tenant']}' 가 파싱 결과에 없음"

    def test_address_keyword_present(self):
        """주소 핵심 키워드가 원문에 존재하는지"""
        assert "평창동" in self.text, "주소 키워드 '평창동' 이 파싱 결과에 없음"

    def test_area_present(self):
        """면적 정보가 원문에 존재하는지"""
        assert "84.84" in self.text, "면적 '84.84' 가 파싱 결과에 없음"

    def test_housing_type_present(self):
        """주택 유형이 원문에 존재하는지"""
        assert "다세대주택" in self.text, "주택 유형 '다세대주택' 이 파싱 결과에 없음"

    def test_deposit_keyword_present(self):
        """보증금 금액 정보가 원문에 존재하는지"""
        assert "사억" in self.text or "400,000,000" in self.text, \
            "보증금 '사억 / 400,000,000' 이 파싱 결과에 없음"

    def test_contract_period_present(self):
        """계약 기간이 원문에 존재하는지"""
        assert "2025" in self.text and "2027" in self.text, \
            "계약 기간 연도 정보가 파싱 결과에 없음"


# ===========================================================
# 2단계: 추출 정확도 검사 — check_required_fields 도구 직접 검사
# ===========================================================

class TestFieldExtractionAccuracy:
    """
    검사자가 직접 정답 JSON 을 구성하고
    check_required_fields 도구가 올바르게 판정하는지 검사
    """

    def _make_json(self, **overrides) -> str:
        base = {
            "landlord":     EXPECTED["landlord"],
            "tenant":       EXPECTED["tenant"],
            "address":      "서울특별시 종로구 평창동 329-2 럭키평창빌라 제101호",
            "area":         "84.84",
            "housing_type": "다세대주택",
            "deposit":      EXPECTED["deposit"],
            "period":       "2025-02-25 ~ 2027-02-24",
        }
        base.update(overrides)
        return json.dumps(base, ensure_ascii=False)

    def test_correct_extraction_returns_success(self):
        """7개 필드 모두 정상 추출 시 success 반환"""
        result = json.loads(check_required_fields.invoke(
            {"extracted_json": self._make_json()}
        ))
        assert result["status"] == "success", \
            f"정상 계약서인데 success 가 아님: {result}"

    def test_correct_landlord_survives_validation(self):
        """임대인 '오성호' 가 검증 통과하는지"""
        result = json.loads(check_required_fields.invoke(
            {"extracted_json": self._make_json()}
        ))
        assert result["data"]["landlord"] == EXPECTED["landlord"]

    def test_correct_tenant_survives_validation(self):
        """임차인 '최유진' 이 검증 통과하는지"""
        result = json.loads(check_required_fields.invoke(
            {"extracted_json": self._make_json()}
        ))
        assert result["data"]["tenant"] == EXPECTED["tenant"]

    def test_correct_deposit_survives_validation(self):
        """보증금 400,000,000 이 검증 통과하는지"""
        result = json.loads(check_required_fields.invoke(
            {"extracted_json": self._make_json()}
        ))
        assert result["data"]["deposit"] == EXPECTED["deposit"]

    def test_missing_landlord_detected(self):
        """임대인 누락 시 missing_fields 에 포함되는지"""
        result = json.loads(check_required_fields.invoke(
            {"extracted_json": self._make_json(landlord=None)}
        ))
        assert result["status"] == "missing_data"
        assert "임대인" in result["missing_fields"]

    def test_missing_deposit_detected(self):
        """보증금 누락 시 missing_fields 에 포함되는지"""
        result = json.loads(check_required_fields.invoke(
            {"extracted_json": self._make_json(deposit=None)}
        ))
        assert result["status"] == "missing_data"
        assert "계약 금액" in result["missing_fields"]

    def test_missing_period_detected(self):
        """계약 기간 누락 시 missing_fields 에 포함되는지"""
        result = json.loads(check_required_fields.invoke(
            {"extracted_json": self._make_json(period=None)}
        ))
        assert result["status"] == "missing_data"
        assert "계약 기간" in result["missing_fields"]


# ===========================================================
# 3단계: 에이전트 흐름 검사 — mock LLM 으로 전체 흐름 검사
# ===========================================================

class TestAgentFlowWithRealFile:
    """
    실제 파일을 읽되 LLM 응답은 mock 으로 대체해
    에이전트 흐름 전체를 검사
    """

    def _mock_agent(self, response_json: dict):
        mock_msg = MagicMock()
        mock_msg.content = json.dumps(response_json, ensure_ascii=False)
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": [mock_msg]}
        return mock_agent

    def test_agent_returns_success_for_valid_contract(self):
        """에이전트가 정상 계약서에 대해 success JSON 을 반환하는지"""
        expected_response = {
            "status": "success",
            "data": {
                "landlord": "오성호",
                "tenant": "최유진",
                "address": "서울특별시 종로구 평창동 329-2 럭키평창빌라 제101호",
                "area": "84.84",
                "housing_type": "다세대주택",
                "deposit": 400_000_000,
                "period": "2025-02-25 ~ 2027-02-24",
            },
            "message": "계약서 데이터 추출이 완료되었습니다.",
        }
        with patch(
            "pcj_common.agents.pdf_review_agent.create_pdf_review_agent",
            return_value=self._mock_agent(expected_response),
        ):
            from pcj_common.agents.pdf_review_agent import run_pdf_review_agent
            result = json.loads(run_pdf_review_agent(CONTRACT_PATH))

        assert result["status"] == "success"
        assert result["data"]["landlord"] == "오성호"
        assert result["data"]["deposit"] == 400_000_000

    def test_agent_invoke_called_with_contract_path(self):
        """에이전트가 계약서 파일 경로를 포함한 메시지로 호출되는지"""
        mock_agent = self._mock_agent({"status": "success", "data": {}, "message": ""})
        with patch(
            "pcj_common.agents.pdf_review_agent.create_pdf_review_agent",
            return_value=mock_agent,
        ):
            from pcj_common.agents.pdf_review_agent import run_pdf_review_agent
            run_pdf_review_agent(CONTRACT_PATH)

        call_args = mock_agent.invoke.call_args
        messages = call_args[0][0]["messages"]
        assert any(CONTRACT_PATH in str(m.content) for m in messages), \
            "에이전트 호출 메시지에 계약서 경로가 없음"


# ===========================================================
# 4단계: 실제 LLM 통합 검사 (-m live 로 실행)
# ===========================================================

@pytest.mark.live
class TestLiveAgentWithRealContract:
    """
    실제 LLM + 실제 계약서 파일로 end-to-end 검사
    실행: pytest pcj_common/tests/test_real_contract.py -v -m live
    """

    def setup_method(self):
        from pcj_common.agents.pdf_review_agent import run_pdf_review_agent
        raw = run_pdf_review_agent(CONTRACT_PATH)
        print(f"\n[에이전트 원본 응답]\n{raw}\n")
        self.result = json.loads(raw)

    def test_live_status_is_success(self):
        """실제 계약서 → 모든 항목 있음 → success 여야 함"""
        assert self.result["status"] == "success", \
            f"success 가 아님. missing_fields: {self.result.get('missing_fields')}"

    def test_live_landlord_extracted_correctly(self):
        """임대인 '오성호' 정확히 추출됐는지"""
        assert self.result["data"]["landlord"] == EXPECTED["landlord"], \
            f"임대인 오추출: {self.result['data'].get('landlord')}"

    def test_live_tenant_extracted_correctly(self):
        """임차인 '최유진' 정확히 추출됐는지"""
        assert self.result["data"]["tenant"] == EXPECTED["tenant"], \
            f"임차인 오추출: {self.result['data'].get('tenant')}"

    def test_live_address_contains_key_info(self):
        """주소에 '평창동' 또는 '종로구' 포함됐는지"""
        address = self.result["data"].get("address", "")
        assert "평창동" in address or "종로구" in address, \
            f"주소 오추출: {address}"

    def test_live_housing_type_is_correct(self):
        """주택 유형이 '다세대주택' 으로 추출됐는지"""
        housing_type = self.result["data"].get("housing_type", "")
        assert "다세대" in housing_type, \
            f"주택 유형 오추출: {housing_type}"

    def test_live_area_is_correct(self):
        """면적에 '84.84' 가 포함됐는지"""
        area = str(self.result["data"].get("area", ""))
        assert "84.84" in area or "84" in area, \
            f"면적 오추출: {area}"

    def test_live_deposit_is_400_million(self):
        """보증금이 400,000,000원으로 추출됐는지"""
        deposit = self.result["data"].get("deposit")
        assert deposit == EXPECTED["deposit"], \
            f"보증금 오추출: {deposit} (정답: {EXPECTED['deposit']})"

    def test_live_period_contains_2025_and_2027(self):
        """계약 기간에 2025, 2027이 포함됐는지"""
        period = str(self.result["data"].get("period", ""))
        assert "2025" in period and "2027" in period, \
            f"계약 기간 오추출: {period}"

    def test_live_all_7_fields_present(self):
        """7개 필드가 모두 None 이 아닌지"""
        data = self.result["data"]
        required = ["landlord", "tenant", "address", "area",
                    "housing_type", "deposit", "period"]
        missing = [f for f in required if not data.get(f)]
        assert not missing, f"누락된 필드: {missing}"
