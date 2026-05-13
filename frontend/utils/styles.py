"""토스 스타일 공통 CSS — 모든 페이지에서 import."""

GLOBAL_CSS = """
<style>
  /* ── Pretendard ─────────────────────────────────────── */
  @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');

  html, body, [class*="css"], [class*="st-"] {
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
  }

  /* ── Global tokens ─────────────────────────────────── */
  :root {
    --blue: #3182f6;
    --blue-soft: #e8f3ff;
    --red: #f04452;
    --red-soft: #ffeded;
    --amber: #ff9500;
    --amber-soft: #fff5e6;
    --green: #00c896;
    --green-soft: #e6f9f4;
    --gray-50: #f9fafb;
    --gray-100: #f2f4f6;
    --gray-200: #e5e8eb;
    --gray-300: #d1d6db;
    --gray-500: #8b95a1;
    --gray-700: #4e5968;
    --gray-900: #191f28;
  }

  /* Streamlit base reset */
  .stApp { background: var(--gray-50); }
  .block-container { padding-top: 2rem !important; padding-bottom: 4rem !important; max-width: 1280px !important; }

  /* Hide default Streamlit chrome */
  #MainMenu, footer { visibility: hidden; }
  header[data-testid="stHeader"] {
    visibility: visible;
    background: transparent;
  }
  header[data-testid="stHeader"] > div {
    visibility: visible;
  }


  /* Sidebar */
  section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #061a3a 0%, #031226 100%);
    border-right: 1px solid rgba(255,255,255,.08);
  }
  section[data-testid="stSidebar"] .block-container { padding-top: 1.5rem !important; }
  section[data-testid="stSidebar"] div.stButton > button {
    background: transparent;
    border-color: transparent;
    color: rgba(255,255,255,.82);
    justify-content: flex-start;
  }
  section[data-testid="stSidebar"] div.stButton > button:hover {
    background: rgba(49,130,246,.18);
    border-color: rgba(49,130,246,.18);
    color: #fff;
  }
  section[data-testid="stSidebar"] div.stButton > button[kind="primary"] {
    background: rgba(49,130,246,.32);
    color: #fff;
    border-color: rgba(49,130,246,.28);
  }
  .side-brand { padding: 8px 4px 28px; }
  .side-logo {
    width: 38px; height: 38px; border-radius: 12px;
    background: rgba(49,130,246,.18); border: 1px solid rgba(138,184,255,.34);
    display:grid; place-items:center; color:#fff; font-weight:900; font-size:18px;
  }
  .side-title { font-weight:900; font-size:17px; color:#fff; letter-spacing:-0.02em; }
  .side-sub { font-size:10px; color:rgba(255,255,255,.62); font-weight:600; margin-top:2px; }

  /* Headings */
  h1 { font-weight: 800 !important; letter-spacing: -0.04em; color: var(--gray-900); font-size: 32px !important; line-height: 1.2 !important; }
  h2 { font-weight: 800 !important; letter-spacing: -0.03em; color: var(--gray-900); font-size: 22px !important; }
  h3 { font-weight: 700 !important; letter-spacing: -0.02em; color: var(--gray-900); font-size: 17px !important; }
  h4, h5 { font-weight: 700 !important; color: var(--gray-900); }

  /* Buttons */
  div.stButton > button {
    border-radius: 12px;
    border: 1px solid var(--gray-200);
    background: #fff;
    color: var(--gray-900);
    font-weight: 600;
    padding: 0.6rem 1rem;
    transition: all 0.15s;
  }
  div.stButton > button:hover {
    border-color: var(--blue);
    color: var(--blue);
    background: var(--blue-soft);
  }
  div.stButton > button[kind="primary"] {
    background: var(--blue);
    color: #fff;
    border-color: var(--blue);
  }
  div.stButton > button[kind="primary"]:hover {
    background: #1b64da;
    border-color: #1b64da;
    color: #fff;
  }


  /* File uploader */
  div[data-testid="stFileUploader"] {
    background: #fff;
    border: 1px solid var(--gray-200);
    border-radius: 12px;
    padding: 12px 14px;
  }
  div[data-testid="stFileUploader"] section {
    background: var(--gray-100);
    border: 1px dashed var(--gray-300);
    border-radius: 12px;
    min-height: 76px;
    padding: 14px !important;
  }
  div[data-testid="stFileUploader"] button {
    min-width: 118px;
    height: 40px;
    border-radius: 10px !important;
    background: #fff !important;
    border: 1px solid var(--gray-300) !important;
    color: var(--gray-900) !important;
    font-weight: 800 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: clip !important;
  }
  div[data-testid="stFileUploader"] small,
  div[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzoneInstructions"] {
    color: var(--gray-500) !important;
    font-size: 12px !important;
  }
  /* Cards / wrappers */
  .tw-card {
    background: #ffffff;
    border: 1px solid var(--gray-200);
    border-radius: 18px;
    padding: 22px;
    box-shadow: 0 1px 2px rgba(17,24,39,.02);
  }
  .tw-card + .tw-card { margin-top: 12px; }

  /* Status pill */
  .status-pill {
    display: inline-flex; align-items: center; gap: 12px;
    padding: 10px 16px; border-radius: 999px;
    background: var(--red-soft); border: 1px solid #ffd5d5;
  }
  .status-pill .icon-wrap {
    width: 28px; height: 28px; border-radius: 50%;
    background: var(--red); color: #fff;
    display: grid; place-items: center; font-weight: 800;
  }
  .status-pill .level { font-size: 11px; font-weight: 700; color: var(--red); letter-spacing: .08em; }
  .status-pill .score { font-size: 14px; font-weight: 600; color: var(--gray-900); }

  /* Risk rows */
  .risk-row {
    display: grid; grid-template-columns: 28px 1fr auto; gap: 12px;
    align-items: center; padding: 14px 16px;
    border-radius: 12px; margin-bottom: 8px;
    background: var(--gray-100);
  }
  .risk-row.danger { background: var(--red-soft); }
  .risk-row.caution { background: var(--amber-soft); }
  .risk-row.safe { background: var(--green-soft); }
  .risk-row .ic { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; color: #fff; font-weight: 800; font-size: 12px; }
  .risk-row.danger .ic { background: var(--red); }
  .risk-row.caution .ic { background: var(--amber); }
  .risk-row.safe .ic { background: var(--green); }
  .risk-row .label { font-weight: 700; color: var(--gray-900); }
  .risk-row .meta { font-size: 12px; font-weight: 700; color: var(--gray-500); }

  /* Law/precedent chips */
  .law-chip {
    display: inline-flex; gap: 6px; padding: 4px 10px; border-radius: 999px;
    background: #fff; border: 1px solid var(--gray-200);
    font-size: 12px; color: var(--gray-700); margin: 2px 4px 2px 0;
  }
  .law-chip .lico {
    width: 18px; height: 18px; border-radius: 4px; background: var(--blue); color: #fff;
    display: grid; place-items: center; font-size: 10px; font-weight: 800;
  }

  /* Law banner (개정 알림) */
  .law-banner {
    display: flex; align-items: center; gap: 12px;
    padding: 14px 18px; border-radius: 14px;
    background: linear-gradient(135deg, #eef4ff 0%, #f4f8ff 100%);
    border: 1px solid #dbe6ff; margin-bottom: 18px;
    font-size: 14px; color: var(--gray-700);
  }
  .law-banner .pill {
    background: var(--blue); color: #fff; padding: 4px 10px; border-radius: 999px;
    font-size: 11px; font-weight: 800; letter-spacing: .04em;
  }

  /* Case rows */
  .case-row {
    display: grid; grid-template-columns: 70px 1fr 90px; gap: 14px;
    padding: 14px 16px; border-radius: 12px;
    background: var(--gray-100); margin-bottom: 8px;
    align-items: center; font-size: 13px;
  }
  .case-row .yr {
    font-weight: 800; color: var(--gray-900);
    background: #fff; padding: 6px 8px; border-radius: 8px; text-align: center;
    border: 1px solid var(--gray-200);
  }
  .case-row .yr small { display: block; font-size: 10px; color: var(--gray-500); margin-top: 2px; font-weight: 600; }
  .case-row .result {
    padding: 6px 10px; border-radius: 999px; font-size: 12px; font-weight: 800; text-align: center;
  }
  .case-row .result.bad { background: var(--red-soft); color: var(--red); }
  .case-row .result.good { background: var(--green-soft); color: var(--green); }
  .case-row .result.partial { background: var(--amber-soft); color: var(--amber); }

  /* Stat row */
  .stat-row { display: flex; justify-content: space-between; padding: 8px 0; font-size: 13px; }
  .stat-row b { color: var(--gray-900); font-weight: 800; }
  .stat-row .delta { color: var(--green); font-size: 11px; font-weight: 700; margin-left: 6px; }

  /* Chat-like cells */
  .chat-q {
    background: var(--blue); color: #fff;
    padding: 12px 16px; border-radius: 16px 16px 4px 16px;
    margin-left: auto; max-width: 80%;
    width: fit-content; margin-bottom: 12px;
    font-size: 14px;
  }
  .chat-a {
    background: #fff; border: 1px solid var(--gray-200);
    padding: 16px 18px; border-radius: 16px 16px 16px 4px;
    margin-right: auto; max-width: 92%;
    width: fit-content; margin-bottom: 12px;
    font-size: 14px; line-height: 1.65; color: var(--gray-900);
  }
  .chat-a + .rag-src { margin-top: -4px; margin-bottom: 12px; }

  .rag-src {
    background: var(--gray-100); border-radius: 10px;
    padding: 10px 14px; font-size: 12px; color: var(--gray-700);
    max-width: 92%; display: flex; flex-wrap: wrap; gap: 6px;
  }
  .rag-src b { color: var(--gray-900); margin-right: 4px; }
  .rag-src .ref {
    background: #fff; padding: 3px 8px; border-radius: 999px;
    border: 1px solid var(--gray-200); font-weight: 600;
  }

  /* Property card mini */
  .prop-mini {
    background: var(--gray-100); border-radius: 12px;
    padding: 12px 14px; font-size: 12px;
  }
  section[data-testid="stSidebar"] .prop-mini {
    background: rgba(255,255,255,.08);
    border: 1px solid rgba(255,255,255,.10);
  }
  section[data-testid="stSidebar"] .prop-mini .ttl { color: #fff; }
  section[data-testid="stSidebar"] .prop-mini .sub { color: rgba(255,255,255,.62); }
  .prop-mini-link {
    display: block; text-decoration: none;
    border: 1px solid transparent;
    transition: all .15s ease;
  }
  .prop-mini-link:hover {
    background: #fff;
    border-color: var(--blue);
    box-shadow: 0 8px 18px rgba(49,130,246,.10);
    transform: translateY(-1px);
  }
  .prop-mini .ttl { font-weight: 800; color: var(--gray-900); font-size: 13px; margin-bottom: 4px; }
  .prop-mini .sub { color: var(--gray-500); }

  .prop-detail-grid {
    display: grid; grid-template-columns: 110px 1fr; row-gap: 12px; column-gap: 12px;
    font-size: 14px;
  }
  .prop-detail-grid span { color: var(--gray-500); font-weight: 700; }
  .prop-detail-grid b { color: var(--gray-900); font-weight: 800; }

  .timeline-row {
    display: grid; grid-template-columns: 18px 1fr; gap: 10px;
    padding: 8px 0; align-items: start;
  }
  .timeline-row > span {
    width: 10px; height: 10px; border-radius: 50%; background: var(--gray-300);
    margin-top: 5px; box-shadow: 0 0 0 4px var(--gray-100);
  }
  .timeline-row.done > span { background: var(--green); box-shadow: 0 0 0 4px var(--green-soft); }
  .timeline-row.now > span { background: var(--red); box-shadow: 0 0 0 4px var(--red-soft); }
  .timeline-row b { display: block; font-size: 14px; color: var(--gray-900); }
  .timeline-row small { display: block; font-size: 12px; color: var(--gray-500); margin-top: 2px; }

  .action-row {
    display: grid; grid-template-columns: 26px 1fr; gap: 10px;
    align-items: center; padding: 8px 0; font-size: 13px; color: var(--gray-700);
  }
  .action-row b {
    width: 24px; height: 24px; border-radius: 8px; background: var(--blue-soft);
    color: var(--blue); display: grid; place-items: center; font-size: 12px;
  }

  /* Emergency block */
  .emergency {
    background: #fff4f4; border: 1px solid #ffd5d5; border-radius: 12px;
    padding: 12px 14px; margin-top: 12px;
  }
  .emergency .ttl { font-size: 11px; font-weight: 800; color: var(--red); letter-spacing: .08em; margin-bottom: 8px; }
  .emergency a {
    display: flex; justify-content: space-between; padding: 6px 0;
    font-size: 12px; color: var(--gray-700); text-decoration: none;
  }
  .emergency a:hover { color: var(--blue); }
  .emergency .num { font-weight: 800; color: var(--gray-900); }

  /* History cards */
  .hist-card {
    background: #fff; border: 1px solid var(--gray-200); border-radius: 14px;
    padding: 16px; height: 100%;
  }
  .hist-card .top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  .hist-card .dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
  .hist-card .dot.danger { background: var(--red); box-shadow: 0 0 0 4px var(--red-soft); }
  .hist-card .dot.caution { background: var(--amber); box-shadow: 0 0 0 4px var(--amber-soft); }
  .hist-card .dot.safe { background: var(--green); box-shadow: 0 0 0 4px var(--green-soft); }
  .hist-card .addr { font-weight: 800; font-size: 15px; color: var(--gray-900); }
  .hist-card .meta { font-size: 12px; color: var(--gray-500); margin-top: 4px; }
  .hist-card .score-row { display: flex; align-items: baseline; gap: 4px; margin-top: 12px; }
  .hist-card .score-row b { font-size: 28px; font-weight: 800; letter-spacing: -0.02em; }
  .hist-card .score-row b.danger { color: var(--red); }
  .hist-card .score-row b.caution { color: var(--amber); }
  .hist-card .score-row b.safe { color: var(--green); }
  .hist-card .score-row small { font-size: 13px; color: var(--gray-500); font-weight: 700; }


  .hist-card.selected {
    border-color: var(--blue);
    box-shadow: 0 0 0 3px rgba(49,130,246,.12), 0 8px 18px rgba(15,23,42,.06);
  }
  .compare-card {
    background: #fff;
    border: 1px solid var(--gray-200);
    border-radius: 16px;
    padding: 20px;
    box-shadow: 0 8px 22px rgba(15,23,42,.04);
    min-height: 360px;
  }
  .compare-card .top {
    display:flex;
    align-items:center;
    gap:8px;
    color:var(--gray-700);
    font-size:13px;
    font-weight:900;
    margin-bottom:8px;
  }
  .compare-card h3 {
    margin: 0 0 14px;
    font-size: 18px !important;
    line-height: 1.4 !important;
  }
  .compare-score {
    font-size: 36px;
    font-weight: 900;
    letter-spacing: -0.04em;
    margin-bottom: 14px;
  }
  .compare-score.danger { color: var(--red); }
  .compare-score.caution { color: var(--amber); }
  .compare-score.safe { color: var(--green); }
  .compare-row {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 0;
    border-top: 1px solid var(--gray-100);
    font-size: 13px;
  }
  .compare-row span { color: var(--gray-500); font-weight: 800; }
  .compare-row b { color: var(--gray-900); font-weight: 900; text-align: right; }


  .case-doc-card {
    background:#fff;
    border:1px solid var(--gray-200);
    border-radius:14px;
    padding:18px;
    margin-bottom:10px;
    box-shadow:0 8px 22px rgba(15,23,42,.03);
  }
  .case-doc-card h3 {
    margin:8px 0 6px;
    font-size:17px !important;
    line-height:1.35 !important;
  }
  .case-doc-card p {
    color:var(--gray-700);
    font-size:13px;
    line-height:1.65;
    margin:0 0 12px;
  }
  .case-kind {
    display:inline-flex;
    align-items:center;
    background:var(--blue-soft);
    color:var(--blue);
    border-radius:999px;
    padding:4px 10px;
    font-size:11px;
    font-weight:900;
  }
  .case-path {
    margin-top:10px;
    color:var(--gray-500);
    font-size:11px;
    word-break:break-all;
  }

  /* Playbook cards */
  .pb-card {
    background: #fff; border: 1px solid var(--gray-200); border-radius: 16px;
    padding: 18px; height: 100%;
  }
  .pb-card .urg {
    display: inline-block; padding: 4px 10px; border-radius: 999px;
    font-size: 11px; font-weight: 800; letter-spacing: .04em; margin-bottom: 8px;
  }
  .pb-card .urg.now { background: var(--red-soft); color: var(--red); }
  .pb-card .urg.soon { background: var(--amber-soft); color: var(--amber); }
  .pb-card .urg.plan { background: var(--blue-soft); color: var(--blue); }
  .pb-card h4 { margin: 4px 0 6px; font-size: 17px; font-weight: 800; color: var(--gray-900); }
  .pb-card p { color: var(--gray-500); font-size: 13px; margin: 0 0 12px; }
  .pb-card .tl { padding-top: 12px; border-top: 1px dashed var(--gray-200); }
  .pb-card .t { display: flex; gap: 10px; font-size: 12px; color: var(--gray-700); padding: 4px 0; }
  .pb-card .t .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--blue); margin-top: 7px; flex-shrink: 0; }
  .pb-card .t b { color: var(--gray-900); }
  .pb-card .footer { font-size: 11px; color: var(--gray-500); padding-top: 12px; border-top: 1px solid var(--gray-100); margin-top: 12px; }

  /* Checklist */
  .chk-item {
    display: flex; gap: 12px; align-items: flex-start;
    padding: 14px; border: 1px solid var(--gray-200); border-radius: 12px;
    background: #fff; margin-bottom: 8px;
  }
  .chk-item .chk-icon {
    width: 24px; height: 24px; border-radius: 8px; flex-shrink: 0;
    border: 2px solid var(--gray-300); display: grid; place-items: center;
    color: transparent; font-weight: 800;
  }
  .chk-item.done .chk-icon { background: var(--blue); border-color: var(--blue); color: #fff; }
  .chk-item .title { font-weight: 700; color: var(--gray-900); font-size: 14px; }
  .chk-item .desc { font-size: 12px; color: var(--gray-500); margin-top: 4px; }


  div[data-testid="stCheckbox"] {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 76px;
    padding-top: 2px;
  }
  div[data-testid="stCheckbox"] label {
    min-width: 26px;
    min-height: 26px;
  }
  div[data-testid="stCheckbox"] p {
    display: none;
  }
  /* Section divider */
  .sec-divider { height: 1px; background: var(--gray-200); margin: 24px 0; }

  /* Dashboard / market map */
  .home-hero {
    min-height: 188px; border-radius: 18px; padding: 28px;
    background: linear-gradient(135deg,#071b3a 0%,#123e86 58%,#21b8b0 100%);
    color:#fff; display:grid; grid-template-columns: minmax(0,1fr) 280px; gap: 24px;
    align-items:end; margin-bottom: 18px;
  }
  .home-hero .eyebrow { font-size:12px; font-weight:800; color:rgba(255,255,255,.72); margin-bottom:8px; }
  .home-hero h1 { color:#fff !important; max-width:760px; margin:0; font-size:34px !important; }
  .home-hero p { color:rgba(255,255,255,.72); margin:12px 0 0; font-size:14px; }
  .home-hero-card {
    background:rgba(255,255,255,.13); border:1px solid rgba(255,255,255,.22);
    border-radius:14px; padding:18px; backdrop-filter: blur(8px);
  }
  .home-hero-card span { display:block; font-size:11px; font-weight:800; color:rgba(255,255,255,.68); margin-bottom:8px; }
  .home-hero-card b { display:block; color:#fff; font-size:18px; margin-bottom:6px; }
  .home-hero-card small { color:rgba(255,255,255,.72); font-weight:700; }

  .dash-metric {
    background:#fff; border:1px solid var(--gray-200); border-radius:8px; padding:18px;
    min-height:104px; box-shadow:0 8px 22px rgba(15,23,42,.04);
  }
  .dash-metric span { color:var(--gray-500); font-size:12px; font-weight:800; }
  .dash-metric b { display:block; color:var(--gray-900); font-size:26px; font-weight:900; margin-top:6px; letter-spacing:-0.03em; }
  .dash-metric small { display:block; color:var(--green); font-size:11px; font-weight:800; margin-top:4px; }
  .dash-metric.violet small, .dash-metric.orange small { color:var(--gray-500); }

  .dash-panel {
    background:#fff; border:1px solid var(--gray-200); border-radius:8px; padding:18px;
    box-shadow:0 8px 22px rgba(15,23,42,.04); height:100%;
  }
  .panel-head { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:14px; }
  .panel-head b { color:var(--gray-900); font-size:15px; }
  .panel-head span { color:var(--gray-500); font-size:11px; font-weight:800; }
  .home-map-preview {
    position:relative; height:284px; border-radius:8px;
    background:
      linear-gradient(90deg, rgba(226,232,240,.45) 1px, transparent 1px),
      linear-gradient(rgba(226,232,240,.45) 1px, transparent 1px),
      #f8fbff;
    background-size:34px 34px; overflow:hidden;
  }
  .dong-chip {
    position:absolute; color:#fff; font-weight:900; font-size:13px; padding:28px 34px;
    border-radius:52% 48% 58% 42%; transform:rotate(-7deg);
    box-shadow:0 10px 20px rgba(15,23,42,.12); border:2px solid rgba(255,255,255,.82);
  }
  .dong-chip.p1 { background:#8dccf2; }
  .dong-chip.p2 { background:#63d2ca; }
  .dong-chip.p3 { background:#8bd8de; }
  .dong-chip.p4 { background:#ff9c69; }
  .dong-chip.p5 { background:#ffb45d; }
  .dong-chip.active { background:#ff6b5f; transform:rotate(8deg) scale(1.06); }
  .map-pin {
    position:absolute; left:55%; bottom:28px; background:#3182f6; color:#fff;
    padding:7px 10px; border-radius:999px; font-size:12px; font-weight:900;
    box-shadow:0 0 0 8px rgba(49,130,246,.16);
  }
  .mini-stat {
    display:grid; grid-template-columns:1fr auto; gap:10px; align-items:center;
    border:1px solid var(--gray-200); border-radius:8px; padding:14px; margin-bottom:10px;
  }
  .mini-stat span { color:var(--gray-500); font-size:12px; font-weight:800; }
  .mini-stat b { color:var(--gray-900); font-size:15px; font-weight:900; }
  .mini-stat b.red { color:var(--red); font-size:20px; }
  .rank-row { display:grid; grid-template-columns:28px 1fr 44px; align-items:center; gap:10px; padding:10px 0; border-top:1px solid var(--gray-100); }
  .rank-row b { width:24px; height:24px; border-radius:8px; background:var(--blue-soft); color:var(--blue); display:grid; place-items:center; font-size:12px; }
  .rank-row span { color:var(--gray-700); font-size:13px; font-weight:700; }
  .rank-row em { color:var(--red); font-style:normal; font-size:11px; font-weight:900; text-align:right; }
  .bar-row { display:grid; grid-template-columns:64px 1fr 54px; gap:10px; align-items:center; margin:12px 0; }
  .bar-row span { color:var(--gray-700); font-size:12px; font-weight:800; }
  .bar-row i { height:18px; border-radius:4px; background:linear-gradient(90deg,#ff6b5f,#ffc15a); display:block; }
  .bar-row b { color:var(--gray-900); font-size:12px; text-align:right; }
  .donut { width:132px; height:132px; border-radius:50%; margin:4px auto 14px; background:conic-gradient(#3182f6 0 49%, #20c7bd 49% 76%, #ff9f43 76% 91%, #8b5cf6 91% 100%); position:relative; }
  .donut:after { content:"3,245건"; position:absolute; inset:34px; border-radius:50%; background:#fff; display:grid; place-items:center; color:var(--gray-900); font-weight:900; font-size:13px; }
  .legend-row { display:flex; align-items:center; gap:8px; color:var(--gray-700); font-size:12px; font-weight:700; margin-top:7px; }
  .legend-row span { width:8px; height:8px; border-radius:50%; display:inline-block; }

  .filter-shell {
    background:#fff; border:1px solid var(--gray-200); border-radius:8px; padding:14px 16px 6px;
    margin: 10px 0 16px; box-shadow:0 8px 22px rgba(15,23,42,.04);
  }
  .map-panel { padding:14px; }
  .region-svg { width:100%; height:auto; display:block; border-radius:8px; }
  .map-legend { display:flex; flex-wrap:wrap; gap:12px; padding:10px 8px 0; color:var(--gray-500); font-size:11px; font-weight:800; }
  .map-legend span { display:flex; align-items:center; gap:6px; }
  .map-legend i { width:10px; height:10px; border-radius:50%; display:inline-block; }

  .price-map {
    position: relative;
    min-height: 330px;
    border-radius: 12px;
    overflow: hidden;
    background:
      linear-gradient(90deg, rgba(203,213,225,.45) 1px, transparent 1px),
      linear-gradient(rgba(203,213,225,.45) 1px, transparent 1px),
      linear-gradient(135deg, #eef6ff 0%, #f8fbff 45%, #eefaf7 100%);
    background-size: 48px 48px, 48px 48px, auto;
    border: 1px solid #dbe7f3;
  }
  .price-map:before,
  .price-map:after {
    content: "";
    position: absolute;
    left: -8%;
    right: -8%;
    height: 70px;
    border: 8px solid rgba(148,163,184,.30);
    border-left: 0;
    border-right: 0;
    border-radius: 50%;
    transform: rotate(-10deg);
  }
  .price-map:before { top: 82px; }
  .price-map:after { bottom: 58px; transform: rotate(12deg); }
  .map-title-chip {
    position: absolute;
    left: 18px;
    top: 16px;
    z-index: 3;
    background: rgba(255,255,255,.92);
    border: 1px solid var(--gray-200);
    border-radius: 999px;
    padding: 8px 12px;
    font-size: 12px;
    color: var(--gray-700);
    font-weight: 900;
    box-shadow: 0 8px 20px rgba(15,23,42,.07);
  }
  .map-price-pin {
    position: absolute;
    z-index: 4;
    min-width: 88px;
    transform: translate(-50%, -50%);
    text-align: center;
  }
  .map-price-pin .dot {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--blue);
    margin: 0 auto 7px;
    border: 3px solid #fff;
    box-shadow: 0 0 0 7px rgba(49,130,246,.16), 0 8px 18px rgba(15,23,42,.20);
  }
  .map-price-pin .label {
    background: #fff;
    border: 1px solid var(--gray-200);
    border-radius: 12px;
    padding: 8px 10px;
    box-shadow: 0 8px 22px rgba(15,23,42,.10);
  }
  .map-price-pin b {
    display: block;
    color: var(--gray-900);
    font-size: 13px;
    line-height: 1.2;
  }
  .map-price-pin span {
    display: block;
    color: var(--gray-500);
    font-size: 11px;
    font-weight: 800;
    margin-top: 2px;
  }
  .map-price-pin.hot .dot { background: var(--red); box-shadow: 0 0 0 7px rgba(240,68,82,.16), 0 8px 18px rgba(15,23,42,.20); }
  .map-price-pin.warm .dot { background: var(--amber); box-shadow: 0 0 0 7px rgba(255,149,0,.16), 0 8px 18px rgba(15,23,42,.20); }
  .map-price-pin.cool .dot { background: #20c7bd; box-shadow: 0 0 0 7px rgba(32,199,189,.16), 0 8px 18px rgba(15,23,42,.20); }
  .map-price-pin.active .label {
    border-color: var(--red);
    box-shadow: 0 0 0 3px rgba(240,68,82,.12), 0 10px 24px rgba(15,23,42,.12);
  }
  .current-property-pin {
    position: absolute;
    z-index: 5;
    left: 58%;
    top: 58%;
    transform: translate(-50%, -50%);
    background: var(--gray-900);
    color: #fff;
    padding: 8px 11px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 900;
    box-shadow: 0 0 0 7px rgba(25,31,40,.12), 0 8px 18px rgba(15,23,42,.18);
  }
  .map-watermark {
    position: absolute;
    right: 18px;
    bottom: 14px;
    color: rgba(78,89,104,.38);
    font-size: 11px;
    font-weight: 900;
    letter-spacing: .05em;
  }

  .market-table { width:100%; border-collapse:collapse; font-size:12px; }
  .market-table th { text-align:left; color:var(--gray-500); font-size:11px; padding:8px 10px; border-bottom:1px solid var(--gray-200); }
  .market-table td { padding:10px; border-bottom:1px solid var(--gray-100); color:var(--gray-700); font-weight:700; }
  .market-table td:nth-child(3) { color:var(--blue); font-weight:900; }

  @media (max-width: 900px) {
    .home-hero { grid-template-columns: 1fr; }
    .home-hero h1 { font-size:28px !important; }
    .bar-row { grid-template-columns:58px 1fr 48px; }
  }
</style>
"""





