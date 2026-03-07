import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import base64
import os
import math
import uuid
import random
from pathlib import Path
from datetime import datetime, timedelta

# ==========================================
# 1. 기본 설정 및 데이터 로드
# ==========================================
st.set_page_config(page_title="FAB 공정 OVERVIEW", layout="wide", initial_sidebar_state="expanded")

@st.cache_data
def get_image_base64(filename: str):
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        img_path = os.path.join(current_dir, filename)
        p = Path(img_path)
        if p.exists():
            with open(img_path, "rb") as img_file:
                return base64.b64encode(img_file.read()).decode()
    except Exception:
        pass
    return ""

@st.cache_data
def load_and_prep_data():
    try:
        df_raw = pd.read_csv('반도체_결함_데이터_한글.csv')
    except FileNotFoundError:
        return pd.DataFrame() 

    KOR_TO_ENG = {
        '공정단계': 'Step', '공정명': 'Step_desc', '배치번호': 'Lot',
        '웨이퍼위치': 'Slot No', '검사순번': 'Defect No', '결함유형': 'Class',
        '불량여부': 'IS_DEFECT', '가로길이': 'SIZE_X', '세로길이': 'SIZE_Y',
        '중심거리': 'RADIUS', '방향각도': 'ANGLE'
    }
    
    df = df_raw.rename(columns=KOR_TO_ENG).copy()
    if 'IS_DEFECT' in df.columns:
        df['IS_DEFECT'] = df['IS_DEFECT'].astype(str).str.strip().replace({'불량': '1', '정상': '0', 'Y': '1', 'N': '0'})
        df['IS_DEFECT'] = pd.to_numeric(df['IS_DEFECT'], errors='coerce').fillna(0).astype(int)
    if 'Class' in df.columns:
        df['Class'] = pd.to_numeric(df['Class'], errors='coerce').fillna(9).astype(int)
    if all(c in df.columns for c in ['Step_desc', 'Lot', 'Slot No']):
        df['Wafer_ID'] = df['Step_desc'].astype(str) + "_" + df['Lot'].astype(str) + "_" + df['Slot No'].astype(str)
        df['Step_desc'] = df['Step_desc'].astype(str).str.upper()
    return df

df_raw = load_and_prep_data()

# ==========================================
# 2. 실제 데이터 기반 지표(KPI) 및 Top 3 계산
# ==========================================
status_colors = {'PC': '#10B981', 'CBCMP': '#10B981', 'RMG': '#10B981'}
status_glow = {'PC': 'rgba(16, 185, 129, 0.4)', 'CBCMP': 'rgba(16, 185, 129, 0.4)', 'RMG': 'rgba(16, 185, 129, 0.4)'}

actual_yield = 100.0
actual_oee = 76.5
actual_prod = 88.0
top3_html = "<div style='text-align:center; padding: 20px; font-size: 27px; color:#6B7280;'>문제 발생 이력 없음</div>"

if not df_raw.empty:
    df_real = df_raw[df_raw['Class'] != 9].copy()
    
    total_wafers = df_raw['Wafer_ID'].nunique() if not df_raw.empty else 1
    total_defects = len(df_real)
    
    WAFER_AREA_CM2 = np.pi * (15 ** 2)
    density = total_defects / total_wafers / WAFER_AREA_CM2
    
    base_area_cm2 = 1.0
    scribe_line_cm = 0.008
    eff_side_cm = np.sqrt(base_area_cm2) + scribe_line_cm
    chip_area_cm2 = eff_side_cm ** 2
    
    actual_yield = np.exp(-chip_area_cm2 * density) * 100

    if not df_real.empty:
        summary = df_real.groupby(['Wafer_ID', 'Lot', 'Step_desc']).size().reset_index(name='결함수')
        severe_lots_count = summary[summary['결함수'] >= 65]['Lot'].nunique()
        total_lots = df_real['Lot'].nunique()
        
        top3_df = summary.sort_values(by='결함수', ascending=False).head(3)
        if not top3_df.empty:
            lines = []
            for i, row in top3_df.iterrows():
                icon = "🚨" if row['결함수'] >= 65 else "⚠️"
                color = "#EF4444" if row['결함수'] >= 65 else "#F59E0B"
                lines.append(f"""<div style="display: flex; justify-content: space-between; align-items: center; background: #F9FAFB; padding: 12px 15px; margin-bottom: 8px; border-radius: 8px; border: 1px solid #E5E7EB;">
<span style="font-size: 27px; font-weight: bold; color: #374151;">{icon} {row['Step_desc']}</span>
<span style="font-size: 27px; color: #4B5563; font-weight: bold;">{row['Lot']}</span>
<span style="font-size: 28px; font-weight: bold; color: {color};">{row['결함수']}건</span>
</div>""")
            top3_html = "".join(lines)

        for step in ['PC', 'CBCMP', 'RMG']:
            step_data = summary[summary['Step_desc'] == step]
            if not step_data.empty:
                max_c = step_data['결함수'].max()
                if max_c >= 65:
                    status_colors[step] = '#EF4444'
                    status_glow[step] = 'rgba(239, 68, 68, 0.5)'

now_kst = datetime.utcnow() + timedelta(hours=9)
current_time_str = now_kst.strftime("%Y-%m-%d %H:%M")

# ==========================================
# 3. CSS 스타일링
# ==========================================
st.markdown("""
<style>
    .stApp { background-color: #FFFFFF; }
    
    .main-title { font-size: 45px; font-weight: 700; color: #31333F; margin-top: 10px;}
    .time-text { font-size: 30px; font-weight: 900; color: #9CA3AF; text-align: right; margin-top: 18px;}
    
    .kpi-title { 
        font-size: 28px; 
        font-weight: bold; 
        color: #1E3A8A; 
        border-bottom: 2px solid #D1D5DB; 
        padding-bottom: 5px; 
        margin-bottom: 15px; 
        margin-top: 20px; 
    }
    
    .bottleneck-card { background: #FFFFFF; padding: 20px; border-radius: 10px; border: 1px solid #E5E7EB; border-top: 5px solid #9CA3AF; position: relative; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .bottleneck-card.alert { border-top: 5px solid #EF4444; background: #FEF2F2; border-color: #FECACA; }
    
    .bn-title { font-size: 36px; font-weight: bold; margin-bottom: 15px; color: #111827; }
    .bn-text { font-size: 27px; color: #6B7280; margin-bottom: 8px; }
    .bn-highlight { color: #B45309; font-weight: bold; font-size: 28px; }
    
    .action-card { background: #FFFFFF; padding: 20px; border-radius: 15px; border: 1px solid #E5E7EB; box-shadow: 0 4px 6px rgba(0,0,0,0.05); height: 100%; }
    .action-title { font-size: 28px; color: #DC2626; margin-bottom: 15px; font-weight: bold; display: flex; align-items: center; gap: 8px;}
    
    .env-container { background: #FFFFFF; padding: 15px; border-radius: 10px; text-align: center; border: 1px solid #E5E7EB; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
    
    .env-step { font-size: 25px; color: #6B7280; margin-bottom: 5px; font-weight: bold; }
    .env-val { font-size: 32px; color: #111827; font-weight: bold; line-height: 1.4; }
</style>
""", unsafe_allow_html=True)

col_t1, col_t2 = st.columns([65, 35], gap="large")
with col_t1:
    st.markdown('<div class="main-title">FAB 공정 OVERVIEW</div>', unsafe_allow_html=True)
with col_t2:
    st.markdown(f'<div class="time-text">현재 시간: {current_time_str}</div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 4. 레이아웃 1층: KPI 계기판 & TOP 3 문제 상황
# ==========================================
col_top_left, col_top_right = st.columns([65, 35], gap="large")

with col_top_left:
    st.markdown('<div class="kpi-title">종합 장비 효율 계기판</div>', unsafe_allow_html=True)
    g_c1, g_c2, g_c3 = st.columns(3)
    
    def make_svg_gauge(val, title):
        val = max(0, min(100, val))
        
        if val == int(val) or val.is_integer():
            val_str = f"{int(val)}"
        else:
            val_str = f"{val:.1f}"
        
        color = "#3B82F6" 
            
        c_outer = 2 * math.pi * 92
        offset_outer = c_outer * (1 - val/100)
        c_inner = 2 * math.pi * 75
        offset_inner = c_inner * (1 - val/100)
        uid = f"mask_{uuid.uuid4().hex[:8]}"
        
        # 💡 SVG 자체 크기를 270x270으로 1.8배 확대 적용 (숫자 및 비율 유지)
        svg_code = f"""
<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; margin-bottom: 20px;">
<div style='text-align:center; color:#1E3A8A; font-weight:bold; margin-bottom:10px; font-size: 25px;'>{title}</div>
<svg width="270" height="270" viewBox="0 0 200 200">
<defs>
<mask id="{uid}">
<rect width="200" height="200" fill="black" />
<circle cx="100" cy="100" r="75" fill="none" stroke="white" stroke-width="20" stroke-dasharray="{c_inner}" stroke-dashoffset="{offset_inner}" transform="rotate(-90 100 100)" />
</mask>
</defs>
<circle cx="100" cy="100" r="92" fill="none" stroke="#E5E7EB" stroke-width="8" />
<circle cx="100" cy="100" r="75" fill="none" stroke="#E5E7EB" stroke-width="12" stroke-dasharray="4 5" />
<circle cx="100" cy="100" r="92" fill="none" stroke="{color}" stroke-width="8" stroke-dasharray="{c_outer}" stroke-dashoffset="{offset_outer}" transform="rotate(-90 100 100)" stroke-linecap="round" />
<circle cx="100" cy="100" r="75" fill="none" stroke="{color}" stroke-width="12" stroke-dasharray="4 5" mask="url(#{uid})" />
<text x="100" y="95" font-family="Arial, sans-serif" font-size="46" font-weight="bold" fill="#1F2937" text-anchor="middle" dominant-baseline="central">{val_str}</text>
<text x="100" y="145" font-family="Arial, sans-serif" font-size="28" fill="#6B7280" text-anchor="middle" dominant-baseline="central">%</text>
</svg>
</div>
"""
        return svg_code

    with g_c1: st.markdown(make_svg_gauge(actual_oee, "장비 효율 (OEE)"), unsafe_allow_html=True)
    with g_c2: st.markdown(make_svg_gauge(actual_prod, "생산성 (Productivity)"), unsafe_allow_html=True)
    with g_c3: st.markdown(make_svg_gauge(actual_yield, "수율 (Yield)"), unsafe_allow_html=True)

with col_top_right:
    html_action = f"""<div class="action-card">
<div class="action-title">
<svg width="43" height="43" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
조치 요망 배치 (Top 3)
</div>
<div>{top3_html}</div>
</div>"""
    st.markdown(html_action, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# 5. 레이아웃 2층: 공정 사진(좌) + 차트/환경(우)
# ==========================================
col_mid_left, col_mid_right = st.columns([65, 35], gap="large")

# ---- (좌) 공정 이미지 ----
with col_mid_left:
    st.markdown('<div class="kpi-title">실시간 공정 상태</div>', unsafe_allow_html=True)
    
    img_b64 = get_image_base64("image_ddb1bd.png")

    if img_b64:
        html_image_overlay = f"""
<div style="position: relative; width: 100%; margin: 0 auto 10px auto;">
  <img src="data:image/png;base64,{img_b64}"
       style="width: 100%; height: auto; border-radius: 10px;
              box-shadow: 0 10px 15px -3px rgba(0,0,0,0.10);" />

  <div style="position: absolute; bottom: 5%; left: 9%;
              width: 25px; height: 25px; border-radius: 50%;
              background-color: {status_colors['PC']};
              box-shadow: 0 0 15px {status_glow['PC']}, inset 0 0 5px white;
              z-index: 10;"></div>

  <div style="position: absolute; bottom: 5%; left: 44.0%;
              width: 25px; height: 25px; border-radius: 50%;
              background-color: {status_colors['CBCMP']};
              box-shadow: 0 0 15px {status_glow['CBCMP']}, inset 0 0 5px white;
              z-index: 10;"></div>

  <div style="position: absolute; bottom: 5%; left: 80.0%;
              width: 25px; height: 25px; border-radius: 50%;
              background-color: {status_colors['RMG']};
              box-shadow: 0 0 15px {status_glow['RMG']}, inset 0 0 5px white;
              z-index: 10;"></div>
</div>
"""
        st.markdown(html_image_overlay, unsafe_allow_html=True)
    else:
        st.error("⚠️ 'image_ddb1bd.png' 파일을 찾을 수 없습니다.")

    st.markdown('<div class="kpi-title">공정별 WIP 현황</div>', unsafe_allow_html=True)

    processes = ['PC', 'RMG', 'CBCMP']
    rates = [random.uniform(0.15, 0.35), random.uniform(0.45, 0.70), random.uniform(0.85, 0.95)]
    random.shuffle(rates)

    flow_data = {}
    for i, proc in enumerate(processes):
        in_qty = random.randint(1200, 1800)
        out_qty = int(in_qty * rates[i])

        is_bottleneck = True if rates[i] < 0.4 else False
        q_time = random.uniform(8.0, 15.0) if is_bottleneck else random.uniform(1.5, 4.5)
        w_lots = random.randint(200, 400) if is_bottleneck else random.randint(20, 80)

        flow_data[proc] = {
            'q': f'{q_time:.1f}h',
            'w': f'{w_lots} Lots',
            'in': in_qty,
            'out': out_qty,
            'alert': is_bottleneck
        }

    # --- 카드 3개 ---
    f_c1, f_c2, f_c3 = st.columns(3)
    for i, (proc, data) in enumerate(flow_data.items()):
        col = [f_c1, f_c2, f_c3][i]
        al_class = "alert" if data['alert'] else ""
        al_icon = "🚨 병목 경고" if data['alert'] else ""

        html_bn = f'''
        <div class="bottleneck-card {al_class}">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div class="bn-title">{proc}</div>
                <div style="color:#DC2626; font-size:24px; font-weight:bold;">{al_icon}</div>
            </div>
            <div class="bn-text">평균 대기 시간: <span style="color:#111827; font-weight:bold;">{data["q"]}</span></div>
            <div class="bn-text">대기 로트 수: <span class="bn-highlight">{data["w"]}</span></div>
        </div>
        '''
        col.markdown(html_bn, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- 투입/완료 바차트 ---
    chart_processes = list(flow_data.keys())
    chart_inputs = [d['in'] for d in flow_data.values()]
    chart_outputs = [d['out'] for d in flow_data.values()]

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=chart_processes, y=chart_inputs,
        name='투입 수량', marker_color='#9CA3AF',
        hovertemplate='%{x} 투입: <b>%{y}개</b><extra></extra>'
    ))
    fig_bar.add_trace(go.Bar(
        x=chart_processes, y=chart_outputs,
        name='완료 수량', marker_color='#3B82F6',
        hovertemplate='%{x} 완료: <b>%{y}개</b><extra></extra>'
    ))

    fig_bar.update_layout(
        barmode='group', bargap=0.55, bargroupgap=0.15,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(t=10, l=10, r=10, b=10),
        height=380,
        hovermode='x unified',
        hoverlabel=dict(font_size=25, bgcolor="#FFFFFF", bordercolor="#D1D5DB", font_color="#1F2937"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color='#1F2937', size=25))
    )
    fig_bar.update_xaxes(tickfont=dict(color='#374151', size=25), showgrid=False)
    fig_bar.update_yaxes(showticklabels=False, showgrid=True, gridcolor='#E5E7EB', zeroline=False)

    st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})

# ---- (우) 개별 공정 막대 차트(X: 건수, Y: 유형) + 온습도 ----
with col_mid_right:
    st.markdown('<div class="kpi-title">공정별 결함 유형 통계</div>', unsafe_allow_html=True)

    if not df_raw.empty:
        df_real = df_raw[df_raw['Class'] != 9].copy()
        df_real['Class_str'] = "유형 " + df_real['Class'].astype(str)

        bar_data = df_real.groupby(['Step_desc', 'Class_str']).size().reset_index(name='count')
        step_totals = bar_data.groupby('Step_desc')['count'].sum().sort_values(ascending=False).index

        for proc in step_totals:
            p_data = bar_data[bar_data['Step_desc'] == proc].copy()
            p_data = p_data.sort_values(by='count', ascending=True) 

            n_bars = len(p_data)
            gradient_colors = [f'rgba(37, 99, 235, {alpha:.2f})' for alpha in np.linspace(0.2, 1.0, n_bars)]
            
            st.markdown(f"<div style='font-size: 28px; font-weight: bold; color: #1E3A8A; margin-bottom: 2px;'>{proc} 공정</div>", unsafe_allow_html=True)
            
            fig_h = go.Figure(go.Bar(
                x=p_data['count'], 
                y=p_data['Class_str'], 
                orientation='h',
                marker_color=gradient_colors
            ))

            fig_h.update_layout(
                height=220,
                margin=dict(t=10, b=40, l=10, r=20),
                xaxis=dict(title="결함 건수", showgrid=True, gridcolor='#E5E7EB', tickfont=dict(size=21, color='#6B7280'), title_font=dict(size=25)),
                yaxis=dict(title="", showgrid=False, tickfont=dict(size=23, color='#374151'), categoryorder='total ascending'),
                showlegend=False,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                hovermode=False
            )

            st.plotly_chart(fig_h, use_container_width=True, config={'displayModeBar': False})
            st.markdown("<div style='margin-bottom: 5px;'></div>", unsafe_allow_html=True)
            
    else:
        st.info("데이터가 없습니다.")

    st.markdown('<div class="kpi-title">실시간 온/습도 모니터링</div>', unsafe_allow_html=True)

    env_data = {'PC': ['23°C', '45%'], 'CBCMP': ['24°C', '50%'], 'RMG': ['25°C', '10%']}

    e_c1, e_c2, e_c3 = st.columns(3)
    for i, (proc, vals) in enumerate(env_data.items()):
        col = [e_c1, e_c2, e_c3][i]
        # 💡 한 줄씩 출력되도록 <br> 태그 추가
        html_env = f'''
        <div class="env-container">
            <div class="env-step">{proc}</div>
            <div class="env-val">🌡️ {vals[0]}<br>💧 {vals[1]}</div>
        </div>
        '''
        col.markdown(html_env, unsafe_allow_html=True)


st.markdown("<br>", unsafe_allow_html=True)

