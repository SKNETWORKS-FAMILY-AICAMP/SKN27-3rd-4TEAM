"""안전 체크리스트 — 계약 전·중·후 단계별."""

import streamlit as st


SECTIONS = [
    {
        "title": "📐 계약 전 (집 보러 다닐 때)",
        "subtitle": "계약서에 사인하기 전 반드시 확인할 것",
        "items": [
            ("등기부등본 직접 발급해 확인", "정부24·인터넷등기소에서 본인이 직접 발급. 부동산이 보여주는 것만 믿지 마세요.", False),
            ("선순위 근저당·가압류 확인", "을구에 있는 채권액 + 보증금 ≤ 매매가의 80% 인지 계산.", True),
            ("신탁등기 여부 확인", "갑구에 '신탁'이 있으면 임대인이 아닌 수탁자(신탁회사) 동의가 필수.", True),
            ("전세가율 80% 이하 확인", "인근 동일면적 시세 대비. 90% 넘으면 깡통전세 위험.", False),
            ("임대인 본인 확인 (영상통화 녹화)", "대리인 계약은 위임장·인감증명서 원본 확인 + 본인 통화.", False),
            ("HUG 보증보험 가입 가능 여부 확인", "안심전세 앱에서 사전 조회 가능. 가입 거절되면 그 매물은 피하세요.", False),
        ],
    },
    {
        "title": "✍️ 계약 당일 (도장 찍기 전)",
        "subtitle": "공인중개사 사무실에서 반드시 추가할 특약",
        "items": [
            ("당일 등기부 재발급 후 비교", "계약 직전 발급해서 변경 여부 확인. 새 근저당이 잡혀있을 수 있어요.", False),
            ("근저당 말소 조건부 무효 특약 추가", "잔금일까지 말소 안 되면 계약 무효 + 보증금 즉시 반환.", False),
            ("권리변동 통지 의무 특약 추가", "임대차 기간 중 등기부 변동 시 임차인에게 즉시 통지.", False),
            ("계약서 사진·스캔 보관", "특약 포함 전 페이지 백업.", False),
            ("계약금 영수증 받기", "현금보다 계좌이체. 임대인 본인 계좌인지 확인.", False),
        ],
    },
    {
        "title": "🏠 잔금·이사 당일",
        "subtitle": "보증금 지키는 마지막 관문 — 이날을 놓치면 권리가 사라집니다",
        "items": [
            ("당일 등기부 3차 확인", "잔금 송금 직전 한 번 더. 근저당 말소 확인.", False),
            ("잔금 송금 → 임대인 본인 계좌", "타인 계좌·법인 계좌·차명 계좌 모두 거부.", False),
            ("당일 전입신고 (관할 동주민센터)", "다음 날 0시부터 대항력 발생. 하루도 미루지 마세요.", False),
            ("확정일자 받기 (계약서 들고)", "전입신고와 같은 날 처리. 우선변제권의 핵심.", False),
            ("입주 사진·동영상 기록", "기존 하자·시설 상태 기록. 보증금 반환 분쟁 대비.", False),
        ],
    },
    {
        "title": "📅 계약 기간 중 (정기 점검)",
        "subtitle": "안심하지 말고 6개월에 한 번씩",
        "items": [
            ("6개월마다 등기부 변동 확인", "임대인 모르게 새 근저당·가압류가 잡힐 수 있음.", False),
            ("임대인 변경 시 새 임대인 등기 확인", "매매·증여로 소유자 바뀌면 등기부 즉시 확인.", False),
            ("계약 만료 6개월 전 갱신 의사 통지", "주임법상 임차인은 1회 갱신청구권 행사 가능.", False),
            ("이사 갈 때는 임차권등기명령 먼저", "보증금 미반환 상태에서 이사 가도 권리 유지.", False),
        ],
    },
]


def render():
    st.markdown(
        '<div style="font-size:12px;font-weight:700;color:var(--gray-500);'
        'letter-spacing:.04em;margin-bottom:6px">안전 체크리스트 · 4단계 19항목</div>',
        unsafe_allow_html=True,
    )
    st.markdown("# 계약 전부터 만료까지, 단계별 점검표")
    st.markdown(
        '<p style="color:var(--gray-500);font-size:14px">'
        "체크하면 자동 저장됩니다. 다음 진단 때도 그대로 이어집니다.</p>",
        unsafe_allow_html=True,
    )

    # 진행률
    total = sum(len(s["items"]) for s in SECTIONS)
    if "checklist_state" not in st.session_state:
        # 초기값: 일부 done=True 항목 미리 체크
        st.session_state.checklist_state = {}
        for si, s in enumerate(SECTIONS):
            for ii, item in enumerate(s["items"]):
                st.session_state.checklist_state[f"{si}_{ii}"] = item[2]

    done = sum(1 for v in st.session_state.checklist_state.values() if v)
    pct = (done / total) * 100 if total else 0

    color = "var(--green)" if pct >= 80 else ("var(--amber)" if pct >= 50 else "var(--red)")
    st.markdown(
        f"""
        <div class="tw-card" style="display:flex;align-items:center;gap:24px;background:linear-gradient(135deg,#fff 0%,var(--gray-50) 100%)">
          <div style="flex:0 0 auto">
            <div style="font-size:11px;font-weight:800;color:{color};letter-spacing:.06em">현재 완료율</div>
            <div style="font-size:48px;font-weight:800;color:{color};letter-spacing:-0.04em">
              {pct:.0f}%
            </div>
            <div style="color:var(--gray-500);font-size:13px">{done} / {total} 항목 완료</div>
          </div>
          <div style="flex:1">
            <div style="height:14px;background:var(--gray-100);border-radius:999px;overflow:hidden">
              <div style="height:100%;width:{pct}%;background:{color};border-radius:999px;transition:width .3s"></div>
            </div>
            <div style="margin-top:8px;font-size:12px;color:var(--gray-500)">
              80% 이상 완료해야 안전 매물이라고 볼 수 있습니다.
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 섹션별 체크리스트
    for si, sec in enumerate(SECTIONS):
        st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)
        st.markdown(f"### {sec['title']}")
        st.markdown(
            f'<p style="color:var(--gray-500);font-size:13px;margin-top:-8px">{sec["subtitle"]}</p>',
            unsafe_allow_html=True,
        )

        for ii, (title, desc, _) in enumerate(sec["items"]):
            key = f"{si}_{ii}"
            cur = st.session_state.checklist_state.get(key, False)

            c1, c2 = st.columns([0.06, 0.94])
            with c1:

                checked = st.checkbox(title, value=cur, key=f"chk_{key}", label_visibility="collapsed")
                if checked != cur:
                    st.session_state.checklist_state[key] = checked
                    st.rerun()
            with c2:
                done_cls = "done" if cur else ""
                opacity = "1" if cur else "0.95"
                title_color = "var(--gray-500); text-decoration: line-through" if cur else "var(--gray-900)"
                st.markdown(
                    f"""
                    <div class="chk-item {done_cls}" style="opacity:{opacity};margin-bottom:6px">
                      <div>
                        <div class="title" style="color:{title_color}">{title}</div>
                        <div class="desc">{desc}</div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )



