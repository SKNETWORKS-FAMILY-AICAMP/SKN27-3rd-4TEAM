"""전세 사기 분석 — 나만의 전세 계약.

Streamlit 앱 메인 진입점.
실행: streamlit run app.py
"""

import importlib
import sys
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
importlib.invalidate_caches()

from utils.styles import GLOBAL_CSS
from utils.components import emergency_widget
import views.chat as chat
import views.checklist as checklist
import views.contract_upload as contract_upload
import views.history as history
import views.home as home
import views.market as market
import views.playbook as playbook
import views.property as property
import views.simulator as simulator


st.set_page_config(
    page_title="나만의 전세 계약",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


VIEWS = {
    "home": {"label": "메인페이지", "icon": "🏠", "badge": None, "render": home.render},
    "contract_upload": {"label": "계약서 업로드", "icon": "📄", "badge": None, "render": contract_upload.render},
    "chat": {"label": "챗봇", "icon": "🤖", "badge": "12", "render": chat.render},
    "cases": {"label": "나와 비슷한 사례", "icon": "📚", "badge": None, "render": playbook.render_cases},
    "checklist": {"label": "체크리스트", "icon": "📋", "badge": None, "render": checklist.render},
    "history": {"label": "진단 기록", "icon": "🗂️", "badge": "6", "render": history.render},
    "simulator": {"label": "시뮬레이터", "icon": "📊", "badge": None, "render": simulator.render},
    "playbook": {"label": "피해 대처 방법", "icon": "🛡️", "badge": None, "render": playbook.render},
    "market": {"label": "지역별 시세", "icon": "🗺️", "badge": None, "render": market.render},
    "property": {"label": "최근 확인 매물", "icon": "🏠", "badge": None, "render": property.render},
}

if "current_view" not in st.session_state:
    st.session_state.current_view = "home"

query_view = st.query_params.get("view")
if query_view in VIEWS:
    st.session_state.current_view = query_view


with st.sidebar:
    st.markdown(
        """
        <div class="side-brand">
          <div style="display:flex;align-items:center;gap:10px">
            <div class="side-logo">🏠</div>
            <div>
              <div class="side-title">나만의 전세 계약</div>
              <div class="side-sub">안전한 전세 계약 관리</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for key, v in VIEWS.items():
        if key == "property":
            continue
        is_active = st.session_state.current_view == key
        if st.button(
            f'{v["icon"]}  {v["label"]}' + (f"  ({v['badge']})" if v["badge"] else ""),
            key=f"nav_{key}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            st.session_state.current_view = key
            st.query_params.clear()
            st.rerun()

    st.markdown('<div style="height:24px"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:11px;font-weight:800;color:rgba(255,255,255,.58);'
        'letter-spacing:.08em;margin:8px 0 8px">최근 확인 매물</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <a class="prop-mini prop-mini-link" href="?view=property" target="_self" aria-label="최근 확인 매물 상세 보기">
          <div class="ttl">명륜2가 한빛빌라 302호</div>
          <div class="sub">전세 ₩2.5억 · 42㎡ · 2018년식</div>
          <div style="margin-top:8px;display:flex;gap:6px;align-items:center">
            <span style="width:10px;height:10px;border-radius:50%;background:var(--red);
                         box-shadow:0 0 0 3px var(--red-soft);display:inline-block"></span>
            <b style="color:var(--red);font-size:12px">위험 78점</b>
          </div>
        </a>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
    emergency_widget()

    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div style="font-size:11px;color:var(--gray-300);text-align:center;padding-top:8px;
                    border-top:1px solid var(--gray-100)">
          v0.1 · 데모 · 종로구 한정
        </div>
        """,
        unsafe_allow_html=True,
    )


view = VIEWS[st.session_state.current_view]
view["render"]()
