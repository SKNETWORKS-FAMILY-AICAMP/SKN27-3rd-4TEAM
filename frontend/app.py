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
    "chat": {"label": "지금 매물 진단", "icon": "💬", "badge": None, "render": chat.render},
    "cases": {"label": "사례·판례", "icon": "⚖️", "badge": None, "render": playbook.render_cases},
    "checklist": {"label": "안전 체크리스트", "icon": "✅", "badge": None, "render": checklist.render},
    "history": {"label": "내 진단 기록", "icon": "📋", "badge": None, "render": history.render},
    # "simulator": {"label": "깡통전세 시뮬레이터", "icon": "📊", "badge": None, "render": simulator.render},
    "playbook": {"label": "피해 대응 안내", "icon": "🆘", "badge": None, "render": playbook.render},
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
            <div class="side-brand">
              <div style="display:flex;align-items:center;gap:10px">
                <div class="side-logo">🏠</div>
                <div>
                  <div class="side-title">안전계약</div>
                  <div class="side-sub">전세사기 진단 서비스</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        for key, view in VIEWS.items():
            if key == "property":
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
        if st.session_state.get("diagnosis_done") and st.session_state.get("report"):
            rpt = st.session_state.report
            ui = rpt.get("user_info", {})
            addr = ui.get("address", "진단 대기 중")
            dep = ui.get("deposit", 0)
            area = ui.get("area_m2", "")
            risk = ui.get("risk_level", "미상")
            score = ui.get("risk_score", 0)
            color = "var(--red)" if risk == "위험" else ("var(--amber)" if risk == "주의" else "var(--green)")
            st.markdown(
                f"""
                <div class="prop-mini">
                  <div class="ttl">{addr}</div>
                  <div class="sub">전세 {dep:,}만원{f' · {area}㎡' if area else ''}</div>
                  <div style="margin-top:8px;display:flex;gap:6px;align-items:center">
                    <span style="width:10px;height:10px;border-radius:50%;background:{color};
                                 box-shadow:0 0 0 3px {color}33;display:inline-block"></span>
                    <b style="color:{color};font-size:12px">{risk} {score}점</b>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="prop-mini"><div class="ttl" style="color:var(--gray-500)">진단 대기 중</div></div>',
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
