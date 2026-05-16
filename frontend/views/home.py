"""Public landing home for the lease fraud diagnosis service."""

from textwrap import dedent

import streamlit as st


def _home_css() -> str:
    return """
    <style>
      section[data-testid="stSidebar"],
      div[data-testid="stSidebarCollapsedControl"] {
        display: none !important;
      }
      .stApp {
        background: #ffffff;
      }
      .block-container {
        max-width: 100% !important;
        padding: 0 !important;
      }
      .home-shell {
        color: #111827;
        background: #ffffff;
      }
      .home-visual {
        min-height: 532px;
        padding: 62px 28px 58px;
        background: linear-gradient(180deg, #eef6ff 0%, #ffffff 82%);
        border-bottom: 1px solid #e5e8eb;
        text-align: center;
      }
      .home-inner {
        width: min(1324px, calc(100vw - 56px));
        margin: 0 auto;
      }
      .home-badge {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        padding: 8px 17px;
        border: 1px solid #b9d5ff;
        border-radius: 999px;
        background: rgba(255, 255, 255, .72);
        color: #2563eb;
        font-size: 13px;
        font-weight: 800;
      }
      .home-badge span {
        font-size: 15px;
      }
      .home-title {
        margin: 24px auto 0;
        max-width: 640px;
        font-size: 42px;
        line-height: 1.25;
        letter-spacing: 0;
        font-weight: 900;
      }
      .home-desc {
        margin: 21px auto 0;
        max-width: 570px;
        color: #64748b;
        font-size: 16px;
        line-height: 1.72;
        font-weight: 600;
      }
      .home-primary-cta {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        height: 51px;
        margin-top: 32px;
        border-radius: 12px;
        background: #3182f6;
        color: #ffffff !important;
        text-decoration: none !important;
        font-size: 15px;
        font-weight: 900;
        transition: background .15s ease, transform .15s ease;
      }
      .home-primary-cta:hover {
        background: #1b64da;
        transform: translateY(-1px);
      }
      .home-secondary-cta {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 160px;
        height: 43px;
        margin-top: 12px;
        border: 1px solid #d1d6db;
        border-radius: 11px;
        background: #ffffff;
        color: #111827 !important;
        text-decoration: none !important;
        font-size: 14px;
        font-weight: 800;
      }
      .home-trust {
        display: flex;
        justify-content: center;
        gap: 25px;
        margin-top: 29px;
        color: #8b95a1;
        font-size: 12px;
        font-weight: 800;
      }
      .home-steps-wrap {
        padding: 58px 28px 48px;
      }
      .home-section-title {
        margin: 0 0 34px;
        text-align: center;
        font-size: 26px;
        line-height: 1.25;
        font-weight: 900;
        letter-spacing: 0;
      }
      .home-step-grid,
      .home-card-grid {
        display: grid;
        gap: 20px;
        margin: 0 auto;
      }
      .home-step-grid {
        max-width: 990px;
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }
      .home-step-card {
        min-height: 188px;
        padding: 27px 24px;
        border: 1px solid #e0e6ed;
        border-radius: 14px;
        background: #ffffff;
      }
      .home-num {
        display: grid;
        place-items: center;
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: #3182f6;
        color: #ffffff;
        font-size: 17px;
        font-weight: 900;
      }
      .home-card-title {
        margin: 18px 0 8px;
        color: #0f172a;
        font-size: 18px;
        line-height: 1.35;
        font-weight: 900;
        letter-spacing: 0;
      }
      .home-card-copy {
        margin: 0;
        color: #64748b;
        font-size: 14px;
        line-height: 1.75;
        font-weight: 600;
      }
      .home-actions-wrap {
        padding: 15px 28px 24px;
      }
      .home-card-grid {
        max-width: 754px;
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }
      .home-action-card {
        display: block;
        min-height: 203px;
        padding: 24px;
        border: 1px solid #e0e6ed;
        border-radius: 14px;
        background: #ffffff;
        color: inherit !important;
        text-decoration: none !important;
        transition: border-color .15s ease, box-shadow .15s ease, transform .15s ease;
      }
      .home-action-card:hover {
        border-color: #b9d5ff;
        box-shadow: 0 14px 30px rgba(15, 23, 42, .08);
        transform: translateY(-2px);
      }
      .home-icon {
        display: grid;
        place-items: center;
        width: 48px;
        height: 48px;
        border-radius: 12px;
        background: #eef6ff;
        font-size: 22px;
      }
      .home-icon.green {
        background: #edf9f4;
      }
      .home-icon.red {
        background: #ffeded;
      }
      .home-action {
        margin-top: 17px;
        color: #2563eb;
        font-size: 14px;
        font-weight: 900;
      }
      .home-action.red {
        color: #f04452;
      }
      .home-stats {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 18px;
        max-width: 690px;
        margin: 56px auto 0;
        padding: 34px 28px;
        border-radius: 16px;
        background: #f2f4f6;
      }
      .home-stat b {
        display: block;
        color: #3182f6;
        font-size: 28px;
        line-height: 1.1;
        font-weight: 900;
      }
      .home-stat span {
        display: block;
        margin-top: 14px;
        color: #64748b;
        font-size: 12px;
        font-weight: 800;
      }
      .home-notice {
        margin: 39px auto 0;
        max-width: 650px;
        color: #8b95a1;
        text-align: center;
        font-size: 12px;
        line-height: 1.7;
        font-weight: 700;
      }
      .home-footer {
        margin-top: 36px;
        padding: 16px 20px;
        background: #f8fafc;
        border-top: 1px solid #e5e8eb;
        color: #8b95a1;
        text-align: center;
        font-size: 12px;
        font-weight: 700;
      }
      @media (max-width: 900px) {
        .home-inner {
          width: min(100% - 32px, 720px);
        }
        .home-visual {
          min-height: auto;
          padding: 42px 16px;
        }
        .home-title {
          font-size: 34px;
        }
        .home-step-grid,
        .home-card-grid,
        .home-stats {
          grid-template-columns: 1fr;
        }
        .home-trust {
          flex-wrap: wrap;
          gap: 10px 18px;
        }
      }
    </style>
    """


def render():
    st.markdown(_home_css(), unsafe_allow_html=True)
    st.markdown(
        dedent(
            """
        <div class="home-shell">
          <div class="home-visual">
            <div class="home-inner">
              <div class="home-badge"><span>♡</span> 서울 종로구 · 전세사기 진단 서비스</div>
              <div class="home-title">계약하기 전에<br />먼저 안전한지 확인하세요</div>
              <div class="home-desc">
                계약서를 올리면, AI가 종로구 실거래가와
                판례 85건을 근거로 위험을 진단해 드립니다.
              </div>
              <a class="home-primary-cta" href="?view=chat" target="_self">자료 올리고 진단 시작 →</a>
              <div class="home-trust">
                <span>✓ 무료</span>
                <span>✓ 1분 진단</span>
                <span>✓ 자료는 저장되지 않음</span>
              </div>
            </div>
          </div>

          <div class="home-steps-wrap">
            <div class="home-inner">
              <div class="home-section-title">3단계로 끝나요</div>
              <div class="home-step-grid">
                <div class="home-step-card">
                  <div class="home-num">1</div>
                  <div class="home-card-title">자료 업로드</div>
                  <div class="home-card-copy">계약서 DOCX를 올리거나, 주소와 전세금만 입력해도 됩니다.</div>
                </div>
                <div class="home-step-card">
                  <div class="home-num">2</div>
                  <div class="home-card-title">AI 자동 분석</div>
                  <div class="home-card-copy">전세가율·특약 조항 등 위험 항목을 자동 점검합니다.</div>
                </div>
                <div class="home-step-card">
                  <div class="home-num">3</div>
                  <div class="home-card-title">맞춤 대응 안내</div>
                  <div class="home-card-copy">비슷한 사례의 회수율과 다음에 해야 할 일을 알려드립니다.</div>
                </div>
              </div>
            </div>
          </div>

          <div class="home-actions-wrap">
            <div class="home-inner">
              <div class="home-card-grid">
                <a class="home-action-card" href="?view=chat" target="_self">
                  <div class="home-icon">🧠</div>
                  <div class="home-card-title">지금 매물 진단하기</div>
                  <div class="home-card-copy">계약서를 올리고 위험도 분석</div>
                  <div class="home-action">시작 →</div>
                </a>
                <a class="home-action-card" href="?view=simulator" target="_self">
                  <div class="home-icon">📊</div>
                  <div class="home-card-title">깡통전세 시뮬레이터</div>
                  <div class="home-card-copy">경매 시 보증금 회수율 계산</div>
                  <div class="home-action">계산 →</div>
                </a>
                <a class="home-action-card" href="?view=cases" target="_self">
                  <div class="home-icon">⚖️</div>
                  <div class="home-card-title">사례·판례 플레이북</div>
                  <div class="home-card-copy">상황별 단계별 대응 가이드</div>
                  <div class="home-action">보기 →</div>
                </a>
                <a class="home-action-card" href="?view=checklist" target="_self">
                  <div class="home-icon green">✅</div>
                  <div class="home-card-title">안전 체크리스트</div>
                  <div class="home-card-copy">계약 전 19가지 확인 항목</div>
                  <div class="home-action">체크 →</div>
                </a>
                <a class="home-action-card" href="?view=playbook" target="_self">
                  <div class="home-icon red">🆘</div>
                  <div class="home-card-title">이미 피해를 입었다면</div>
                  <div class="home-card-copy">신고 창구 · 진행 순서 안내</div>
                  <div class="home-action red">바로가기 →</div>
                </a>
                <a class="home-action-card" href="?view=history" target="_self">
                  <div class="home-icon">📋</div>
                  <div class="home-card-title">내 진단 기록</div>
                  <div class="home-card-copy">이전에 검토한 매물 비교</div>
                  <div class="home-action">보기 →</div>
                </a>
              </div>

              <div class="home-stats">
                <div class="home-stat"><b>1,160건</b><span>종로구 2025 전세 실거래가</span></div>
                <div class="home-stat"><b>157건</b><span>대법원·하급심 판례 분석</span></div>
                <div class="home-stat"><b>47건</b><span>HUG 대위변제 공개 데이터</span></div>
                <div class="home-stat"><b>2026.3.1</b><span>최신 주임법 개정 반영</span></div>
              </div>

              <div class="home-notice">
                ▲ 본 서비스는 법률 자문이 아닌 데이터 기반 사전 점검 도구입니다.
                실제 계약 전 변호사·공인중개사 상담을 권장합니다.
              </div>
            </div>
          </div>

          <div class="home-footer">
            🔒 업로드한 계약서는 분석 후 즉시 폐기됩니다 · 본 분석은 참고용이며 최종 계약 전 공인중개사·법률 전문가 상담을 권장합니다 · v1.0
          </div>
        </div>
        """
        ).replace("\n", ""),
        unsafe_allow_html=True,
    )
