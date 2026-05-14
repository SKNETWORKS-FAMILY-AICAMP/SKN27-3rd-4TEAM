"""Safe lease contract assistant Streamlit entry point."""

import importlib
import sys
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
importlib.invalidate_caches()

from utils.components import emergency_widget
from utils.styles import GLOBAL_CSS
import views.chat as chat
import views.checklist as checklist
import views.dashboard as dashboard
import views.history as history
import views.home as home
import views.market as market
import views.playbook as playbook
import views.property as property
import views.simulator as simulator


st.set_page_config(
    page_title="안전계약 전세사기 진단",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


VIEWS = {
    "home": {"label": "홈", "icon": "🏠", "badge": None, "render": home.render},
    "dashboard": {"label": "홈", "icon": "🏠", "badge": None, "render": dashboard.render},
    "chat": {"label": "AI 안심 상담", "icon": "💬", "badge": None, "render": chat.render},
    "cases": {"label": "유사 사례 및 판례 찾기", "icon": "⚖️", "badge": None, "render": playbook.render_cases},
    "checklist": {"label": "안전 체크리스트", "icon": "✅", "badge": None, "render": checklist.render},
    "history": {"label": "내 진단 기록", "icon": "📋", "badge": None, "render": history.render},
    "playbook": {"label": "피해 대응 안내", "icon": "🛡️", "badge": None, "render": playbook.render},
    "market": {"label": "지역 시세", "icon": "📍", "badge": None, "render": market.render},
    "property": {"label": "최근 확인 매물", "icon": "🏠", "badge": None, "render": property.render},
}

if "current_view" not in st.session_state:
    st.session_state.current_view = "home"

query_view = st.query_params.get("view")
if query_view in VIEWS:
    st.session_state.current_view = query_view


if st.session_state.current_view != "home":
    with st.sidebar:
        st.markdown(
            """
            <a class="side-brand-link" href="?view=home" target="_self" aria-label="홈으로 돌아가기">
              <div class="side-brand">
                <div style="display:flex;align-items:center;gap:10px">
                  <div class="side-logo">🏠</div>
                  <div>
                    <div class="side-title">나만의 전세 계약</div>
                    <div class="side-sub">전세사기 진단 서비스</div>
                  </div>
                </div>
              </div>
            </a>
            """,
            unsafe_allow_html=True,
        )

        for key, view in VIEWS.items():
            if key in ("property", "home"):
                # property: 사이드바에 별도 카드로 노출. home: 로딩 페이지(타이틀 클릭/초기 진입 전용)
                continue
            is_active = st.session_state.current_view == key
            if st.button(
                f'{view["icon"]}  {view["label"]}' + (f"  ({view['badge']})" if view["badge"] else ""),
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
              <div class="ttl">종로구 명륜2가 세빛빌라 302호</div>
              <div class="sub">전세 2.5억 · 42㎡ · 2018년식</div>
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
                        border-top:1px solid rgba(255,255,255,.12)">
              v0.5 · 종로구 전세사기 진단
            </div>
            """,
            unsafe_allow_html=True,
        )


view = VIEWS[st.session_state.current_view]
view["render"]()
