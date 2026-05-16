"""지역별 시세 확인 — Leaflet 지도."""

import streamlit as st


REGION_DATA = {
    "서울특별시": {
        "종로구": {
            "평창동": (35500, 318, 60.2, "아파트·연립", 37.6112, 126.9687),
            "이화동": (32800, 267, 59.1, "연립·다세대", 37.5797, 127.0040),
            "삼청동": (31200, 201, 57.8, "단독·다가구", 37.5907, 126.9817),
            "가회동": (29900, 176, 54.3, "연립·다세대", 37.5838, 126.9848),
            "혜화동": (28700, 254, 56.7, "오피스텔", 37.5872, 127.0015),
            "무악동": (26200, 153, 52.4, "아파트", 37.5727, 126.9577),
            "교남동": (24800, 142, 49.8, "오피스텔", 37.5687, 126.9657),
            "부암동": (23100, 131, 51.6, "단독·다가구", 37.5932, 126.9627),
        },
        "강남구": {
            "역삼동": (64500, 412, 61.3, "오피스텔", 37.5007, 127.0367),
            "대치동": (78200, 388, 72.4, "아파트", 37.4947, 127.0617),
            "청담동": (83500, 244, 78.1, "아파트", 37.5247, 127.0467),
            "논현동": (59800, 361, 55.8, "연립·다세대", 37.5147, 127.0267),
            "삼성동": (74400, 297, 69.4, "아파트", 37.5087, 127.0617),
            "개포동": (68800, 316, 64.7, "아파트", 37.4787, 127.0567),
        },
        "마포구": {
            "공덕동": (42100, 305, 58.8, "아파트", 37.5437, 126.9517),
            "아현동": (39800, 286, 55.2, "연립·다세대", 37.5557, 126.9557),
            "상암동": (45200, 251, 63.5, "아파트", 37.5777, 126.8917),
            "서교동": (37600, 331, 48.9, "오피스텔", 37.5507, 126.9177),
            "망원동": (34200, 278, 46.2, "연립·다세대", 37.5557, 126.9077),
            "합정동": (38900, 219, 51.4, "오피스텔", 37.5497, 126.9147),
        },
    },
    "경기도": {
        "성남시 분당구": {
            "정자동": (61200, 288, 66.8, "아파트", 37.3647, 127.1097),
            "서현동": (57400, 241, 63.2, "아파트", 37.3777, 127.1237),
            "수내동": (59100, 224, 64.5, "아파트", 37.3777, 127.1137),
            "야탑동": (48200, 307, 58.1, "오피스텔", 37.4107, 127.1257),
            "구미동": (43800, 189, 56.2, "연립·다세대", 37.3507, 127.1077),
        },
        "수원시 영통구": {
            "영통동": (35600, 344, 59.7, "아파트", 37.2507, 127.0567),
            "망포동": (33100, 298, 57.6, "아파트", 37.2537, 127.0447),
            "매탄동": (29400, 263, 52.9, "연립·다세대", 37.2627, 127.0367),
            "이의동": (41700, 201, 62.3, "아파트", 37.2837, 127.0667),
        },
    },
}


def _per_pyeong(data) -> int:
    return round(data[0] / (data[2] / 3.3058))


def _pin_color(value: int) -> str:
    if value >= 1900:
        return "#f04452"
    if value >= 1750:
        return "#ff9500"
    if value >= 1600:
        return "#20c7bd"
    return "#8dccf2"


def _build_leaflet_html(gu: str, dongs: dict, selected_dong: str) -> str:
    first = list(dongs.values())[0]
    center_lat = sum(d[4] for d in dongs.values()) / len(dongs)
    center_lng = sum(d[5] for d in dongs.values()) / len(dongs)

    markers_js = []
    for name, d in dongs.items():
        val = _per_pyeong(d)
        color = _pin_color(val)
        is_selected = name == selected_dong
        border = f"3px solid {color}" if is_selected else "1px solid #e5e8eb"
        shadow = f"0 0 0 4px {color}33, 0 4px 12px rgba(0,0,0,.15)" if is_selected else "0 4px 12px rgba(0,0,0,.1)"
        markers_js.append(f"""
        L.marker([{d[4]}, {d[5]}], {{
            icon: L.divIcon({{
                className: '',
                html: '<div style="text-align:center;min-width:80px;transform:translate(-50%,-100%)">' +
                      '<div style="width:12px;height:12px;border-radius:50%;background:{color};margin:0 auto 4px;border:2.5px solid #fff;box-shadow:0 0 0 5px {color}28,0 4px 10px rgba(0,0,0,.18)"></div>' +
                      '<div style="background:#fff;border:{border};border-radius:10px;padding:6px 8px;box-shadow:{shadow};display:inline-block">' +
                      '<b style="display:block;color:#191f28;font-size:12px;line-height:1.2;white-space:nowrap">{name}</b>' +
                      '<span style="display:block;color:#8b95a1;font-size:10px;font-weight:700;margin-top:1px">{val:,}만원/평</span>' +
                      '</div></div>',
                iconSize: [0, 0],
                iconAnchor: [0, 0]
            }})
        }}).addTo(map);
        """)

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  html, body {{ margin:0; padding:0; }}
  #map {{ width:100%; height:400px; border-radius:12px; border:1px solid #dbe7f3; }}
</style>
</head><body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
window.addEventListener('load', function() {{
    var map = L.map('map', {{
        center: [{center_lat}, {center_lng}],
        zoom: 14,
        zoomControl: true,
        attributionControl: false
    }});
    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}@2x.png', {{
        maxZoom: 18
    }}).addTo(map);
    {"".join(markers_js)}
}});
</script>
</body></html>"""


def render():
    st.markdown(
        '<div style="font-size:12px;font-weight:700;color:var(--gray-500);'
        'letter-spacing:.04em;margin-bottom:6px">지역별 시세 · 동별 평당 보증금 지도</div>',
        unsafe_allow_html=True,
    )
    st.markdown("# 지역별 시세")
    st.markdown(
        '<p style="color:var(--gray-500);font-size:14px;margin-top:-8px">'
        "시도와 시군구를 선택하면 해당 구의 동별 평당 보증금을 지도와 순위로 확인할 수 있습니다.</p>",
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    sido = c1.selectbox("시도", list(REGION_DATA.keys()), key="market_sido")
    sigungu_options = list(REGION_DATA[sido].keys())
    if st.session_state.get("market_sigungu") not in sigungu_options:
        st.session_state.market_sigungu = sigungu_options[0]
    sigungu = c2.selectbox("시군구", sigungu_options, key="market_sigungu")
    dong_options = list(REGION_DATA[sido][sigungu].keys())
    if st.session_state.get("market_dong") not in dong_options:
        st.session_state.market_dong = dong_options[0]
    dong = c3.selectbox("동", dong_options, key="market_dong")

    dongs = REGION_DATA[sido][sigungu]
    selected = dongs[dong]
    total_count = sum(item[1] for item in dongs.values())
    avg_deposit = round(sum(item[0] for item in dongs.values()) / len(dongs))
    avg_area = sum(item[2] for item in dongs.values()) / len(dongs)

    m1, m2, m3, m4 = st.columns(4)
    for col, (label, value, delta, tone) in zip(
        (m1, m2, m3, m4),
        [
            ("총 거래 건수", f"{total_count:,}건", "선택 구 기준", "blue"),
            ("평균 평당 보증금", f"{round(avg_deposit / (avg_area / 3.3058)):,}만원", "동별 평당", "green"),
            ("평균 면적", f"{avg_area:.1f}㎡", "실거래 기준", "violet"),
            ("선택 지역", dong, f"{sido} {sigungu}", "orange"),
        ],
    ):
        with col:
            st.markdown(
                f'<div class="dash-metric {tone}"><span>{label}</span><b>{value}</b><small>{delta}</small></div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)

    map_col, info_col = st.columns([1.75, 1])
    with map_col:
        st.components.v1.html(
            _build_leaflet_html(sigungu, dongs, dong),
            height=420,
        )
        st.markdown(
            """
            <div class="map-legend">
              <span><i style="background:#8dccf2"></i>~1,600</span>
              <span><i style="background:#20c7bd"></i>1,600~1,750</span>
              <span><i style="background:#ff9500"></i>1,750~1,900</span>
              <span><i style="background:#f04452"></i>1,900~</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with info_col:
        st.markdown(
            f"""
            <div class="dash-panel selected-region">
              <div class="panel-head"><b>{dong}</b><span>선택 지역</span></div>
              <div class="mini-stat"><span>평균 평당 보증금</span><b class="red">{_per_pyeong(selected):,}만원</b></div>
              <div class="mini-stat"><span>거래 건수</span><b>{selected[1]:,}건</b></div>
              <div class="mini-stat"><span>평균 면적</span><b>{selected[2]:.1f}㎡</b></div>
              <div class="mini-stat"><span>주요 매물 유형</span><b>{selected[3]}</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)
    left, right = st.columns([1.3, 1])
    sorted_dongs = sorted(dongs.items(), key=lambda item: _per_pyeong(item[1]), reverse=True)
    with left:
        rows = "".join(
            f"<tr><td>{i}</td><td>{name}</td><td>{_per_pyeong(data):,}</td><td>{data[1]:,}</td><td>{data[2]:.1f}</td></tr>"
            for i, (name, data) in enumerate(sorted_dongs, 1)
        )
        st.markdown(
            f"""
            <div class="dash-panel">
              <div class="panel-head"><b>{sigungu} 동별 순위</b><span>평당 보증금순</span></div>
              <table class="market-table">
                <thead><tr><th>순위</th><th>지역</th><th>평당 보증금</th><th>거래 건수</th><th>평균 면적</th></tr></thead>
                <tbody>{rows}</tbody>
              </table>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        bars = "".join(
            f"<div class='bar-row'><span>{name}</span><i style='width:{max(28, _per_pyeong(data) / _per_pyeong(sorted_dongs[0][1]) * 92):.0f}%'></i><b>{_per_pyeong(data):,}</b></div>"
            for name, data in sorted_dongs[:5]
        )
        st.markdown(
            f"""
            <div class="dash-panel">
              <div class="panel-head"><b>동별 평당 보증금 TOP 5</b><span>만원/평</span></div>
              {bars}
            </div>
            """,
            unsafe_allow_html=True,
        )
