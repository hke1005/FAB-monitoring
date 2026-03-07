import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import base64
import os
from pathlib import Path

# ==========================================
# 1. 전역 변수 및 기본 설정 (세션 상태 포함)
# ==========================================
WAFER_RADIUS = 150000 # 150mm (15cm)
WAFER_AREA_CM2 = np.pi * (15 ** 2) # 약 706.86 cm^2

st.set_page_config(page_title="현장 관리자 대시보드", layout="wide")

if 'selected_lot_state' not in st.session_state:
    st.session_state.selected_lot_state = '전체'
if 'selected_die_state' not in st.session_state:
    st.session_state.selected_die_state = '100 mm²'

def set_selected_lot(lot_id):
    st.session_state.selected_lot_state = lot_id

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 28px; color: #1E3A8A; font-weight: bold; }
    [data-testid="stMetricLabel"] { font-size: 16px; color: #4B5563; }
    div[data-testid="stMetric"] {
        background-color: #EFF6FF; padding: 15px; border-radius: 10px;
        border: 1px solid #BFDBFE; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    .stDataFrame { border: 1px solid #BFDBFE; border-radius: 5px; }
    
    .manager-card {
        background-color: #1E3A8A; color: white; padding: 15px; border-radius: 10px;
        text-align: left; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }

    .alert-box::-webkit-scrollbar { width: 6px; }
    .alert-box::-webkit-scrollbar-track { background: transparent; }
    .alert-box::-webkit-scrollbar-thumb { background: #D1D5DB; border-radius: 3px; }
    .alert-box::-webkit-scrollbar-thumb:hover { background: #9CA3AF; }

    /* 💡 메인 영역과 사이드바를 나누는 세로선 굵고 진하게 수정 */
    div[data-testid="stHorizontalBlock"] > div:nth-child(2) {
        border-left: 3px solid #9CA3AF; 
        padding-left: 20px;
    }
    
    /* 하단 3개 차트를 묶을 때 내부에 생기는 불필요한 회색 세로선 완벽 제거 */
    div[data-testid="stHorizontalBlock"] div[data-testid="stHorizontalBlock"] > div:nth-child(2),
    div[data-testid="stHorizontalBlock"] div[data-testid="stHorizontalBlock"] > div:nth-child(3) {
        border-left: none !important;
        padding-left: 0 !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 데이터 생성 및 로드 함수
# ==========================================
@st.cache_data
def get_simulated_equipment_data(lot_id):
    seed_val = sum([ord(c) for c in str(lot_id)]) if lot_id and lot_id != '전체' else 999
    np.random.seed(seed_val)
    
    steps = 60
    base_time = pd.Timestamp.now().floor('T') - pd.Timedelta(minutes=60)
    times = [base_time + pd.Timedelta(minutes=i) for i in range(steps)]
    
    def gen_with_outliers(base, std, outlier_range):
        data = np.random.normal(base, std, steps)
        outlier_idx = np.random.rand(steps) < 0.05 
        data[outlier_idx] += np.random.choice(outlier_range, size=outlier_idx.sum())
        return data

    df_eq = pd.DataFrame({
        'Time': times,
        'Temp': gen_with_outliers(400.0, 1.5, [-15.0, 18.0, -22.0, 25.0]),   
        'Press': gen_with_outliers(3.0, 0.1, [-1.5, 1.8, -1.2, 1.4]),        
        'Gas': gen_with_outliers(100.0, 1.0, [-8.0, 9.0, -11.0, 12.0]),      
        'Power': gen_with_outliers(600.0, 2.0, [-45.0, 50.0, -35.0, 40.0])
    })
    
    equip_life_max = np.clip(np.random.normal(60, 20), 10, 98)
    shift_prog_max = np.clip(np.random.normal(85, 10), 10, 99)
    df_eq['Equip_Life'] = np.linspace(max(0, equip_life_max - 1.5), equip_life_max, steps)
    df_eq['Shift_Prog'] = np.linspace(max(0, shift_prog_max - 2.0), shift_prog_max, steps)
    
    if equip_life_max >= 85: df_eq['Maint_Status'] = "즉시 교체 필요"
    elif equip_life_max >= 70: df_eq['Maint_Status'] = "점검 필요"
    else: df_eq['Maint_Status'] = "정상 가동 중"

    return df_eq

@st.cache_data
def get_image_base64(filename: str):
    try:
        from PIL import Image
        import io
        current_dir = os.path.dirname(os.path.abspath(__file__))
        img_path = os.path.join(current_dir, filename)
        p = Path(img_path)
        
        if p.exists():
            img = Image.open(img_path).convert("RGBA")
            data = img.getdata()
            new_data = []
            
            for item in data:
                if item[0] > 200 and item[1] > 200 and item[2] > 200:
                    if abs(item[0]-item[1]) < 15 and abs(item[1]-item[2]) < 15:
                        new_data.append((255, 255, 255, 0))
                        continue
                new_data.append(item)
                    
            img.putdata(new_data)
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode()
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
        '중심거리': 'RADIUS', '방향각도': 'ANGLE',
        '영역잡음': 'PATCHNOISE', '점형지수': 'SPOTLIKENESS', '정렬정도': 'ALIGNRATIO',
        '상대강도': 'RELATIVEMAGNITUDE', '활성지수': 'ACTIVERATIO', '패치신호': 'PATCHDEFECTSIGNAL'
    }
    
    df = df_raw.rename(columns=KOR_TO_ENG).copy()
    
    if 'IS_DEFECT' in df.columns:
        df['IS_DEFECT'] = df['IS_DEFECT'].astype(str).str.strip().replace({'불량': '1', '정상': '0', 'Y': '1', 'N': '0'})
        df['IS_DEFECT'] = pd.to_numeric(df['IS_DEFECT'], errors='coerce').fillna(0).astype(int)
    if 'Class' in df.columns:
        df['Class'] = pd.to_numeric(df['Class'], errors='coerce').fillna(9).astype(int)
    if 'RADIUS' in df.columns and 'ANGLE' in df.columns:
        df['X'] = df['RADIUS'] * np.cos(np.radians(df['ANGLE']))
        df['Y'] = df['RADIUS'] * np.sin(np.radians(df['ANGLE']))
    if all(c in df.columns for c in ['Step_desc', 'Lot', 'Slot No']):
        df['Wafer_ID'] = df['Step_desc'].astype(str) + "_" + df['Lot'].astype(str) + "_" + df['Slot No'].astype(str)
        
    radar_features_eng = ['PATCHNOISE', 'SPOTLIKENESS', 'ALIGNRATIO', 'RELATIVEMAGNITUDE', 'ACTIVERATIO', 'PATCHDEFECTSIGNAL']
    for col in radar_features_eng:
        if col not in df.columns: df[col] = 0.0
    df[radar_features_eng] = df[radar_features_eng].apply(pd.to_numeric, errors='coerce').fillna(0)
    
    return df

# ==========================================
# 3. 메인 대시보드 구조 (통합 레이아웃 적용)
# ==========================================
df_raw = load_and_prep_data()

if df_raw.empty:
    st.error("데이터가 없거나 불러오는데 실패했습니다. '반도체_결함_데이터_한글.csv' 파일을 확인해주세요.")
else:
    df = df_raw[(df_raw['Step_desc'].astype(str).str.upper() == 'RMG') & (df_raw['Class'] != 9)].copy()
    
    if df.empty:
        st.warning("RMG 공정에 해당하는 데이터가 존재하지 않습니다.")
    else:
        radar_features_eng = ['PATCHNOISE', 'SPOTLIKENESS', 'ALIGNRATIO', 'RELATIVEMAGNITUDE', 'ACTIVERATIO', 'PATCHDEFECTSIGNAL']
        radar_features_kor = ['영역잡음', '점형지수', '정렬정도', '상대강도', '활성지수', '패치신호']
        
        radar_min, radar_max = df[radar_features_eng].min(), df[radar_features_eng].max()
        radar_denom = (radar_max - radar_min).replace(0, 1)

        wafer_summary = df.groupby(['Wafer_ID', 'Lot', 'Step_desc']).size().reset_index(name='결함수')
        wafer_summary['상태 (Severity)'] = np.where(wafer_summary['결함수'] >= 65, '🔴 HIGH', '🟢 NORMAL')
        wafer_summary = wafer_summary.sort_values('결함수', ascending=False).reset_index(drop=True)

        high_defect_wafers = wafer_summary[wafer_summary['결함수'] >= 65]

        df_rmg_all = df_raw[df_raw['Step_desc'].astype(str).str.upper() == 'RMG'].copy()
        
        total_wafers_produced = df_rmg_all['Wafer_ID'].nunique() if not df_rmg_all.empty else 0
        
        class_9_cnt = len(df_rmg_all[df_rmg_all['Class'] == 9])
        non_class_9_cnt = len(df_rmg_all[df_rmg_all['Class'] != 9])
        total_defects_all = class_9_cnt + non_class_9_cnt
        class_9_ratio = (class_9_cnt / total_defects_all * 100) if total_defects_all > 0 else 0.0
        
        if high_defect_wafers.empty:
            status_indicator, priority_lot = "🟢", "없음"
        else:
            status_indicator = "🔴"
            priority_lot = (
                high_defect_wafers_all.groupby('Lot')
                .size().reset_index(name='count')
                .sort_values('count', ascending=False)
                .iloc[0]['Lot']
            )

        # 💡 [핵심 변경] 기둥을 단 한 번만 나눕니다.
        main_col, side_col = st.columns([65, 35], gap="large")

        # ==========================================
        # 4. 좌측 메인 영역 (타이틀 포함)
        # ==========================================
        with main_col:
            # 💡 타이틀을 왼쪽 기둥 안으로 가져왔습니다.
            st.title("RMG 공정 모니터링")
            st.caption("RMG 공정 | 결함 분포/경고 웨이퍼/공정 변수 모니터링")
            
            # 💡 기둥이 합쳐졌으므로 margin-top을 양수(10px)로 주어 자연스럽게 간격을 벌립니다.
            st.markdown("<hr style='margin-top: 70px; margin-bottom: 20px; border: 0; border-top: 1px solid rgba(156, 163, 175, 0.5);'>", unsafe_allow_html=True)
            kpi_container = st.container()

            row1_left, row1_right = st.columns([1.2, 2.5], gap="large")
            
            with row1_left:
                st.markdown("<div style='font-weight: 800; font-size: 16px; margin-bottom: 10px;'>🚨 실시간 알림 내역 <span style='float:right; color:#9CA3AF; font-size: 13px; font-weight: normal;'>방금 전</span></div>", unsafe_allow_html=True)
                
                alert_container = st.container(height=350, border=True)
                with alert_container:
                    alert_count = 0
                    
                    if not high_defect_wafers.empty:
                        lot_warning_counts = high_defect_wafers.groupby('Lot').size().reset_index(name='경고웨이퍼수').sort_values('경고웨이퍼수', ascending=False)
                        for idx, row_warn in lot_warning_counts.iterrows():
                            lot_num = row_warn['Lot']
                            warn_cnt = row_warn['경고웨이퍼수']
                            alert_count += 1
                            
                            a_col1, a_col2, a_col3 = st.columns([1, 4, 1.5], vertical_alignment="center")
                            with a_col1:
                                st.markdown(f"<div style='width: 32px; height: 32px; background-color: #FA5C5C; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-top: 5px;'>{warn_cnt}</div>", unsafe_allow_html=True)
                            with a_col2:
                                st.markdown(f"<div style='font-weight: bold; font-size: 14px; margin-bottom: 2px; color: #374151;'>결함 다량 발생 감지</div><div style='font-size: 12px; color: #6B7280;'>배치: {lot_num} | 위험 {warn_cnt}장</div>", unsafe_allow_html=True)
                            with a_col3:
                                st.button("조회", key=f"btn_def_{lot_num}", on_click=set_selected_lot, args=(lot_num,), use_container_width=True)
                            
                            st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #F3F4F6;'>", unsafe_allow_html=True)
                            
                    unique_lots = df['Lot'].dropna().unique() if not df.empty else []
                    for lot_num in unique_lots:
                        eq_data = get_simulated_equipment_data(lot_num)
                        
                        cur_t = eq_data['Temp'].iloc[-1]
                        cur_p = eq_data['Press'].iloc[-1]
                        cur_g = eq_data['Gas'].iloc[-1]
                        cur_pw = eq_data['Power'].iloc[-1]
                        
                        anomalies = []
                        if cur_t > 420.0 or cur_t < 380.0: anomalies.append(('T', '온도', f"{cur_t:.1f}", '°C'))
                        if cur_p > 5.0 or cur_p < 1.0: anomalies.append(('P', '압력', f"{cur_p:.2f}", 'Torr'))
                        if cur_g > 110.0 or cur_g < 90.0: anomalies.append(('G', '가스', f"{cur_g:.1f}", 'sccm'))
                        if cur_pw > 650.0 or cur_pw < 550.0: anomalies.append(('W', 'RF전력', f"{cur_pw:.0f}", 'W'))
                        
                        if len(anomalies) == 1:
                            alert_count += 1
                            initial, param_name, val_str, unit = anomalies[0]
                            
                            a_col1, a_col2, a_col3 = st.columns([1, 4, 1.5], vertical_alignment="center")
                            with a_col1:
                                st.markdown(f"<div style='width: 32px; height: 32px; background-color: #EF4444; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-top: 5px;'>{initial}</div>", unsafe_allow_html=True)
                            with a_col2:
                                st.markdown(f"<div style='font-weight: bold; font-size: 14px; margin-bottom: 2px; color: #374151;'>설비 파라미터 이상 감지</div><div style='font-size: 12px; color: #6B7280;'>배치: {lot_num} | {param_name}: <span style='color:#EF4444; font-weight:bold;'>{val_str}{unit}</span></div>", unsafe_allow_html=True)
                            with a_col3:
                                st.button("조회", key=f"btn_eq_{lot_num}_{initial}", on_click=set_selected_lot, args=(lot_num,), use_container_width=True)
                            
                            st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #F3F4F6;'>", unsafe_allow_html=True)
                            
                        elif len(anomalies) >= 2:
                            alert_count += 1
                            detail_str = ", ".join([f"{p}: <span style='color:#EF4444; font-weight:bold;'>{v}{u}</span>" for i, p, v, u in anomalies])
                            
                            a_col1, a_col2, a_col3 = st.columns([1, 4, 1.5], vertical_alignment="center")
                            with a_col1:
                                st.markdown(f"<div style='width: 32px; height: 32px; background-color: #EF4444; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 16px; margin-top: 5px;'>⚠️</div>", unsafe_allow_html=True)
                            with a_col2:
                                st.markdown(f"<div style='font-weight: bold; font-size: 14px; margin-bottom: 2px; color: #374151;'>설비 파라미터 {len(anomalies)}건 이상</div><div style='font-size: 12px; color: #6B7280;'>배치: {lot_num} | {detail_str}</div>", unsafe_allow_html=True)
                            with a_col3:
                                st.button("조회", key=f"btn_eq_{lot_num}_multi", on_click=set_selected_lot, args=(lot_num,), use_container_width=True)
                            
                            st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #F3F4F6;'>", unsafe_allow_html=True)

                    if alert_count == 0:
                        st.markdown("<div style='display: flex; align-items: center; justify-content: center; height: 100%; color: #10B981; font-weight: bold;'>현재 발생한 경고 알림이 없습니다.</div>", unsafe_allow_html=True)

            with row1_right:
                st.markdown("**조회 조건 설정**")
                
                filter_col1, filter_col2 = st.columns(2)
                with filter_col1:
                    lot_options = ['전체'] + sorted(list(wafer_summary['Lot'].astype(str).unique()))
                    selected_lot = st.selectbox("배치번호(Lot):", lot_options, key='selected_lot_state')
                with filter_col2:
                    selected_die = st.selectbox("다이 사이즈 선택:", ["100 mm²", "130 mm²"], key='selected_die_state')

                st.markdown("<div style='margin-top: 10px;'><b>Lot Data Breakdown (웨이퍼ID를 클릭하세요!)</b></div>", unsafe_allow_html=True)
                
                if selected_lot != '전체':
                    display_summary = wafer_summary[wafer_summary['Lot'].astype(str) == selected_lot].reset_index(drop=True)
                else:
                    display_summary = wafer_summary.copy()
                
                event = st.dataframe(
                    display_summary[['Wafer_ID', '상태 (Severity)', '결함수']],
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
                            max_value=int(wafer_summary['결함수'].max()) if not wafer_summary.empty else 100
                        )
                    },
                    height=270, 
                    use_container_width=True
                )

            # 필터링 로직
            ts_lot = selected_lot
            if event.selection.rows:
                selected_idx = event.selection.rows[0]
                selected_wafer_id = display_summary.iloc[selected_idx]['Wafer_ID']
                ts_lot = display_summary.iloc[selected_idx]['Lot']
                filtered_df = df[df['Wafer_ID'] == selected_wafer_id].copy()
                chart_title_suffix = f" ({selected_wafer_id})"
            else:
                if selected_lot != '전체':
                    filtered_df = df[df['Lot'].astype(str) == selected_lot].copy()
                    chart_title_suffix = f" (Lot: {selected_lot})"
                else:
                    filtered_df = df.copy()
                    chart_title_suffix = " (RMG 공정 전체)"

            filtered_df = filtered_df.reset_index(drop=True)
            filtered_df['Defect_ID'] = filtered_df.index  
            
            if not filtered_df.empty:
                filtered_df['Class_str'] = filtered_df['Class'].astype(str)
                unique_classes = sorted(filtered_df['Class'].unique())
                color_palette = px.colors.qualitative.Plotly
                color_map = {str(cls): color_palette[i % len(color_palette)] for i, cls in enumerate(unique_classes)}
            else:
                color_map = {}

            with kpi_container:
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                
                num_wafers_in_scope = filtered_df['Wafer_ID'].nunique() if not filtered_df.empty else 1
                if num_wafers_in_scope == 0: num_wafers_in_scope = 1
                
                total_defects_in_scope = len(filtered_df)
                
                scope_summary = filtered_df.groupby('Wafer_ID').size().reset_index(name='결함수')
                scope_high_wafers = len(scope_summary[scope_summary['결함수'] >= 65])
                
                kpi1_label = "결함 수"
                kpi1_val = f"{total_defects_in_scope:,} 건"
                
                if event.selection.rows:
                    density = total_defects_in_scope / WAFER_AREA_CM2
                else:
                    avg_defects = total_defects_in_scope / num_wafers_in_scope
                    density = avg_defects / WAFER_AREA_CM2

                scribe_line_cm = 0.008 
                if selected_die == "100 mm²":
                    base_area_cm2 = 1.0
                else:
                    base_area_cm2 = 1.3
                    
                eff_side_cm = np.sqrt(base_area_cm2) + scribe_line_cm
                chip_area_cm2 = eff_side_cm ** 2
                
                poisson_yield = np.exp(-chip_area_cm2 * density) * 100

                kpi1.metric(kpi1_label, kpi1_val)
                kpi2.metric("수율", f"{poisson_yield:.2f} %")
                kpi3.metric("Defect Density", f"{density:.4f} ea/cm²")
                kpi4.metric("경고 웨이퍼 수", f"{scope_high_wafers} 장")

            # 💡 수정 2: 삭제했던 두 번째 회색 선을 '결함 심층 분석' 영역 바로 위로 내려서 재배치
            st.markdown("---")
            st.markdown(f"<h4 style='color: #1E3A8A; margin-top: 10px; font-weight: bold;'>🔍 결함 심층 분석 {chart_title_suffix}</h4>", unsafe_allow_html=True)
            
            with st.container(border=True):
                row2_left, row2_mid, row2_right = st.columns([1.2, 1.2, 1.2], gap="large")

                with row2_left:
                    if not filtered_df.empty and 'X' in filtered_df.columns:
                        st.markdown(f"**결함 분포 맵** {chart_title_suffix}")
                        
                        fig_map = px.scatter(
                            filtered_df, x='X', y='Y', 
                            color='Class_str', 
                            hover_data=['Wafer_ID', 'Step_desc', 'Lot'],
                            custom_data=['Defect_ID'], 
                            color_discrete_map=color_map, 
                            labels={'Class_str': '결함 유형'},
                            height=350
                        )
                        fig_map.add_shape(type="circle", x0=-WAFER_RADIUS, y0=-WAFER_RADIUS, x1=WAFER_RADIUS, y1=WAFER_RADIUS, line_color="#9CA3AF", line_width=2)
                        fig_map.update_layout(
                            xaxis=dict(visible=False, range=[-WAFER_RADIUS*1.1, WAFER_RADIUS*1.1]), 
                            yaxis=dict(visible=False, range=[-WAFER_RADIUS*1.1, WAFER_RADIUS*1.1], scaleanchor="x", scaleratio=1), 
                            margin=dict(l=0, r=0, t=10, b=0),
                            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                            showlegend=False,
                            hoverlabel=dict(font=dict(size=18))
                        )
                        
                        map_event = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun", selection_mode="points")
                    else:
                        map_event = None
                        st.info("해당 조건의 맵 데이터가 없습니다.")

                with row2_mid:
                    st.markdown(f"**결함 특성화 지표** {chart_title_suffix}")
                    
                    if map_event and map_event.selection.points:
                        selected_defect_id = map_event.selection.points[0]["customdata"][0]
                        sel_row = filtered_df[filtered_df['Defect_ID'] == selected_defect_id]
                        raw_vals = sel_row[radar_features_eng].values[0]
                        radar_vals = ((raw_vals - radar_min) / radar_denom).tolist()
                    else:
                        raw_vals = filtered_df[radar_features_eng].mean() if not filtered_df.empty else pd.Series(0, index=radar_features_eng)
                        radar_vals = ((raw_vals - radar_min) / radar_denom).tolist()
                    
                    radar_vals_closed = radar_vals + [radar_vals[0]]
                    radar_labels_closed = radar_features_kor + [radar_features_kor[0]]
                    
                    fig_radar = go.Figure(data=go.Scatterpolar(
                        r=radar_vals_closed,
                        theta=radar_labels_closed,
                        fill='toself',
                        line_color='#60A5FA',          
                        fillcolor='rgba(96, 165, 250, 0.4)', 
                        marker=dict(size=6)
                    ))
                    
                    fig_radar.update_layout(
                        polar=dict(radialaxis=dict(visible=True, showticklabels=False, ticks='', range=[0, 1])),
                        showlegend=False,
                        margin=dict(l=40, r=40, t=30, b=30),
                        height=350,
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        hoverlabel=dict(font=dict(size=18))
                    )
                    st.plotly_chart(fig_radar, use_container_width=True)

                with row2_right:
                    st.markdown(f"**결함 유형 통계** {chart_title_suffix}")
                    if filtered_df.empty or "Class" not in filtered_df.columns:
                        st.info("차트에 표시할 데이터가 없습니다.")
                    else:
                        class_counts = filtered_df["Class"].value_counts().reset_index()
                        class_counts.columns = ["Class", "Count"]
                        class_counts["Class_str"] = class_counts["Class"].astype("Int64").astype(str)
                        
                        total_count = class_counts["Count"].sum()
                        class_counts['Percent'] = (class_counts['Count'] / total_count) * 100
                        class_counts = class_counts.sort_values("Percent", ascending=False).reset_index(drop=True)
                        
                        max_percent = class_counts['Percent'].max() if not class_counts.empty else 0

                        pie_colors = [color_map.get(cls, "#999999") for cls in class_counts["Class_str"]]

                        fig_donut = go.Figure(go.Pie(
                            labels=class_counts["Class_str"],
                            values=class_counts["Count"],
                            hole=0.65,
                            textinfo="none",  
                            hovertemplate="유형 %{label}<br><b>%{value}개</b> (%{percent})<extra></extra>", 
                            marker=dict(colors=pie_colors)
                        ))
                        
                        fig_donut.update_layout(
                            showlegend=False,
                            margin=dict(l=10, r=10, t=10, b=10),
                            height=200,
                            annotations=[dict(text=f"{max_percent:.0f}%", x=0.5, y=0.5, font_size=32, showarrow=False, font=dict(color="#374151"))],
                            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                            hoverlabel=dict(font=dict(size=18))
                        )
                        st.plotly_chart(fig_donut, use_container_width=True)

                        legend_html = "<div style='display:flex;flex-direction:column;justify-content:center;padding:0 6px 6px 6px;'>"
                        for _, row in class_counts.head(5).iterrows():
                            cls_str = row["Class_str"]
                            color = color_map.get(cls_str, "#999999")
                            
                            legend_html += (
                                "<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>"
                                "<div style='display:flex;align-items:center;'>"
                                f"<span style='color:{color};font-size:16px;margin-right:8px;'>●</span>"
                                f"<span style='color:#4B5563;font-size:13px;font-weight:700;'>유형 {cls_str}</span>"
                                "</div>"
                                f"<div style='font-weight:800;color:#111827;font-size:13px;'>{row['Percent']:.0f}%</div>" 
                                "</div>"
                            )
                        if len(class_counts) > 5:
                            legend_html += f"<div style='text-align:right;font-size:12px;color:#9CA3AF;'>+ 외 {len(class_counts)-5}개 유형</div>"
                        legend_html += "</div>"
                        st.markdown(legend_html, unsafe_allow_html=True)

        # ==========================================
        # 5. 우측 사이드바 (담당자 카드 & 설비 모니터링)
        # ==========================================
        with side_col:
            # 💡 기존에 위에 따로 있던 파란색 관리자 카드를 우측 기둥 최상단으로 옮겼습니다.
            st.markdown(f"""
            <div class="manager-card" style="margin-top: 15px; margin-bottom: 0; padding: 12px 20px;">
                <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.2); padding-bottom: 10px; margin-bottom: 10px;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div style="width: 50px; height: 50px; border-radius: 50%; border: 3px solid #60A5FA; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: bold; position: relative; background-color: #1E3A8A;">
                            RMG
                            <div style="position: absolute; top: -10px; right: -6px; font-size: 16px;">
                                {status_indicator}
                            </div>
                        </div>
                        <div>
                            <div style="font-size: 12px; color: #93C5FD; margin-bottom: 2px;">생산 웨이퍼</div>
                            <div style="font-size: 18px; font-weight: bold;">{total_wafers_produced} 장</div>
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 16px; font-weight: bold;">담당자: 허가은</div>
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: flex-end;">
                    <div>
                        <div style="font-size: 11px; color: #93C5FD; margin-bottom: 2px;">가성 결함 비율</div>
                        <div style="font-size: 15px; font-weight: bold;">{class_9_ratio:.1f}%</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 11px; color: #93C5FD; margin-bottom: 2px;">우선 점검 배치</div>
                        <div style="font-size: 15px; font-weight: bold; color: #FCD34D;">{priority_lot}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            disp_lot = ts_lot if ts_lot != '전체' else ''
            st.markdown(f"<h4 style='color: #1E3A8A; margin-top: 15px; margin-bottom: 10px; font-weight: bold;'>설비 상태 모니터링 {f'(Lot: {disp_lot})' if disp_lot else ''}</h4>", unsafe_allow_html=True)
            
            df_eq = get_simulated_equipment_data(ts_lot)
            
            current_temp = df_eq['Temp'].iloc[-1]
            current_press = df_eq['Press'].iloc[-1]
            current_gas = df_eq['Gas'].iloc[-1]
            current_power = df_eq['Power'].iloc[-1]
            
            def get_status(val, ucl, lcl):
                if val > ucl or val < lcl: return "WARNING", "#EF4444", "rgba(239, 68, 68, 0.15)"
                return "OK", "#10B981", "rgba(16, 185, 129, 0.15)"

            t_stat, t_col, t_bg = get_status(current_temp, 420.0, 380.0)
            p_stat, p_col, p_bg = get_status(current_press, 5.0, 1.0)
            g_stat, g_col, g_bg = get_status(current_gas, 110.0, 90.0)
            pw_stat, pw_col, pw_bg = get_status(current_power, 650.0, 550.0)

            TEXT_SUB = "#4B5563"

            with st.container(border=False):
                img_b64 = get_image_base64("rmg_chamber.png")
                
                if img_b64:
                    img_tag = f"<img src='data:image/png;base64,{img_b64}' style='position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: contain; z-index: 1;' />"
                else:
                    img_tag = f"<div style='position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: #EF4444; font-weight: bold; z-index: 1; text-align: center;'> rmg_chamber.png 이미지를 찾을 수 없습니다.</div>"

                html_equipment = f"""
<div style="position: relative; height: 380px; width: 100%; background-color: transparent; overflow: hidden;">
{img_tag}
<svg style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 2; pointer-events: none;">
<line x1="82%" y1="12%" x2="53%" y2="12%" stroke="{g_col}" stroke-width="2" stroke-dasharray="4 3"/>
<circle cx="53%" cy="12%" r="5" fill="{g_col}"/>

<line x1="82%" y1="46%" x2="68%" y2="46%" stroke="{t_col}" stroke-width="2" stroke-dasharray="4 3"/>
<circle cx="68%" cy="46%" r="5" fill="{t_col}"/>

<line x1="82%" y1="73%" x2="61%" y2="73%" stroke="{pw_col}" stroke-width="2" stroke-dasharray="4 3"/>
<circle cx="61%" cy="73%" r="5" fill="{pw_col}"/>

<line x1="18%" y1="75%" x2="31%" y2="75%" stroke="{p_col}" stroke-width="2" stroke-dasharray="4 3"/>
<circle cx="31%" cy="75%" r="5" fill="{p_col}"/>
</svg>

<div style="position: absolute; top: 8%; right: 2%; z-index: 3; background: {g_bg}; border: 1.5px solid {g_col}; border-radius: 5px; padding: 4px 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
<div style="font-size: 9px; color: {TEXT_SUB}; font-family: sans-serif;">GAS FLOW</div>
<div style="font-size: 14px; font-weight: bold; color: {g_col};">{current_gas:.0f} sccm</div>
</div>
<div style="position: absolute; top: 42%; right: 2%; z-index: 3; background: {t_bg}; border: 1.5px solid {t_col}; border-radius: 5px; padding: 4px 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
<div style="font-size: 9px; color: {TEXT_SUB}; font-family: sans-serif;">TEMP</div>
<div style="font-size: 14px; font-weight: bold; color: {t_col};">{current_temp:.1f} °C</div>
</div>
<div style="position: absolute; top: 69%; right: 2%; z-index: 3; background: {pw_bg}; border: 1.5px solid {pw_col}; border-radius: 5px; padding: 4px 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
<div style="font-size: 9px; color: {TEXT_SUB}; font-family: sans-serif;">RF POWER</div>
<div style="font-size: 14px; font-weight: bold; color: {pw_col};">{current_power:.0f} W</div>
</div>
<div style="position: absolute; top: 71%; left: 2%; z-index: 3; background: {p_bg}; border: 1.5px solid {p_col}; border-radius: 5px; padding: 4px 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
<div style="font-size: 9px; color: {TEXT_SUB}; font-family: sans-serif;">PRESSURE</div>
<div style="font-size: 14px; font-weight: bold; color: {p_col};">{current_press:.2f} Torr</div>
</div>
</div>
"""
                st.markdown(html_equipment, unsafe_allow_html=True)

            st.markdown(f"<h4 style='color: #1E3A8A; margin-top: 20px; font-weight: bold;'>공정 변수 모니터링</h4>", unsafe_allow_html=True)
            
            def make_env_chart(df_in, col, title, unit, target, ucl, lcl, fmt='.2f'):
                fig = px.line(df_in, x='Time', y=col)
                fig.update_traces(line_color='#1E3A8A', line_width=2, hovertemplate=f'<b>시간:</b> %{{x|%H:%M}}<br><b>{title}:</b> %{{y:{fmt}}} {unit}<extra></extra>')
                
                fig.update_layout(
                    height=160, margin=dict(l=0, r=10, t=30, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(visible=False, showgrid=False), yaxis=dict(visible=False, hoverformat=fmt),
                    title=dict(text=f"<b>{title}</b> ({unit})", font=dict(size=12, color='#1E3A8A'), x=0.5, xanchor='center', y=0.95), 
                    showlegend=False, hovermode="x unified",
                    hoverlabel=dict(font=dict(size=18))
                )
                
                fig.add_hline(y=ucl, line_dash="dash", line_color="#EF4444", line_width=1.2, annotation_text=f"{ucl}{unit}", annotation_position="top left", annotation_font=dict(color="#EF4444"))
                fig.add_hline(y=lcl, line_dash="dash", line_color="#EF4444", line_width=1.2, annotation_text=f"{lcl}{unit}", annotation_position="bottom left", annotation_font=dict(color="#EF4444"))
                
                outliers = df_in[(df_in[col] > ucl) | (df_in[col] < lcl)]
                if not outliers.empty: fig.add_trace(go.Scatter(x=outliers['Time'], y=outliers[col], mode='markers', marker=dict(color='#EF4444', size=5), hoverinfo='skip', showlegend=False))
                return fig

            with st.container(border=True):
                r1_c1, r1_c2 = st.columns(2)
                with r1_c1: st.plotly_chart(make_env_chart(df_eq, 'Temp', 'Chamber Temp', '°C', 400.0, 420.0, 380.0, fmt='.1f'), use_container_width=True, config={'displayModeBar': False})
                with r1_c2: st.plotly_chart(make_env_chart(df_eq, 'Press', 'Pressure', 'Torr', 3.0, 5.0, 1.0, fmt='.2f'), use_container_width=True, config={'displayModeBar': False})
                
                r2_c1, r2_c2 = st.columns(2)
                with r2_c1: st.plotly_chart(make_env_chart(df_eq, 'Gas', 'Gas Flow', 'sccm', 100.0, 110.0, 90.0, fmt='.1f'), use_container_width=True, config={'displayModeBar': False})
                with r2_c2: st.plotly_chart(make_env_chart(df_eq, 'Power', 'RF Power', 'W', 600.0, 650.0, 550.0, fmt='.0f'), use_container_width=True, config={'displayModeBar': False})

            st.markdown(f"<h4 style='color: #1E3A8A; margin-top: 20px; font-weight: bold;'>작업 진행 및 수명</h4>", unsafe_allow_html=True)
            
            cur_equip = df_eq['Equip_Life'].iloc[-1]
            cur_shift = df_eq['Shift_Prog'].iloc[-1]
            maint_msg = df_eq['Maint_Status'].iloc[-1]

            st.caption(f"작업 진행률 ({cur_shift:.0f}%)")
            st.progress(cur_shift / 100)

            st.caption(f"장비 수명 ({100-cur_equip:.0f}%)")
            st.progress(1 - cur_equip / 100)

            st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
            if "즉시 교체" in maint_msg:
                st.error(maint_msg)
            elif "점검 필요" in maint_msg:
                st.warning(maint_msg)
            else:

                st.success(maint_msg)


