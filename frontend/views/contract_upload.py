"""계약서 업로드와 텍스트 추출을 확인하는 화면."""

from __future__ import annotations

import requests
import streamlit as st

from utils.api import BACKEND_BASE_URL, upload_contract_file


FIELD_LABELS = {
    "address": "주소",
    "deposit_amount": "보증금(만원)",
    "monthly_rent": "월세(만원)",
    "contract_start": "계약 시작일",
    "contract_end": "계약 종료일",
    "special_terms": "특약사항",
}


def _render_fields(parsed_fields: dict) -> None:
    """추출된 핵심 필드를 사용자에게 읽기 쉬운 카드 형태로 보여준다."""
    st.markdown("### 추출된 핵심 정보")
    columns = st.columns(2)
    for index, (key, label) in enumerate(FIELD_LABELS.items()):
        value = parsed_fields.get(key) or "추출 필요"
        with columns[index % 2]:
            st.markdown(f"**{label}**")
            st.write(value)


def render() -> None:
    """업로드 파일을 백엔드로 보내고 텍스트 추출 결과를 표시한다."""
    st.markdown("# 계약서 업로드")
    st.caption("PDF, DOCX, TXT 계약서를 올리면 백엔드에서 텍스트와 기본 계약 정보를 먼저 추출합니다.")

    st.info(f"현재 연결 대상 백엔드: `{BACKEND_BASE_URL}`")

    uploaded_file = st.file_uploader(
        "계약서 파일 선택",
        type=["pdf", "docx", "txt"],
        help="첫 단계에서는 파일 저장 없이 텍스트 추출 결과만 확인합니다.",
    )

    if not uploaded_file:
        st.markdown(
            """
            #### 다음 단계
            - 여기서 추출된 텍스트를 RAG 진단 입력으로 넘깁니다.
            - 추출된 주소/보증금/월세는 시세 비교와 딥러닝 위험 예측 입력으로 씁니다.
            - 최종적으로 멀티에이전트가 전체 결과를 합쳐 리포트를 생성합니다.
            """
        )
        return

    if st.button("텍스트 추출하기", type="primary", use_container_width=True):
        try:
            with st.spinner("계약서 텍스트를 추출하는 중입니다..."):
                result = upload_contract_file(
                    filename=uploaded_file.name,
                    content=uploaded_file.getvalue(),
                    content_type=uploaded_file.type,
                )
            st.session_state["uploaded_contract"] = result
            st.success("계약서 텍스트 추출이 완료되었습니다.")
        except requests.exceptions.ConnectionError:
            st.error("백엔드 서버에 연결할 수 없습니다. 먼저 FastAPI 서버를 실행해주세요.")
            st.code("cd backend\n..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --reload", language="powershell")
            return
        except requests.exceptions.HTTPError as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            st.error(f"업로드 API 오류: {detail}")
            return
        except Exception as exc:
            st.error(f"예상하지 못한 오류가 발생했습니다: {exc}")
            return

    result = st.session_state.get("uploaded_contract")
    if not result:
        return

    st.markdown("### 업로드 결과")
    st.write(
        {
            "contract_id": result.get("contract_id"),
            "filename": result.get("filename"),
            "text_length": result.get("text_length"),
        }
    )

    _render_fields(result.get("parsed_fields", {}))

    st.markdown("### 추출 텍스트 미리보기")
    st.text_area(
        "extracted_text",
        value=result.get("extracted_text", ""),
        height=320,
        label_visibility="collapsed",
    )
