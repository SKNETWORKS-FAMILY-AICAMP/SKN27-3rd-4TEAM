"""
PDF 검토 에이전트 테스트 (create_agent 패턴)

실행:
  pytest pcj_common/tests/test_pdf_review_agent.py -v -m "not live"

실제 LLM 테스트:
  pytest pcj_common/tests/test_pdf_review_agent.py -v -m live
"""
from __future__ import annotations

import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from pcj_common.tools.contract_tools import (
    check_required_fields,
    parse_contract_document,
    REQUIRED_FIELDS,
)

TEST_DIR = os.path.dirname(__file__)
VALID_DOCX   = os.path.join(TEST_DIR, "valid_contract.docx")
MISSING_DOCX = os.path.join(TEST_DIR, "missing_deposit_period.docx")


# ---------------------------------------------------------------------------
# 1. parse_contract_document 도구 테스트
# ---------------------------------------------------------------------------

class TestParseContractDocument:

    def test_valid_docx_returns_text(self):
        result = parse_contract_document.invoke({"file_path": VALID_DOCX})
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_valid_docx_contains_landlord(self):
        result = parse_contract_document.invoke({"file_path": VALID_DOCX})
        assert "홍길동" in result

    def test_valid_docx_contains_address(self):
        result = parse_contract_document.invoke({"file_path": VALID_DOCX})
        assert "테헤란로" in result

    def test_missing_file_returns_error_message(self):
        result = parse_contract_document.invoke({"file_path": "없는파일.docx"})
        assert "[오류]" in result

    def test_unsupported_format_returns_error_message(self):
        result = parse_contract_document.invoke({"file_path": "계약서.txt"})
        assert "[오류]" in result
        assert "지원하지 않는" in result

    def test_missing_docx_still_parses(self):
        result = parse_contract_document.invoke({"file_path": MISSING_DOCX})
        assert "이영희" in result


# ---------------------------------------------------------------------------
# 2. check_required_fields 도구 테스트
# ---------------------------------------------------------------------------

class TestCheckRequiredFields:

    def _full_json(self) -> str:
        return json.dumps({
            "landlord": "홍길동",
            "tenant": "김철수",
            "address": "서울시 강남구 테헤란로 123",
            "area": "84.5",
            "housing_type": "아파트",
            "deposit": 300000000,
            "period": "2025-03-01 ~ 2027-03-01",
        }, ensure_ascii=False)

    def test_all_fields_present_returns_success(self):
        result = check_required_fields.invoke({"extracted_json": self._full_json()})
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["landlord"] == "홍길동"

    def test_missing_deposit_returns_missing_data(self):
        data = json.loads(self._full_json())
        data["deposit"] = None
        result = check_required_fields.invoke({"extracted_json": json.dumps(data)})
        parsed = json.loads(result)
        assert parsed["status"] == "missing_data"
        assert "계약 금액" in parsed["missing_fields"]

    def test_missing_period_returns_missing_data(self):
        data = json.loads(self._full_json())
        data["period"] = None
        result = check_required_fields.invoke({"extracted_json": json.dumps(data)})
        parsed = json.loads(result)
        assert parsed["status"] == "missing_data"
        assert "계약 기간" in parsed["missing_fields"]

    def test_multiple_missing_fields(self):
        data = {
            "landlord": None, "tenant": None,
            "address": "서울시", "area": "84.5",
            "housing_type": "아파트",
            "deposit": None, "period": None,
        }
        result = check_required_fields.invoke({"extracted_json": json.dumps(data)})
        parsed = json.loads(result)
        assert parsed["status"] == "missing_data"
        assert "임대인" in parsed["missing_fields"]
        assert "임차인" in parsed["missing_fields"]
        assert "계약 금액" in parsed["missing_fields"]

    def test_all_fields_missing_returns_all_korean_names(self):
        data = {k: None for k in REQUIRED_FIELDS.keys()}
        result = check_required_fields.invoke({"extracted_json": json.dumps(data)})
        parsed = json.loads(result)
        assert parsed["status"] == "missing_data"
        assert len(parsed["missing_fields"]) == len(REQUIRED_FIELDS)

    def test_invalid_json_returns_error(self):
        result = check_required_fields.invoke({"extracted_json": "이건JSON이아님"})
        parsed = json.loads(result)
        assert parsed["status"] == "missing_data"
        assert "JSON 파싱 실패" in parsed["message"]

    def test_success_message_included(self):
        result = check_required_fields.invoke({"extracted_json": self._full_json()})
        parsed = json.loads(result)
        assert "message" in parsed

    def test_missing_message_contains_field_names(self):
        data = json.loads(self._full_json())
        data["landlord"] = None
        result = check_required_fields.invoke({"extracted_json": json.dumps(data)})
        parsed = json.loads(result)
        assert "임대인" in parsed["message"]


# ---------------------------------------------------------------------------
# 3. 에이전트 통합 테스트 (LLM mock)
# ---------------------------------------------------------------------------

class TestPdfReviewAgentIntegration:
    """create_agent 패턴 전체 흐름 테스트."""

    def _mock_agent_response(self, response_content: str):
        """create_agent 가 반환하는 에이전트를 mock 으로 대체."""
        mock_msg = MagicMock()
        mock_msg.content = response_content

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": [mock_msg]}
        return mock_agent

    def test_success_result_contains_status_success(self):
        success_response = json.dumps({
            "status": "success",
            "data": {
                "landlord": "홍길동", "tenant": "김철수",
                "address": "서울시 강남구", "area": "84.5",
                "housing_type": "아파트", "deposit": 300000000,
                "period": "2025-03-01 ~ 2027-03-01",
            },
            "message": "계약서 데이터 추출이 완료되었습니다.",
        }, ensure_ascii=False)

        with patch(
            "pcj_common.agents.pdf_review_agent.create_pdf_review_agent",
            return_value=self._mock_agent_response(success_response),
        ):
            from pcj_common.agents.pdf_review_agent import run_pdf_review_agent
            result_str = run_pdf_review_agent(VALID_DOCX)
            result = json.loads(result_str)

        assert result["status"] == "success"
        assert result["data"]["landlord"] == "홍길동"

    def test_missing_data_result_contains_missing_fields(self):
        missing_response = json.dumps({
            "status": "missing_data",
            "missing_fields": ["계약 금액", "계약 기간"],
            "message": "계약서에 다음 항목이 누락되어 있습니다: 계약 금액, 계약 기간",
        }, ensure_ascii=False)

        with patch(
            "pcj_common.agents.pdf_review_agent.create_pdf_review_agent",
            return_value=self._mock_agent_response(missing_response),
        ):
            from pcj_common.agents.pdf_review_agent import run_pdf_review_agent
            result_str = run_pdf_review_agent(MISSING_DOCX)
            result = json.loads(result_str)

        assert result["status"] == "missing_data"
        assert "계약 금액" in result["missing_fields"]

    def test_agent_create_uses_correct_tools(self):
        """create_pdf_review_agent 가 올바른 도구 2개를 포함하는지 확인."""
        # reload 없이 patch 컨텍스트 안에서 직접 함수 호출
        import pcj_common.agents.pdf_review_agent as agent_module

        mock_agent = MagicMock()
        with patch.object(agent_module, "create_agent", return_value=mock_agent) as mock_create, \
             patch.object(agent_module, "build_chat_llm", return_value=MagicMock()):
            agent_module.create_pdf_review_agent()

        call_kwargs = mock_create.call_args
        tools_passed = call_kwargs.kwargs.get("tools") or call_kwargs.args[1]
        tool_names = [t.name for t in tools_passed]
        assert "parse_contract_document" in tool_names
        assert "check_required_fields" in tool_names


# ---------------------------------------------------------------------------
# 4. 실제 LLM 테스트 (-m live)
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestLiveWithRealLLM:
    """GROQ_API_KEY 가 필요한 실제 LLM 통합 테스트."""

    def test_live_valid_contract(self):
        from pcj_common.agents.pdf_review_agent import run_pdf_review_agent
        result_str = run_pdf_review_agent(VALID_DOCX)
        print(f"\n[LIVE] 결과: {result_str}")
        result = json.loads(result_str)
        assert result["status"] in ("success", "missing_data")

    def test_live_missing_contract(self):
        from pcj_common.agents.pdf_review_agent import run_pdf_review_agent
        result_str = run_pdf_review_agent(MISSING_DOCX)
        print(f"\n[LIVE] 결과: {result_str}")
        result = json.loads(result_str)
        assert result["status"] == "missing_data"
        assert len(result["missing_fields"]) > 0
