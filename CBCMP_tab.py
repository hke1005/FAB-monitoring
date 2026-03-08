import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# 페이지 기본 설정/공통 스타일
# =========================================================
st.set_page_config(layout="wide", page_title="CBCMP 공정 관리자 대시보드", initial_sidebar_state="collapsed")

st.markdown("""
<style>
[data-testid="stMetricValue"] {
  font-size: 28px;
  color: #1E3A8A;
  font-weight: bold;
}
[data-testid="stMetricLabel"] {
  font-size: 16px;
  color: #4B5563;
}
div[data-testid="stMetric"] {
  background-color: #EFF6FF;
  padding: 15px;
  border-radius: 10px;
  border: 1px solid #BFDBFE;
  box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
}
.manager-card {
  background-color: #1E3A8A;
  color: white;
  padding: 15px;
  border-radius: 10px;
  text-align: left;
  box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
  margin-bottom: 20px;
}
.manager-card h4 { margin: 0; padding-bottom: 5px; color: white; }
.manager-card p { margin: 0; font-size: 14px; opacity: 0.9; }
.donut-container {
  background-color: #9CA3AF;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  padding: 12px 10px;
  box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.05);
}
div[data-testid="stHorizontalBlock"] > div:nth-child(2) {
  border-left: 3px solid #9CA3AF;
  padding-left: 20px;
}
div[data-testid="stHorizontalBlock"] div[data-testid="stHorizontalBlock"] > div:nth-child(2) {
  border-left: none !important;
  padding-left: 5px !important;
}
.mes-card {
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  border-radius: 16px;
  padding: 14px 14px 10px 14px;
  box-shadow: 0 6px 18px rgba(0,0,0,0.06);
}
.mes-title {
  font-size: 16px;
  font-weight: 900;
  color: #111827;
  margin: 0 0 2px 0;
}
.mes-sub {
  font-size: 12px;
  color: #6B7280;
  margin: 0 0 10px 0;
}
</style>
""", unsafe_allow_html=True)
# 로컬 데이터/이미지 파일 경로
BASE_DIR = Path(__file__).parent
DEFECT_MAP_PATH = BASE_DIR / "cbcmp_defect_map_no9.csv"
TS_PATH         = BASE_DIR / "cbcmp_lot_process_timeseries.csv"
EQUIP_IMG_PATH  = BASE_DIR / "cbcmp_equipment.png"
SOURCE_KOR_PATH = BASE_DIR / "반도체_결함_데이터_한글.csv"

WAFER_RADIUS = 150000  # wafer map 諛섍꼍(醫뚰몴 ?⑥쐞)

# 공통 유틸 함수(인코딩, Lot 정규화, SPC 계산)
# =========================================================
def safe_read_csv(path: Path, encoding_candidates=("utf-8-sig", "utf-8", "cp949")):
    last_err = None
    for enc in encoding_candidates:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception as e:
            last_err = e
    raise last_err

def norm_lot(x: str) -> str:
    """Lot 문자열을 정규화한다(공백/대소문자 정리)."""
    if x is None:
        return ""
    return str(x).strip().replace("\u00A0", " ").strip().upper()

def add_spc_lines(fig: go.Figure, mean: float, ucl: float, lcl: float):
    if mean is not None and np.isfinite(mean):
        fig.add_hline(y=mean, line_dash="dot", line_width=2, annotation_text="Mean", annotation_position="top left")
    if ucl is not None and np.isfinite(ucl):
        fig.add_hline(y=ucl, line_dash="dash", line_width=2, line_color="#EF4444", annotation_text="UCL", annotation_position="top left")
    if lcl is not None and np.isfinite(lcl):
        fig.add_hline(y=lcl, line_dash="dash", line_width=2, line_color="#EF4444", annotation_text="LCL", annotation_position="bottom left")
    return fig

def compute_ucl_lcl(series: pd.Series, k: float = 3.0):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 5:
        return (None, None, None)
    mu = float(s.mean())
    sd = float(s.std(ddof=1))
    if sd == 0 or not np.isfinite(sd):
        return (mu, mu, mu)
    return (mu, mu + k * sd, mu - k * sd)


# def _get_font(size: int = 22):
#     try:
#         return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
#     except Exception:
#         return ImageFont.load_default()

# def _get_font(size: int = 22):
#     try:
#         f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
#         return f
#     except Exception as e:
#         return ImageFont.load_default()
    

# from pathlib import Path
# from PIL import ImageFont

# def _get_font(size: int = 22):
#     candidates = [
#         "C:/Windows/Fonts/malgunbd.ttf",
#         "C:/Windows/Fonts/malgun.ttf",
#         "C:/Windows/Fonts/arialbd.ttf",
#         "C:/Windows/Fonts/arial.ttf",
#     ]
#     for fp in candidates:
#         try:
#             if Path(fp).exists():
#                 return ImageFont.truetype(fp, size)
#         except Exception:
#             pass
#     # 理쒗썑 fallback
#     return ImageFont.load_default()


FONT_PATH = BASE_DIR / "malgunbd.ttf"

def _get_font(size: int = 22):
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except Exception as e:
        # st.sidebar.error(f"Font load failed: {e}")
        return ImageFont.load_default()
    


# 설비 이미지 위에 KPI 값을 덧그려서 보여주는 함수
def render_cbcmp_kpi_overlay(latest: dict, base_img_path: Path = EQUIP_IMG_PATH) -> BytesIO:
    """
    ???λ퉬 ?대?吏 ?꾩뿉 '珥덈줉 KPI 諛뺤뒪 3媛?留??ㅻ쾭?덉씠:
    - Slurry Flow / Pressure(Mid) / Removal Rate
    """
    img = Image.open(base_img_path).convert("RGBA")

    scale = 2
    img = img.resize((int(img.width*scale), int(img.height*scale)))
    # img = Image.open(base_img_path).convert("RGBA")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    font_title = _get_font(60)
    font_val   = _get_font(100)
    font_small = _get_font(80)

    def rrect(x0, y0, x1, y1, radius=18, fill=(220, 252, 231, 220), outline=(16, 185, 129, 255), width=3):
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=outline, width=width)

    slurry = latest.get("slurry_flow_ml_min", np.nan)
    rr     = latest.get("removal_rate_nm_min", np.nan)
    pm     = latest.get("pressure_middle_psi", np.nan)

    box_w = int(w * 0.39)
    box_h = int(h * 0.08)
    x0 = int(w * 0.60)
    y0 = int(h * 0.14)
    gap = int(h * 0.15)

    items = [
        ("Slurry Flow",    f"{slurry:,.1f} mL/min" if np.isfinite(slurry) else "-"),
        ("Pressure (Mid)", f"{pm:,.2f} psi"        if np.isfinite(pm)     else "-"),
        ("Removal Rate",   f"{rr:,.1f} nm/min"     if np.isfinite(rr)     else "-"),
    ]

    for i, (lab, val) in enumerate(items):
        yy0 = y0 + i * (box_h + gap)
        yy1 = yy0 + box_h
        rrect(x0, yy0, x0 + box_w, yy1)
        draw.text((x0 + 18, yy0 + 10), lab, font=font_title, fill=(17, 24, 39, 255))
        draw.text((x0 + 18, yy0 + int(box_h * 0.48)), val, font=font_val, fill=(3, 105, 161, 255))

    # st.sidebar.write("FONT:", type(font_val), getattr(font_val, "path", "NO_PATH"), getattr(font_val, "size", "NO_SIZE"))

    out = BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out

# 우측 패널의 압력 존 요약 카드 HTML 생성
def pressure_zone_panel(pc, pm, pe):
    def fmt(v):
        return "-" if v is None or not np.isfinite(v) else f"{v:.2f} psi"

    html = f"""
    <div style="background:#F3F4F6;border:1px solid #E5E7EB;border-radius:14px;padding:10px 12px;">
      <div style="font-weight:900;color:#111827;font-size:13px;margin-bottom:6px;">압력 존 모니터링</div>

      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
        <div style="font-weight:800;color:#374151;font-size:12px;">Center Zone</div>
        <div style="display:flex;align-items:center;gap:8px;">
          <div style="background:#10B981;color:white;font-weight:900;padding:3px 9px;border-radius:8px;font-size:12px;">{fmt(pc)}</div>
          <div style="width:40px;height:8px;background:#10B981;border-radius:999px;clip-path: polygon(0 0, 85% 0, 85% 0, 100% 50%, 85% 100%, 0 100%);"></div>
        </div>
      </div>

      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
        <div style="font-weight:800;color:#374151;font-size:12px;">Middle Zone</div>
        <div style="display:flex;align-items:center;gap:8px;">
          <div style="background:#F59E0B;color:white;font-weight:900;padding:3px 9px;border-radius:8px;font-size:12px;">{fmt(pm)}</div>
          <div style="width:40px;height:8px;background:#F59E0B;border-radius:999px;clip-path: polygon(0 0, 85% 0, 85% 0, 100% 50%, 85% 100%, 0 100%);"></div>
        </div>
      </div>

      <div style="display:flex;align-items:center;justify-content:space-between;">
        <div style="font-weight:800;color:#374151;font-size:12px;">Edge Zone</div>
        <div style="display:flex;align-items:center;gap:8px;">
          <div style="background:#EF4444;color:white;font-weight:900;padding:3px 9px;border-radius:8px;font-size:12px;">{fmt(pe)}</div>
          <div style="width:40px;height:8px;background:#EF4444;border-radius:999px;clip-path: polygon(0 0, 85% 0, 85% 0, 100% 50%, 85% 100%, 0 100%);"></div>
        </div>
      </div>
    </div>
    """
    return html

# SPC 시계열 차트(Mean/UCL/LCL + 이상점) 생성
def plot_spc_timeseries(df_plot: pd.DataFrame,
                        ycol: str,
                        title: str,
                        y_label: str,
                        spc_df: pd.DataFrame,
                        k: float = 3.0,
                        height: int = 240) -> go.Figure:
    """
    - 시계열 line + Mean/UCL/LCL 추가
    - UCL/LCL 벗어난 포인트는 빨간 점으로 표시
    """
    # UCL/LCL 
    mean, ucl, lcl = compute_ucl_lcl(spc_df[ycol], k=float(k))

    fig = px.line(
        df_plot, x="timestamp", y=ycol,
        labels={"timestamp": "Time", ycol: y_label},
        height=height
    )

    fig = add_spc_lines(fig, mean, ucl, lcl)

    s = pd.to_numeric(df_plot[ycol], errors="coerce")
    is_ooc = pd.Series(False, index=df_plot.index)

    if ucl is not None and np.isfinite(ucl):
        is_ooc = is_ooc | (s > ucl)
    if lcl is not None and np.isfinite(lcl):
        is_ooc = is_ooc | (s < lcl)

    ooc_df = df_plot.loc[is_ooc & s.notna(), ["timestamp", ycol]].copy()

    if not ooc_df.empty:
        fig.add_scatter(
            x=ooc_df["timestamp"],
            y=ooc_df[ycol],
            mode="markers",
            marker=dict(size=9, color="red"),
            name="UCL/LCL 초과"
        )

    fig.update_layout(
        title=dict(text=title, x=0.02, xanchor="left", font=dict(size=14)),
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=12),
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.06)"),
        hoverlabel=dict(
            font=dict(size=16, color="#111827"),
            bgcolor="#E5E7EB",
            bordercolor="#9CA3AF",
        ),
        dragmode="pan",
    )
    # 기본 뷰는 최근 1시간, 드래그하면 과거 구간 탐색 가능
    if "timestamp" in df_plot.columns and not df_plot.empty:
        x_max = df_plot["timestamp"].max()
        x_min = x_max - pd.Timedelta(hours=1)
        fig.update_xaxes(range=[x_min, x_max], rangeslider_visible=False)
    # 공정 변수 모니터링 차트의 Y축 제목(라벨) 제거
    fig.update_yaxes(title_text=None)
    fig.update_traces(line=dict(width=3))
    return fig


# 반경별 결함 밀도 곡선 생성
def make_radial_density_curve(df_in: pd.DataFrame, bins=12, radius_col="RADIUS", wafer_radius=WAFER_RADIUS):
    """
    x=諛섍꼍, y=defect density(怨좊━硫댁쟻??媛쒖닔)
    """
    if df_in is None or df_in.empty:
        return None
    if radius_col not in df_in.columns:
        return None
    tmp = df_in.copy()
    tmp[radius_col] = pd.to_numeric(tmp[radius_col], errors="coerce")
    tmp = tmp.dropna(subset=[radius_col])
    if tmp.empty:
        return None

    r = tmp[radius_col].clip(lower=0, upper=wafer_radius).values
    edges = np.linspace(0, wafer_radius, bins + 1)
    tmp["r_bin"] = pd.cut(r, bins=edges, include_lowest=True)

    counts = tmp.groupby("r_bin").size().reset_index(name="defect_count")
    left = edges[:-1]
    right = edges[1:]

    ring_area = np.pi * (right**2 - left**2)
    ring_area = np.where(ring_area == 0, 1, ring_area)

    counts["r_center"] = (left + right) / 2
    counts["defect_density"] = counts["defect_count"].values / ring_area

    fig = px.line(
        counts,
        x="r_center",
        y="defect_density",
        markers=True,
        labels={"r_center": "Radius", "defect_density": "Defect density"},
        height=260
    )
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10))
    return fig

# 결함 맵 원천 데이터 로드/정규화
# =========================================================
@st.cache_data(show_spinner=False)
def load_defect_map():
    if not DEFECT_MAP_PATH.exists():
        raise FileNotFoundError(f"defect map not found: {DEFECT_MAP_PATH}")
    df = safe_read_csv(DEFECT_MAP_PATH)

    rename = {
        "공정명": "Step_desc",
        "공정단계": "Step",
        "배치번호": "Lot",
        "웨이퍼위치": "Slot No",
        "검사순번": "Defect No",
        "결함유형": "Class",
        "불량여부": "IS_DEFECT",
        "가로길이": "SIZE_X",
        "세로길이": "SIZE_Y",
        "검출면적": "DEFECT_AREA",
        "직경크기": "SIZE_D",
        "신호강도": "INTENSITY",
        "신호극성": "POLARITY",
        "에너지값": "ENERGY_PARAM",
        "기준점오프셋": "MDAT_OFFSET",
        "명도편차": "MDAT_GL",
        "잡음정도": "MDAT_NOISE",
        "중심거리": "RADIUS",
        "방향각도": "ANGLE",
        "정렬정도": "ALIGNRATIO",
        "점형지수": "SPOTLIKENESS",
        "패치잡음": "PATCHNOISE",
        "상대강도": "RELATIVEMAGNITUDE",
        "활성지수": "ACTIVERATIO",
        "패치결함신호": "PATCHDEFECTSIGNAL",
        "wafer_x": "X",
        "wafer_y": "Y",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    if "Step_desc" in df.columns:
        df["Step_desc"] = df["Step_desc"].astype(str)
        df = df[df["Step_desc"].str.upper().str.contains("CBCMP", na=False)].copy()

    if "Lot" in df.columns:
        df["Lot_norm"] = df["Lot"].map(norm_lot)
    else:
        df["Lot"] = "UNKNOWN"
        df["Lot_norm"] = "UNKNOWN"

    if "Slot No" not in df.columns:
        df["Slot No"] = 0
    df["Wafer_ID"] = df["Step_desc"].astype(str) + "_" + df["Lot_norm"].astype(str) + "_" + df["Slot No"].astype(str)

    for c in ["X", "Y", "RADIUS", "ANGLE", "Class"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if "IS_DEFECT" in df.columns:
        # 불량여부 문자열을 1(실제 결함) / 0(가성 결함)로 정규화
        defect_map = {
            "불량": "1", "정상": "0", "Y": "1", "N": "0",
            "REAL": "1", "FALSE": "0", "PSEUDO": "0", "FAKE": "0"
        }
        raw_flag = df["IS_DEFECT"].astype(str).str.strip().str.upper()
        mapped = raw_flag.replace(defect_map)
        # 알 수 없는 값은 결함(1)으로 보수 처리
        df["IS_DEFECT"] = pd.to_numeric(mapped, errors="coerce").fillna(1).astype(int)
    else:
        df["IS_DEFECT"] = 1

    return df

@st.cache_data(show_spinner=False)
def load_timeseries():
    if not TS_PATH.exists():
        raise FileNotFoundError(f"timeseries not found: {TS_PATH}")
    ts = safe_read_csv(TS_PATH)
    ts["Lot_norm"] = ts["배치번호"].map(norm_lot)
    ts["timestamp"] = pd.to_datetime(ts["timestamp"], errors="coerce")
    ts = ts.dropna(subset=["timestamp"]).sort_values("timestamp")
    return ts

@st.cache_data(show_spinner=False)
def load_false_defect_source():
    """가성 결함 비율 산출용 원본(한글) 데이터 로드."""
    if not SOURCE_KOR_PATH.exists():
        return pd.DataFrame()
    src = safe_read_csv(SOURCE_KOR_PATH)
    if "배치번호" in src.columns:
        src["Lot_norm"] = src["배치번호"].map(norm_lot)
    else:
        src["Lot_norm"] = ""
    if "공정명" in src.columns:
        src["공정명"] = src["공정명"].astype(str)
    if "불량여부" in src.columns:
        src["불량여부_norm"] = src["불량여부"].astype(str).str.strip().str.upper()
    return src

def calc_false_defect_ratio(selected_lot_norm: str) -> float:
    """선택 Lot 기준 가성 결함 비율(%) 계산."""
    src = load_false_defect_source()
    if src.empty:
        return 0.0

    view = src.copy()
    # CBCMP 데이터가 있으면 우선 사용
    if "공정명" in view.columns:
        cbcmp_view = view[view["공정명"].str.upper().str.contains("CBCMP", na=False)]
        if not cbcmp_view.empty:
            view = cbcmp_view

    if selected_lot_norm != "전체" and "Lot_norm" in view.columns:
        lot_view = view[view["Lot_norm"] == selected_lot_norm]
        if not lot_view.empty:
            view = lot_view

    if len(view) == 0:
        return 0.0

    if "불량여부_norm" in view.columns:
        is_false = view["불량여부_norm"].isin(["FALSE", "0", "N", "가성", "PSEUDO", "FAKE"])
        return float(is_false.mean() * 100.0)

    if "결함유형" in view.columns:
        cls = pd.to_numeric(view["결함유형"], errors="coerce")
        return float((cls == 9).mean() * 100.0)

    return 0.0

# 운영 고정값(사이드바 제거 버전)
# =========================================================
# 사이드바 제거: 운영 고정값
severity_threshold = 65
spc_scope = "선택 Lot"
k_sigma = 2.5

# 메인 데이터 준비(결함맵 + 시계열 + Lot 목록)
# =========================================================
df = load_defect_map()
ts = load_timeseries()

lot_def = sorted(df["Lot_norm"].dropna().unique().tolist())
lot_ts  = sorted(ts["Lot_norm"].dropna().unique().tolist())
lot_union = sorted(list(dict.fromkeys(lot_def + lot_ts)))
lot_options = ["전체"] + lot_union

if "selected_lot_norm" not in st.session_state:
    st.session_state["selected_lot_norm"] = "전체"

# 좌측(분석) / 우측(설비) 메인 레이아웃
# =========================================================
left, right = st.columns([0.65, 0.35], gap="large")

with left:
    # 제목 왼쪽 정렬, ISO 텍스트 오른쪽 정렬 (두께 normal, 크기 20px)
    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: flex-end; padding-top: 15px; margin-bottom: -15px;">
            <div>
                <h1 style="margin-bottom: 0; padding-bottom: 0; font-size: 2.25rem; font-weight: 700; color: #111827;">CBCMP 공정 모니터링</h1>
                <p style="color: #6B7280; font-size: 14px; margin-top: 5px; margin-bottom: 0;">CBCMP 공정 | 결함 분포/위험 웨이퍼 배치 알림/프로파일 모니터링</p>
            </div>
            <div style="text-align: right; color: #9CA3AF; font-size: 20px; font-weight: normal; line-height: 1.4; padding-bottom: 5px;">
                ISO 26262
            </div>
        </div>
    """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # ---------------------------------------------------------
    wafer_diameter_cm = 30.0
    wafer_radius_cm = wafer_diameter_cm / 2
    wafer_area_cm2 = np.pi * (wafer_radius_cm ** 2)

    default_base_area_cm2 = 1.0
    default_chip_side_cm = np.sqrt(default_base_area_cm2)
    default_scribe_line_cm = 0.008
    default_eff_chip_area_cm2 = (default_chip_side_cm + default_scribe_line_cm) ** 2

    raw_die_count = wafer_area_cm2 / default_eff_chip_area_cm2
    edge_loss = (np.pi * wafer_diameter_cm) / np.sqrt(2 * default_eff_chip_area_cm2)
    total_dpw = max(int(raw_die_count - edge_loss), 1)

    # 웨이퍼 단위 요약 테이블 생성
    wafer_summary = df.groupby(["Wafer_ID", "Lot_norm"]).size().reset_index(name="결함수")
    wafer_summary["Defect_Density"] = wafer_summary["결함수"] / wafer_area_cm2
    wafer_summary["상태 (Severity)"] = np.where(
        wafer_summary["결함수"] >= severity_threshold, "🔴 HIGH", "🟢 NORMAL"
    )
    wafer_summary = wafer_summary.sort_values("결함수", ascending=False).reset_index(drop=True)

    high_defect_wafers_all = wafer_summary[wafer_summary["결함수"] >= severity_threshold].copy()

    total_defects_all = len(df)

    st.markdown("---")

    kpi_container = st.container()

    # 상단 1행: 좌측 알림 / 우측 조회조건+테이블
    row1_left, row1_right = st.columns([1.2, 2.5], gap="large")

    # ---------------------------------------------------------
    # ---------------------------------------------------------
    with row1_right:
        st.markdown("**조회 조건 설정**")

        col_lot, col_die = st.columns(2)

        if "lot_selectbox" not in st.session_state:
            st.session_state["lot_selectbox"] = st.session_state.get("selected_lot_norm", "전체")

        with col_lot:
            selected_lot_norm = st.selectbox(
                "배치번호(Lot):",
                options=lot_options,
                index=lot_options.index(st.session_state["lot_selectbox"])
                if st.session_state["lot_selectbox"] in lot_options else 0,
                key="lot_selectbox"
            )

        st.session_state["selected_lot_norm"] = selected_lot_norm

        with col_die:
            die_size_option = st.selectbox("다이 사이즈 선택:", ["100 mm²", "130 mm²"])

        base_area_cm2 = 1.0 if die_size_option == "100 mm²" else 1.3
        chip_side_cm = np.sqrt(base_area_cm2)
        scribe_line_cm = 0.008
        eff_chip_area_cm2 = (chip_side_cm + scribe_line_cm) ** 2

        raw_die_count = wafer_area_cm2 / eff_chip_area_cm2
        edge_loss = (np.pi * wafer_diameter_cm) / np.sqrt(2 * eff_chip_area_cm2)
        total_dpw = max(int(raw_die_count - edge_loss), 1)

        wafer_summary["Yield_Poisson"] = np.exp(
            -eff_chip_area_cm2 * wafer_summary["Defect_Density"]
        ) * 100

        wafer_summary["Expected_Good_Dies"] = (
            total_dpw * wafer_summary["Yield_Poisson"] / 100
        ).round().astype(int)

        st.markdown("**Lot Data Breakdown (웨이퍼ID를 클릭하세요)**")

        display_summary = (
            wafer_summary[wafer_summary["Lot_norm"] == selected_lot_norm].reset_index(drop=True)
            if selected_lot_norm != "전체"
            else wafer_summary.copy()
        )

        event = st.dataframe(
            display_summary[["Wafer_ID", "상태 (Severity)", "결함수"]],
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Wafer_ID": st.column_config.TextColumn("웨이퍼 ID"),
                "상태 (Severity)": st.column_config.TextColumn("상태"),
                "결함수": st.column_config.ProgressColumn(
                    "결함수",
                    format="%d 건",
                    min_value=0,
                    max_value=int(wafer_summary["결함수"].max()) if not wafer_summary.empty else 100
                )
            },
            height=270,
            use_container_width=True
        )

    # 테이블 선택값을 기준으로 필터 데이터 결정
    selected_wafer_id = None

    if event.selection.rows and not display_summary.empty:
        selected_wafer_id = display_summary.iloc[event.selection.rows[0]]["Wafer_ID"]
        filtered_df = df[df["Wafer_ID"] == selected_wafer_id].copy()
        chart_title_suffix = f" ({selected_wafer_id})"
    else:
        if selected_lot_norm != "전체":
            filtered_df = df[df["Lot_norm"] == selected_lot_norm].copy()
            chart_title_suffix = f" (Lot: {selected_lot_norm})"
        else:
            filtered_df = df.copy()
            chart_title_suffix = " (CBCMP 전체)"

    filtered_df = filtered_df.reset_index(drop=True)
    filtered_df["Defect_ID"] = filtered_df.index

    # KPI 계산(결함수/수율/밀도/경고 웨이퍼)
    if filtered_df.empty:
        kpi_total_defects = 0
        kpi_density = 0.0
        yield_rate = 0.0
        avg_good_dies = 0.0
    else:
        wafer_counts = filtered_df.groupby("Wafer_ID").size()
        wafer_density = wafer_counts / wafer_area_cm2
        kpi_total_defects = int(wafer_counts.sum())

        if selected_wafer_id is not None and selected_wafer_id in wafer_density.index:
            kpi_density = float(wafer_density.loc[selected_wafer_id])
            yield_rate = float(
                wafer_summary.loc[wafer_summary["Wafer_ID"] == selected_wafer_id, "Yield_Poisson"].iloc[0]
            )
            avg_good_dies = float(
                wafer_summary.loc[wafer_summary["Wafer_ID"] == selected_wafer_id, "Expected_Good_Dies"].iloc[0]
            )
        else:
            kpi_density = float(wafer_density.mean())

            if selected_lot_norm != "전체":
                lot_view = wafer_summary[wafer_summary["Lot_norm"] == selected_lot_norm]
                yield_rate = float(lot_view["Yield_Poisson"].mean()) if not lot_view.empty else 0.0
                avg_good_dies = float(lot_view["Expected_Good_Dies"].mean()) if not lot_view.empty else 0.0
            else:
                yield_rate = float(wafer_summary["Yield_Poisson"].mean()) if not wafer_summary.empty else 0.0
                avg_good_dies = float(wafer_summary["Expected_Good_Dies"].mean()) if not wafer_summary.empty else 0.0

    if selected_wafer_id is not None:
        wafer_lot = wafer_summary.loc[wafer_summary["Wafer_ID"] == selected_wafer_id, "Lot_norm"]
        wafer_lot = str(wafer_lot.iloc[0]) if not wafer_lot.empty else "전체"
        warn_view = high_defect_wafers_all[high_defect_wafers_all["Lot_norm"] == wafer_lot]
        warn_count = len(warn_view)
    else:
        if selected_lot_norm == "전체":
            warn_count = len(high_defect_wafers_all)
        else:
            warn_view = high_defect_wafers_all[high_defect_wafers_all["Lot_norm"] == selected_lot_norm]
            warn_count = len(warn_view)

    with kpi_container:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("결함 수", f"{kpi_total_defects:,} 건")
        k2.metric("예상 수율", f"{yield_rate:.2f} %")
        k3.metric("Defect Density", f"{kpi_density:.5f} ea/cm²")
        k4.metric("경고 웨이퍼 수", f"{warn_count} 장")

    st.markdown("---")

    # ---------------------------------------------------------
    # ---------------------------------------------------------
    with row1_left:
        st.write("")
        st.markdown("""
        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;'>
            <div style='font-weight: 800; font-size: 16px; color: #1F2937;'>
                <span style='margin-right: 8px;'>🚨</span> 실시간 알림 내역
            </div>
            <div style='color: #9CA3AF; font-size: 13px;'>방금 전</div>
        </div>
        """, unsafe_allow_html=True)

        # 실시간 알림 영역(결함 다량 + 공정 변수 이상)
        alert_container = st.container(height=315, border=True)
        with alert_container:
            alert_count = 0
            def set_selected_lot(target_lot: str):
                st.session_state["lot_selectbox"] = target_lot
                st.session_state["selected_lot_norm"] = target_lot

            if not high_defect_wafers_all.empty:
                lot_warning_counts = (
                    high_defect_wafers_all.groupby("Lot_norm").size()
                    .reset_index(name="경고웨이퍼수")
                    .sort_values("경고웨이퍼수", ascending=False)
                )

                for idx, row_warn in lot_warning_counts.iterrows():
                    lot_num = row_warn["Lot_norm"]
                    warn_cnt = int(row_warn["경고웨이퍼수"])
                    alert_count += 1

                    a_col1, a_col2, a_col3 = st.columns([1, 4, 1.5], vertical_alignment="center")
                    with a_col1:
                        st.markdown(
                            f"<div style='width: 32px; height: 32px; background-color: #FA5C5C; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-top: 5px;'>{warn_cnt}</div>",
                            unsafe_allow_html=True
                        )
                    with a_col2:
                        st.markdown(
                            f"<div style='font-weight: bold; font-size: 13px; margin-bottom: 2px; color: #374151;'>결함 다량 발생 감지</div><div style='font-size: 12px; color: #6B7280;'>배치: <b>{lot_num}</b> | 위험 {warn_cnt}장</div>",
                            unsafe_allow_html=True
                        )
                    with a_col3:
                        st.button(
                            "조회",
                            key=f"btn_def_{lot_num}",
                            on_click=set_selected_lot,
                            args=(lot_num,),
                            use_container_width=True
                        )

                    st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #F3F4F6;'>", unsafe_allow_html=True)

            # 공정 변수 이상 탐지 대상 컬럼 정의
            metric_specs = [
                ("slurry_flow_ml_min", "S", "Slurry", "mL/min"),
                ("pressure_middle_psi", "P", "Pressure", "psi"),
                ("removal_rate_nm_min", "R", "Removal", "nm/min"),
                ("Temp", "T", "Temperature", "°C"),
                ("temperature", "T", "Temperature", "°C"),
                ("chamber_temp", "T", "Temperature", "°C"),
            ]
            abnormal_map = {
                "SLURRY": ("S", "Slurry Flow", "slurry_flow_ml_min", "mL/min"),
                "PRESSURE": ("P", "Middle Pressure", "pressure_middle_psi", "psi"),
                "RR_PAD": ("R", "Removal Rate", "removal_rate_nm_min", "nm/min"),
                "TEMP": ("T", "Temperature", "Temp", "°C"),
                "TEMPERATURE": ("T", "Temperature", "temperature", "°C"),
                "CHAMBER_TEMP": ("T", "Temperature", "chamber_temp", "°C"),
            }
            alert_lots = lot_union if selected_lot_norm == "전체" else [selected_lot_norm]

            for lot_num in alert_lots:
                lot_ts = ts[ts["Lot_norm"] == lot_num].sort_values("timestamp").copy()
                if lot_ts.empty:
                    continue

                anomalies = []
                # 1순위: 시계열의 이상 플래그 컬럼(is_abnormal/abnormal_type) 사용
                if {"is_abnormal", "abnormal_type"}.issubset(lot_ts.columns):
                    abn_mask = pd.to_numeric(lot_ts["is_abnormal"], errors="coerce").fillna(0) > 0
                    abn_rows = lot_ts.loc[abn_mask]
                    if not abn_rows.empty:
                        latest_abn = abn_rows.iloc[-1]
                        abn_types = [t.strip().upper() for t in str(latest_abn.get("abnormal_type", "")).split(",") if t.strip() and t.strip().upper() != "NORMAL"]
                        for abn in abn_types:
                            if abn not in abnormal_map:
                                continue
                            initial, label, col, unit = abnormal_map[abn]
                            if col not in lot_ts.columns:
                                continue
                            val = pd.to_numeric(pd.Series([latest_abn.get(col)]), errors="coerce").iloc[0]
                            if pd.notna(val):
                                anomalies.append((initial, label, float(val), unit))

                # 2순위: 플래그가 없으면 SPC 기준(UCL/LCL)으로 fallback
                if not anomalies:
                    for col, initial, label, unit in metric_specs:
                        if col not in lot_ts.columns:
                            continue
                        series = pd.to_numeric(lot_ts[col], errors="coerce").dropna()
                        if len(series) < 5:
                            continue
                        latest_val = float(series.iloc[-1])
                        _, ucl, lcl = compute_ucl_lcl(series, k=float(k_sigma))
                        if (ucl is not None and np.isfinite(ucl) and latest_val > ucl) or (
                            lcl is not None and np.isfinite(lcl) and latest_val < lcl
                        ):
                            anomalies.append((initial, label, latest_val, unit))

                if anomalies:
                    dedup = {}
                    for initial, label, value, unit in anomalies:
                        dedup[label] = (initial, label, value, unit)
                    anomalies = list(dedup.values())

                if len(anomalies) == 1:
                    alert_count += 1
                    initial, label, value, unit = anomalies[0]
                    a_col1, a_col2, a_col3 = st.columns([1, 4, 1.5], vertical_alignment="center")
                    with a_col1:
                        st.markdown(
                            f"<div style='width: 32px; height: 32px; background-color: #EF4444; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-top: 5px;'>{initial}</div>",
                            unsafe_allow_html=True
                        )
                    with a_col2:
                        st.markdown(
                            f"<div style='font-weight: bold; font-size: 13px; margin-bottom: 2px; color: #374151;'>공정 변수 이상 감지</div><div style='font-size: 12px; color: #6B7280;'>배치: <b>{lot_num}</b> | {label}: <span style='color:#EF4444; font-weight:bold;'>{value:.2f} {unit}</span></div>",
                            unsafe_allow_html=True
                        )
                    with a_col3:
                        st.button(
                            "조회",
                            key=f"btn_ts_{lot_num}_{initial}",
                            on_click=set_selected_lot,
                            args=(lot_num,),
                            use_container_width=True
                        )
                    st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #F3F4F6;'>", unsafe_allow_html=True)
                elif len(anomalies) >= 2:
                    alert_count += 1
                    detail_str = ", ".join(
                        [f"{label}: <span style='color:#EF4444; font-weight:bold;'>{value:.2f} {unit}</span>" for _, label, value, unit in anomalies]
                    )
                    a_col1, a_col2, a_col3 = st.columns([1, 4, 1.5], vertical_alignment="center")
                    with a_col1:
                        st.markdown(
                            f"<div style='width: 32px; height: 32px; background-color: #EF4444; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight:bold; margin-top: 5px;'>{len(anomalies)}</div>",
                            unsafe_allow_html=True
                        )
                    with a_col2:
                        st.markdown(
                            f"<div style='font-weight: bold; font-size: 13px; margin-bottom: 2px; color: #374151;'>공정 변수 {len(anomalies)}건 동시 이탈</div><div style='font-size: 12px; color: #6B7280;'>배치: <b>{lot_num}</b> | {detail_str}</div>",
                            unsafe_allow_html=True
                        )
                    with a_col3:
                        st.button(
                            "조회",
                            key=f"btn_ts_{lot_num}_multi",
                            on_click=set_selected_lot,
                            args=(lot_num,),
                            use_container_width=True
                        )
                    st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #F3F4F6;'>", unsafe_allow_html=True)

            if alert_count == 0:
                st.markdown(
                    "<div style='display:flex; align-items:center; justify-content:center; height:100%; color:#10B981; font-weight:bold;'>현재 공정에 발생한 경고 알림이 없습니다.</div>",
                    unsafe_allow_html=True
                )

    # ---------------------------------------------------------
    # ---------------------------------------------------------
    if not filtered_df.empty:
        filtered_df["Class_str"] = filtered_df["Class"].astype("Int64").astype(str)
        unique_classes = sorted(filtered_df["Class"].dropna().unique().tolist())
        palette = px.colors.qualitative.Plotly
        color_map = {str(cls): palette[i % len(palette)] for i, cls in enumerate(unique_classes)}
    else:
        color_map = {}

    st.markdown("<br>", unsafe_allow_html=True)

    # ---------------------------------------------------------
    # ---------------------------------------------------------
    st.markdown(
        f"<div style='font-weight:800; font-size:22px; color:#1E3A8A; margin:2px 0 10px 0;'>🔎 결함 심층 분석 {chart_title_suffix}</div>",
        unsafe_allow_html=True,
    )
    # 하단 결함 심층 분석(맵/레이더/유형 통계)
    block = st.container(border=True)
    with block:
        row2_left, row2_mid, row2_right = st.columns([1, 1, 1], gap="large")

        with row2_left:
            st.markdown(f"**결함 분포 맵 {chart_title_suffix}**")
            if not filtered_df.empty and {"X", "Y"}.issubset(filtered_df.columns):
                fig_map = px.scatter(
                    filtered_df, x="X", y="Y", color="Class_str",
                    hover_data=["Wafer_ID", "Lot_norm"],
                    custom_data=["Defect_ID"],
                    color_discrete_map=color_map,
                    labels={"Class_str": "결함 유형"},
                    height=340
                )
                fig_map.add_shape(
                    type="circle",
                    x0=-WAFER_RADIUS, y0=-WAFER_RADIUS,
                    x1=WAFER_RADIUS, y1=WAFER_RADIUS,
                    line_color="#9CA3AF", line_width=2
                )
                fig_map.update_layout(
                    xaxis=dict(visible=False, range=[-WAFER_RADIUS * 1.1, WAFER_RADIUS * 1.1]),
                    yaxis=dict(visible=False, range=[-WAFER_RADIUS * 1.1, WAFER_RADIUS * 1.1], scaleanchor="x", scaleratio=1),
                    margin=dict(l=0, r=0, t=10, b=0),
                    legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
                )
                map_event = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun", selection_mode="points")
            else:
                st.info("해당 조건의 맵 데이터가 없습니다.")
                map_event = None

        radar_features = [
            ("ALIGNRATIO", "정렬정도"),
            ("SPOTLIKENESS", "점형지수"),
            ("RELATIVEMAGNITUDE", "상대강도"),
            ("PATCHNOISE", "패치잡음"),
            ("INTENSITY", "신호강도"),
            ("DEFECT_AREA", "면적"),
        ]

        with row2_mid:
            st.markdown(f"**결함 특성화 지표 {chart_title_suffix}**")
            if filtered_df.empty:
                st.info("표시할 데이터가 없습니다.")
            else:
                feats = [(c, k) for c, k in radar_features if c in filtered_df.columns]
                cols = [c for c, _ in feats]
                labels = [k for _, k in feats]

                if map_event and getattr(map_event, "selection", None) and map_event.selection.points:
                    selected_defect_id = map_event.selection.points[0]["customdata"][0]
                    sel = filtered_df.loc[filtered_df["Defect_ID"] == selected_defect_id, cols]
                    vec = sel.iloc[0] if not sel.empty else filtered_df[cols].mean()
                    st.caption("선택된 단일 결함 프로파일")
                else:
                    vec = filtered_df[cols].mean()
                    # st.caption("선택 범위 평균 결함 프로파일")

                mins = filtered_df[cols].min()
                maxs = filtered_df[cols].max()
                denom = (maxs - mins).replace(0, np.nan)
                norm = ((vec - mins) / denom).fillna(0.5).clip(0, 1).tolist()

                fig_radar = go.Figure(go.Scatterpolar(
                    r=norm + [norm[0]],
                    theta=labels + [labels[0]],
                    fill="toself",
                    line_color="#60A5FA",
                    fillcolor="rgba(96,165,250,0.35)"
                ))
                fig_radar.update_layout(
                    polar=dict(radialaxis=dict(visible=True, showticklabels=False, ticks="", range=[0, 1])),
                    showlegend=False,
                    margin=dict(l=25, r=25, t=25, b=25),
                    height=340,
                    hoverlabel=dict(font=dict(size=16), bgcolor="#E5E7EB")
                )
                st.plotly_chart(fig_radar, use_container_width=True)

        with row2_right:
            st.markdown(f"**결함 유형 통계 {chart_title_suffix}**")
            if filtered_df.empty or "Class" not in filtered_df.columns:
                st.info("차트에 표시할 데이터가 없습니다.")
            else:
                class_counts = filtered_df["Class"].value_counts().reset_index()
                class_counts.columns = ["Class", "Count"]
                class_counts["Class_str"] = class_counts["Class"].astype("Int64").astype(str)
                class_counts = class_counts.sort_values("Count", ascending=False).reset_index(drop=True)
                total_count = class_counts["Count"].sum()
                class_counts["Percent"] = (class_counts["Count"] / total_count * 100).round(1) if total_count > 0 else 0.0

                fig_donut = go.Figure(go.Pie(
                    labels=class_counts["Class_str"],
                    values=class_counts["Count"],
                    hole=0.65,
                    textinfo="none",
                    hovertemplate="유형 %{label}<br>%{value}건 (%{percent})<extra></extra>",
                    marker=dict(colors=[color_map.get(cls, "#999999") for cls in class_counts["Class_str"]])
                ))
                fig_donut.update_layout(
                    showlegend=False,
                    margin=dict(l=10, r=10, t=10, b=10),
                    height=240,
                    hoverlabel=dict(font=dict(size=16), bgcolor="#E5E7EB"),
                    annotations=[dict(
                        text=f"{class_counts.iloc[0]['Percent']:.0f}%",
                        x=0.5, y=0.5, font_size=22, showarrow=False
                    )]
                )
                st.plotly_chart(fig_donut, use_container_width=True)

                legend_html = "<div style='display:flex;flex-direction:column;justify-content:center;padding:0 6px 6px 6px;'>"
                for _, row in class_counts.head(4).iterrows():
                    cls_str = row["Class_str"]
                    color = color_map.get(cls_str, "#999999")
                    legend_html += (
                        "<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;'>"
                        "<div style='display:flex;align-items:center;'>"
                        f"<span style='color:{color};font-size:16px;margin-right:8px;'>●</span>"
                        f"<span style='color:#4B5563;font-size:13px;font-weight:700;'>유형 {cls_str}</span>"
                        "</div>"
                        f"<div style='font-weight:800;color:#111827;font-size:13px;'>{row['Percent']:.0f}%</div>"
                        "</div>"
                    )
                legend_html += "</div>"
                st.markdown(legend_html, unsafe_allow_html=True)

    # 보조 지표: 반경별 결함 밀도
    with st.expander("📈 CBCMP 반경별 결함 분포"):
        fig_radial = make_radial_density_curve(
            filtered_df, bins=12, radius_col="RADIUS", wafer_radius=WAFER_RADIUS
        )
        if fig_radial is None:
            st.info("RADIUS 데이터가 없거나 반경 분포를 계산할 수 없습니다.")
        else:
            st.plotly_chart(fig_radial, use_container_width=True)


                    


# 우측 패널에서 사용하는 flow 이미지
FLOW_IMG_PATH = BASE_DIR / "FLOW_IMG_PATH.png"

with right:
    # 우측 상단 상태 카드(PC_tab2 스타일)
    lot_sel = st.session_state.get("selected_lot_norm", "전체")
    ts_view = ts.copy() if lot_sel == "전체" else ts[ts["Lot_norm"] == lot_sel].copy()
    summary_wafer = len(df["Wafer_ID"].unique())
    priority_lot = (
        high_defect_wafers_all.groupby("Lot_norm").size().sort_values(ascending=False).index[0]
        if not high_defect_wafers_all.empty else (lot_sel if lot_sel != "전체" else "-")
    )
    warn_cnt = int(len(high_defect_wafers_all))
    status_indicator = "🟢" if warn_cnt == 0 else "🔴"
    false_defect_ratio = calc_false_defect_ratio(lot_sel)

    card_html = f"""<div class="manager-card" style="margin-top: 12px; margin-bottom: 12px; padding: 12px 20px;">
<div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.2); padding-bottom: 10px; margin-bottom: 10px;">
<div style="display: flex; align-items: center; gap: 12px;">
<div style="width: 50px; height: 50px; border-radius: 50%; border: 3px solid #60A5FA; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: bold; position: relative; background-color: #1E3A8A;">
CMP<div style="position: absolute; top: -6px; right: -6px; font-size: 14px;">{status_indicator}</div>
</div>
<div>
<div style="font-size: 12px; color: #93C5FD; margin-bottom: 2px;">생산 웨이퍼</div>
<div style="font-size: 18px; font-weight: bold;">{summary_wafer:,} 장</div>
</div>
</div>
<div style="text-align: right;"><div style="font-size: 16px; font-weight: bold;">담당자 : 신소망</div></div>
</div>
<div style="display: flex; justify-content: space-between; align-items: flex-end;">
<div><div style="font-size: 11px; color: #93C5FD; margin-bottom: 2px;">가성 결함</div><div style="font-size: 15px; font-weight: bold;">{false_defect_ratio:.1f}%</div></div>
<div style="text-align: right;"><div style="font-size: 11px; color: #93C5FD; margin-bottom: 2px;">우선 점검 배치</div><div style="font-size: 15px; font-weight: bold; color: #FCD34D;">{priority_lot}</div></div>
</div>
</div>"""
    st.markdown(card_html, unsafe_allow_html=True)

    st.markdown(
        f"<h4 style='color: #1E3A8A; margin-top: 15px; margin-bottom: 10px; font-weight: bold;'>설비 변수 모니터링 {f'(Lot: {lot_sel})' if lot_sel != '전체' else ''}</h4>",
        unsafe_allow_html=True,
    )

    if ts_view.empty:
        st.warning("선택한 Lot에 해당하는 설비 시계열 데이터가 없습니다.")
    else:
        ts_view = ts_view.sort_values("timestamp")
        # 전체 데이터를 유지해 드래그 시 과거 시간대도 볼 수 있게 함
        ts_plot = ts_view.copy()
        last = ts_plot.iloc[-1]

        # 우측 본문 1: 공정 이미지 + 압력존/flow
        with st.container(border=True):
            colL, colR = st.columns([1, 1.02], gap="small")

            with colL:
                if EQUIP_IMG_PATH.exists():
                    kpi_img = render_cbcmp_kpi_overlay(last.to_dict(), EQUIP_IMG_PATH)
                    st.image(kpi_img, width=300)
                else:
                    st.info("설비 이미지 파일이 없습니다. (EQUIP_IMG_PATH 확인)")

            with colR:
                st.markdown(
                    pressure_zone_panel(
                        last.get("pressure_center_psi", np.nan),
                        last.get("pressure_middle_psi", np.nan),
                        last.get("pressure_edge_psi", np.nan),
                    ),
                    unsafe_allow_html=True,
                )
                st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
                if FLOW_IMG_PATH.exists():
                    st.image(str(FLOW_IMG_PATH), width=280)
                else:
                    st.info("유량분포 이미지 파일이 없습니다. (FLOW_IMG_PATH 확인)")

        # 우측 본문 2: 주요 SPC 시계열 2개
        st.markdown(
            "<h4 style='color: #1E3A8A; margin-top: 20px; margin-bottom: 10px; font-weight: bold;'>공정 변수 모니터링</h4>",
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            fig_flow = plot_spc_timeseries(
                df_plot=ts_plot,
                ycol="slurry_flow_ml_min",
                title="Slurry Flow (mL/min)",
                y_label="Slurry Flow (mL/min)",
                spc_df=ts_view,
                k=float(k_sigma),
                height=180,
            )
            st.plotly_chart(fig_flow, use_container_width=True, config={"displayModeBar": False})

            st.markdown("<div style='margin-top: -10px;'></div>", unsafe_allow_html=True)
            fig_rr = plot_spc_timeseries(
                df_plot=ts_plot,
                ycol="removal_rate_nm_min",
                title="Removal Rate (MRR) (nm/min)",
                y_label="Removal Rate (nm/min)",
                spc_df=ts_view,
                k=float(k_sigma),
                height=180,
            )
            st.plotly_chart(fig_rr, use_container_width=True, config={"displayModeBar": False})

        # 우측 본문 3: 작업 진행률/설비 부담도
        st.markdown(
            "<h4 style='color: #1E3A8A; margin-top: 25px; margin-bottom: 10px; font-weight: bold;'>작업 진행 및 장비수명</h4>",
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            day_progress = ((last["timestamp"].hour * 60) + last["timestamp"].minute) / 1440 * 100
            if "is_abnormal" in ts_plot.columns:
                abn_series = pd.to_numeric(ts_plot["is_abnormal"], errors="coerce").fillna(0)
            else:
                abn_series = pd.Series([0.0])
            equip_load = float(np.clip(35 + abn_series.mean() * 55, 10, 95))

            st.caption(f"<span style='font-size: 14px; color: #4B5563; font-weight: bold;'>작업 진행률 ({day_progress:.0f}%)</span>", unsafe_allow_html=True)
            st.progress(day_progress / 100)

            st.caption(f"<span style='font-size: 14px; color: #4B5563; font-weight: bold;'>장비 수명 ({equip_load:.0f}%)</span>", unsafe_allow_html=True)
            st.progress(equip_load / 100)

            st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
            if equip_load >= 85:
                st.error("**설비 교체 필요**")
            elif equip_load >= 70:
                st.warning("**점검 필요**")
            else:
                st.success("**정상 가동 중**")






