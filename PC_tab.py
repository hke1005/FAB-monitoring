import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import datetime
import math

# 전역 변수 및 기본 설정
# ------------------------------------------------------------
# 좌표(맵) 그리기용 반지름(원본 코드 유지: 데이터 RADIUS 단위에 맞춘 값)
WAFER_RADIUS = 150000

# ✅ Defect Density 계산용 (실제 웨이퍼 반지름 15cm)
WAFER_RADIUS_CM = 15
WAFER_AREA_CM2 = math.pi * (WAFER_RADIUS_CM ** 2)  # 706.858...

st.set_page_config(page_title="PC 공정 모니터링", layout="wide")

st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 28px; color: #1E3A8A; font-weight: bold; }
    [data-testid="stMetricLabel"] { font-size: 16px; color: #4B5563; }
    div[data-testid="stMetric"] {
        background-color: #EFF6FF; padding: 15px; border-radius: 10px;
        border: 1px solid #BFDBFE; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    .stDataFrame { border: 1px solid #BFDBFE; border-radius: 5px; }
    
    /* 우측 담당자 카드 스타일링 */
    .manager-card {
        background-color: #1E3A8A; color: white; padding: 15px; border-radius: 10px;
        text-align: left; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .manager-card h4 { margin: 0; padding-bottom: 5px; color: white; }
    .manager-card p { margin: 0; font-size: 14px; opacity: 0.9; }

    /* 제목 아래 구분선 */
    .page-title-box {
        padding-bottom: 0px;
        margin-bottom: 0px;
        border-bottom: none;
    }

    /* 도넛 차트 박스 */
    .donut-container {
        background-color: #FAFAFA;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 20px 15px;
        box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.05);
    }
    
    /* 커스텀 스크롤바 (알림 리스트용) */
    .alert-box::-webkit-scrollbar { width: 6px; }
    .alert-box::-webkit-scrollbar-track { background: transparent; }
    .alert-box::-webkit-scrollbar-thumb { background: #D1D5DB; border-radius: 3px; }
    .alert-box::-webkit-scrollbar-thumb:hover { background: #9CA3AF; }

    /* ===== 핵심: 페이지 최상위 2열 레이아웃의 오른쪽 컬럼만 세로 구분선 ===== */
    div[data-testid="stHorizontalBlock"]:nth-of-type(1) > div:nth-child(2) {
        border-left: 3px solid #9CA3AF !important;   /* 더 진하게 */
        padding-left: 24px !important;
    }

    /* 내부 중첩 columns에는 세로선 제거 */
    div[data-testid="stHorizontalBlock"]:nth-of-type(1)
    div[data-testid="stHorizontalBlock"] > div:nth-child(2) {
        border-left: none !important;
        padding-left: 0 !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 데이터 로드 
# ==========================================
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
        '검출면적': 'DEFECT_AREA', '직경크기': 'SIZE_D', '중심거리': 'RADIUS',
        '방향각도': 'ANGLE',
        '영역잡음': 'PATCHNOISE', '점형지수': 'SPOTLIKENESS', '정렬정도': 'ALIGNRATIO',
        '상대강도': 'RELATIVEMAGNITUDE', '활성지수': 'ACTIVERATIO', '패치신호': 'PATCHDEFECTSIGNAL'
    }
    
    rename_dict = {k: v for k, v in KOR_TO_ENG.items() if k in df_raw.columns}
    df = df_raw.rename(columns=rename_dict).copy()
    
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
        if col not in df.columns:
            df[col] = 0.0
            
    df[radar_features_eng] = df[radar_features_eng].apply(pd.to_numeric, errors='coerce').fillna(0)
    
    return df

# ==========================================
# 장비 및 공정 환경 통합 데이터 생성 (Lot 별 시계열)
# ==========================================
@st.cache_data
def get_simulated_equipment_data(lot_id):
    seed_val = sum([ord(c) for c in str(lot_id)]) if lot_id != '전체' else 999
    np.random.seed(seed_val)
    
    steps = 60
    base_time = pd.Timestamp.now().floor('T') - pd.Timedelta(minutes=60)
    times = [base_time + pd.Timedelta(minutes=i) for i in range(steps)]
    
    def gen_with_outliers(base, std, outlier_range):
        data = np.random.normal(base, std, steps)
        outlier_idx = np.random.rand(steps) < 0.05 # 5% 확률 이상치
        data[outlier_idx] += np.random.choice(outlier_range, size=outlier_idx.sum())
        return data

    df_eq = pd.DataFrame({
        'Time': times,
        'Dose': gen_with_outliers(25.0, 0.1, [-1.5, 1.8]),
        'Focus': gen_with_outliers(0.00, 0.02, [-0.09, 0.11]),
        'CD': gen_with_outliers(45.0, 0.4, [-2.5, 3.0]),         # CD 선폭 (Target 45nm)
        'Particles': np.random.poisson(4, steps).astype(float),  # 파티클 수 (Poisson)
        'Temp': gen_with_outliers(22.0, 0.08, [-0.6, 0.7]),      # 챔버 온도 (22도)
        'Humidity': gen_with_outliers(45.0, 0.4, [-3.5, 4.0])    # 챔버 습도 (45%)
    })
    
    # 파티클 이상치 강제 주입
    df_eq.loc[np.random.choice(steps, 2), 'Particles'] += 12
    # 배치(Lot)별로 고유한 시프트 진척률과 장비 수명 사용률 생성
    if lot_id == '전체':
        shift_prog = 50.0
        equip_life = 45.0
    else:
        # seed_val 기반으로 배치마다 고정된 랜덤값 부여
        shift_prog = np.random.uniform(10.0, 99.0)
        equip_life = np.random.uniform(15.0, 96.0)

    # 장비 수명 사용률(%)에 따른 상태 메시지 결정
    if equip_life >= 85.0:
        maint_status = "장비 교체 필요"
    elif equip_life >= 70.0:
        maint_status = "점검 필요"
    else:
        maint_status = "정상 가동 중"

    # 시계열 끝에서 현재 값에 도달하도록 선형 배열 생성 (iloc[-1]에서 최종값을 씀)
    df_eq['Shift_Prog'] = np.linspace(max(0, shift_prog - 5), shift_prog, steps)
    df_eq['Equip_Life'] = np.linspace(max(0, equip_life - 2), equip_life, steps)
    df_eq['Maint_Status'] = maint_status
    # ============================================

    return df_eq

# ==========================================
# 메인 대시보드 렌더링
# ==========================================
df_raw = load_and_prep_data()

if df_raw.empty:
    st.title("PC 공정 모니터링")
    st.error("데이터가 없거나 불러오는데 실패했습니다. '반도체_결함_데이터_한글.csv' 파일을 확인해주세요.")
else:
    # ✅ PC 공정 + Class!=9 만 사용
    df = df_raw[(df_raw['Step_desc'].astype(str).str.upper() == 'PC') & (df_raw['Class'] != 9)].copy()
    
    if df.empty:
        st.title("PC 공정 모니터링")
        st.warning("PC 공정에 해당하는 데이터 중 결함유형이 9가 아닌 데이터가 존재하지 않습니다.")
    else:
        # ----------------------------------------------------
        # 기본 준비
        # ----------------------------------------------------
        radar_features_eng = ['PATCHNOISE', 'SPOTLIKENESS', 'ALIGNRATIO', 'RELATIVEMAGNITUDE', 'ACTIVERATIO', 'PATCHDEFECTSIGNAL']
        radar_features_kor = ['영역잡음', '점형지수', '정렬정도', '상대강도', '활성지수', '패치신호']
        
        radar_min = df[radar_features_eng].min()
        radar_max = df[radar_features_eng].max()
        radar_denom = (radar_max - radar_min).replace(0, 1)

        # ✅ wafer_summary = "웨이퍼당 결함수" 기반으로 만들고 density까지 추가
        wafer_summary = df.groupby(['Wafer_ID', 'Lot', 'Step_desc']).size().reset_index(name='결함수')
        wafer_summary["Defect_Density"] = wafer_summary["결함수"] / WAFER_AREA_CM2
        wafer_summary['상태 (Severity)'] = np.where(wafer_summary['결함수'] >= 65, '🔴 HIGH', '🟢 NORMAL')
        wafer_summary = wafer_summary.sort_values('결함수', ascending=False).reset_index(drop=True)

        # 경고 웨이퍼(전체 기준)
        high_defect_wafers_all = wafer_summary[wafer_summary['결함수'] >= 65].copy()

        # ----------------------------------------------------
        # ----------------------------------------------------
        # 상단 헤더/메인/사이드 통합 레이아웃
        # ----------------------------------------------------
        df_pc_all = df_raw[df_raw['Step_desc'].astype(str).str.upper() == 'PC'].copy()
        total_wafers_produced = df_pc_all['Wafer_ID'].nunique() if not df_pc_all.empty else 0
        class_9_cnt = len(df_pc_all[df_pc_all['Class'] == 9])
        non_class_9_cnt = len(df_pc_all[df_pc_all['Class'] != 9])
        total_defects_all = class_9_cnt + non_class_9_cnt
        class_9_ratio = (class_9_cnt / total_defects_all * 100) if total_defects_all > 0 else 0.0

        if high_defect_wafers_all.empty:
            status_indicator, priority_lot = "🟢", "없음"
        else:
            status_indicator = "🔴"
            priority_lot = (
                high_defect_wafers_all.groupby('Lot')
                .size().reset_index(name='count')
                .sort_values('count', ascending=False)
                .iloc[0]['Lot']
            )

        # ✅ 한 번만 2열로 나눈다
        main_col, side_col = st.columns([6.5, 3.5], gap="large")

       with main_col:
            st.title("PC 공정 모니터링")
            st.caption("PC 공정 | 결함 분포/경고 웨이퍼/공정 변수 모니터링")
            st.markdown("---")

        with side_col:
            st.markdown(f"""
            <div class="manager-card" style="margin-top: 12px; margin-bottom: 18px; padding: 12px 20px;">
                <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.2); padding-bottom: 10px; margin-bottom: 10px;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div style="width: 50px; height: 50px; border-radius: 50%; border: 3px solid #60A5FA; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: bold; position: relative; background-color: #1E3A8A;">
                            PC<div style="position: absolute; top: -6px; right: -6px; font-size: 14px;">{status_indicator}</div>
                        </div>
                        <div>
                            <div style="font-size: 12px; color: #93C5FD; margin-bottom: 2px;">생산 웨이퍼</div>
                            <div style="font-size: 18px; font-weight: bold;">{total_wafers_produced} 장</div>
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 16px; font-weight: bold;">담당자: 손영민</div>
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: flex-end;">
                    <div>
                        <div style="font-size: 11px; color: #93C5FD; margin-bottom: 2px;">가성 결함</div>
                        <div style="font-size: 15px; font-weight: bold;">{class_9_ratio:.1f}%</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 11px; color: #93C5FD; margin-bottom: 2px;">우선 점검 배치</div>
                        <div style="font-size: 15px; font-weight: bold; color: #FCD34D;">{priority_lot}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

       

        # ==========================================
        # ✅ 메인 영역
        # ==========================================
        with main_col:
            

            # ✅ KPI 위치를 "미리" 잡아두고, 아래에서 selection/filtered_df 만든 다음 채움
            kpi_container = st.container()

            # Row1 (알림 + 테이블)
            row1_left, row1_right = st.columns([1.2, 2.5], gap="large")

            # --- 오른쪽: Lot/wafer 선택 및 다이 사이즈 선택 ---
            with row1_right:
                st.markdown("**조회 조건 설정**")
                
                col_lot, col_die = st.columns(2)
                with col_lot:
                    lot_options = ['전체'] + sorted(list(wafer_summary['Lot'].astype(str).unique()))
                    
                    # 💡 추가: 세션 상태(Session State) 초기화
                    if 'lot_selectbox' not in st.session_state:
                        st.session_state.lot_selectbox = '전체'
                        
                    # 💡 수정: key를 부여하여 세션 상태와 드롭다운을 동기화
                    selected_lot = st.selectbox(
                        "배치번호(Lot):", 
                        lot_options, 
                        key="lot_selectbox"
                    )
                with col_die:
                    die_size_option = st.selectbox("다이 사이즈 선택:", ["100 mm²", "130 mm²"])

                # 💡 추가된 부분: 선택한 다이 사이즈에 따른 유효 면적 계산 (스크라이브 라인 반영)
                base_area_cm2 = 1.0 if die_size_option == "100 mm²" else 1.3
                chip_side_cm = np.sqrt(base_area_cm2)
                scribe_line_cm = 0.008 # 80um
                eff_chip_area_cm2 = (chip_side_cm + scribe_line_cm) ** 2

                # 💡 추가된 부분: 포아송 모델 적용 수율 계산 (미리 계산하여 저장)
                wafer_summary["Yield_Poisson"] = np.exp(-eff_chip_area_cm2 * wafer_summary["Defect_Density"]) * 100

                st.markdown("**Lot Data Breakdown (웨이퍼ID를 클릭하세요!)**")

                display_summary = (
                    wafer_summary[wafer_summary['Lot'].astype(str) == selected_lot].reset_index(drop=True)
                    if selected_lot != '전체'
                    else wafer_summary.copy()
                )

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
                    height=270, # 필터가 차지하는 공간을 위해 높이 약간 조정
                    use_container_width=True
                )

            # --- selection에 따라 filtered_df 결정 ---
            selected_wafer_id = None
            target_lot_for_eq = selected_lot
            
            if event.selection.rows:
                selected_wafer_id = display_summary.iloc[event.selection.rows[0]]['Wafer_ID']
                target_lot_for_eq = display_summary.iloc[event.selection.rows[0]]['Lot']
                filtered_df = df[df['Wafer_ID'] == selected_wafer_id].copy()
                chart_title_suffix = f" ({selected_wafer_id})"
            else:
                filtered_df = df[df['Lot'].astype(str) == selected_lot].copy() if selected_lot != '전체' else df.copy()
                chart_title_suffix = f" (Lot: {selected_lot})" if selected_lot != '전체' else " (PC 공정 전체)"

            filtered_df = filtered_df.reset_index(drop=True)
            filtered_df['Defect_ID'] = filtered_df.index

            # --- KPI 계산: “Lot면 평균 / Wafer면 해당 값” ---
            if filtered_df.empty:
                kpi_total_defects = 0
                kpi_density = 0.0
                yield_rate = 0.0
            else:
                # wafer별 결함수(=row count)
                wafer_counts = filtered_df.groupby("Wafer_ID").size()

                # wafer별 density
                wafer_density = wafer_counts / WAFER_AREA_CM2

                # 전체 결함 수 (선택범위 내)
                kpi_total_defects = int(wafer_counts.sum())

                # density: wafer 선택이면 해당 wafer, 아니면 wafer density 평균
                if selected_wafer_id is not None and selected_wafer_id in wafer_density.index:
                    kpi_density = float(wafer_density.loc[selected_wafer_id])
                else:
                    kpi_density = float(wafer_density.mean())

                # 💡 수정된 부분: 선택 여부에 따른 수율(Yield) 동적 할당
                if selected_wafer_id is not None and selected_wafer_id in wafer_density.index:
                    # 1. 특정 웨이퍼 단일 선택 시: 해당 웨이퍼의 수율
                    kpi_density = float(wafer_density.loc[selected_wafer_id])
                    yield_rate = float(wafer_summary.loc[wafer_summary['Wafer_ID'] == selected_wafer_id, 'Yield_Poisson'].iloc[0])
                else:
                    # 2. 특정 Lot 또는 전체 선택 시: 평균 수율
                    kpi_density = float(wafer_density.mean())
                    if selected_lot != '전체':
                        yield_rate = float(wafer_summary.loc[wafer_summary['Lot'].astype(str) == selected_lot, 'Yield_Poisson'].mean())
                    else:
                        yield_rate = float(wafer_summary['Yield_Poisson'].mean())

            # 경고 웨이퍼 수: Lot 선택이면 해당 Lot 기준으로 보여주기
            if selected_wafer_id is not None:
                # 선택 wafer의 Lot을 기준으로 경고 count
                wafer_lot = wafer_summary.loc[wafer_summary['Wafer_ID'] == selected_wafer_id, 'Lot']
                wafer_lot = str(wafer_lot.iloc[0]) if not wafer_lot.empty else "전체"
                warn_view = high_defect_wafers_all[high_defect_wafers_all['Lot'].astype(str) == wafer_lot]
                warn_count = len(warn_view)
            else:
                if selected_lot == "전체":
                    warn_count = len(high_defect_wafers_all)
                else:
                    warn_view = high_defect_wafers_all[high_defect_wafers_all['Lot'].astype(str) == str(selected_lot)]
                    warn_count = len(warn_view)

            # --- KPI 출력 (상단 고정 위치) ---
            with kpi_container:
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric(label="결함 수", value=f"{kpi_total_defects:,} 건")
                kpi2.metric(label="수율", value=f"{yield_rate:.2f} %")
                kpi3.metric(label="Defect Density", value=f"{kpi_density:.5f} ea/cm²")
                kpi4.metric(label="경고 웨이퍼 수", value=f"{warn_count} 장")

            st.markdown("---")

            # --- 왼쪽: 알림(결함 + 설비 파라미터 이상 통합) ---
            with row1_left:
                st.write("")
                st.markdown("""
                <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;'>
                    <div style='font-weight: 800; font-size: 16px; color: #1F2937;'><span style='margin-right: 8px;'>🚨</span> 실시간 알림 내역</div>
                    <div style='color: #9CA3AF; font-size: 13px;'>방금 전</div>
                </div>
                """, unsafe_allow_html=True)

                # 버튼 클릭 시 실행될 콜백 함수 (선택된 Lot를 세션 상태에 업데이트)
                def set_selected_lot(target_lot):
                    st.session_state.lot_selectbox = target_lot

                # 스크롤 가능한 Streamlit 컨테이너 생성
                alert_container = st.container(height=315, border=True)
                with alert_container:
                    alert_count = 0
                    
                    # ----------------------------------------------------
                    # 1. 결함 다량 발생 감지 알림
                    # ----------------------------------------------------
                    if not high_defect_wafers_all.empty:
                        lot_warning_counts = (
                            high_defect_wafers_all.groupby('Lot').size()
                            .reset_index(name='경고웨이퍼수')
                            .sort_values('경고웨이퍼수', ascending=False)
                        )
                        for idx, row_warn in lot_warning_counts.iterrows():
                            lot_num = row_warn['Lot']
                            warn_cnt = row_warn['경고웨이퍼수']
                            alert_count += 1
                            
                            a_col1, a_col2, a_col3 = st.columns([1, 4, 1.5], vertical_alignment="center")
                            with a_col1:
                                st.markdown(f"<div style='width: 32px; height: 32px; background-color: #FA5C5C; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-top: 5px;'>{warn_cnt}</div>", unsafe_allow_html=True)
                            with a_col2:
                                st.markdown(f"<div style='font-weight: bold; font-size: 13px; margin-bottom: 2px; color: #374151;'>결함 다량 발생 감지</div><div style='font-size: 12px; color: #6B7280;'>배치: <b>{lot_num}</b> | 위험 {warn_cnt}장</div>", unsafe_allow_html=True)
                            with a_col3:
                                st.button("조회", key=f"btn_def_{lot_num}", on_click=set_selected_lot, args=(lot_num,), use_container_width=True)
                            
                            st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #F3F4F6;'>", unsafe_allow_html=True)
                    
                    # ----------------------------------------------------
                    # 2. 공정 파라미터 (Dose, Focus, CD 등) 이상 감지 알림
                    # ----------------------------------------------------
                    unique_lots = df['Lot'].dropna().unique() if not df.empty else []
                    for lot_num in unique_lots:
                        # 해당 배치의 장비 데이터 로드
                        eq_data = get_simulated_equipment_data(lot_num)
                        
                        # 각 변수의 현재(마지막) 값 추출
                        cur_dose = eq_data['Dose'].iloc[-1]
                        cur_focus = eq_data['Focus'].iloc[-1]
                        cur_cd = eq_data['CD'].iloc[-1]
                        cur_p = eq_data['Particles'].iloc[-1]
                        cur_t = eq_data['Temp'].iloc[-1]
                        cur_h = eq_data['Humidity'].iloc[-1]
                        
                        # 각 변수별 관리 한계(UCL/LCL) 초과 여부 확인
                        anomalies = []
                        if cur_dose > 26.0 or cur_dose < 24.0: anomalies.append(('D', 'Dose', f"{cur_dose:.1f}", 'mJ'))
                        if cur_focus > 0.08 or cur_focus < -0.08: anomalies.append(('F', 'Focus', f"{cur_focus:.3f}", 'μm'))
                        if cur_cd > 47.0 or cur_cd < 43.0: anomalies.append(('C', 'CD', f"{cur_cd:.1f}", 'nm'))
                        if cur_p > 15: anomalies.append(('P', '파티클', f"{cur_p:.0f}", 'ea'))
                        if cur_t > 22.5 or cur_t < 21.5: anomalies.append(('T', '온도', f"{cur_t:.1f}", '°C'))
                        if cur_h > 48.0 or cur_h < 42.0: anomalies.append(('H', '습도', f"{cur_h:.1f}", '%'))
                        
                        # 이상이 1건일 경우 (초성 표시)
                        if len(anomalies) == 1:
                            alert_count += 1
                            initial, param_name, val_str, unit = anomalies[0]
                            
                            a_col1, a_col2, a_col3 = st.columns([1, 4, 1.5], vertical_alignment="center")
                            with a_col1:
                                st.markdown(f"<div style='width: 32px; height: 32px; background-color: #EF4444; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-top: 5px;'>{initial}</div>", unsafe_allow_html=True)
                            with a_col2:
                                st.markdown(f"<div style='font-weight: bold; font-size: 13px; margin-bottom: 2px; color: #374151;'>공정 변수 이상 감지</div><div style='font-size: 12px; color: #6B7280;'>배치: <b>{lot_num}</b> | {param_name}: <span style='color:#EF4444; font-weight:bold;'>{val_str} {unit}</span></div>", unsafe_allow_html=True)
                            with a_col3:
                                st.button("조회", key=f"btn_eq_{lot_num}_{initial}", on_click=set_selected_lot, args=(lot_num,), use_container_width=True)
                            
                            st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #F3F4F6;'>", unsafe_allow_html=True)
                            
                        # 이상이 2건 이상일 경우 (⚠️ 아이콘과 함께 묶어서 표시)
                        elif len(anomalies) >= 2:
                            alert_count += 1
                            detail_str = ", ".join([f"{p}: <span style='color:#EF4444; font-weight:bold;'>{v}{u}</span>" for i, p, v, u in anomalies])
                            
                            a_col1, a_col2, a_col3 = st.columns([1, 4, 1.5], vertical_alignment="center")
                            with a_col1:
                                st.markdown(f"<div style='width: 32px; height: 32px; background-color: #EF4444; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 16px; margin-top: 5px;'>⚠️</div>", unsafe_allow_html=True)
                            with a_col2:
                                st.markdown(f"<div style='font-weight: bold; font-size: 13px; margin-bottom: 2px; color: #374151;'>공정 변수 {len(anomalies)}건 동시 이탈</div><div style='font-size: 12px; color: #6B7280;'>배치: <b>{lot_num}</b> | {detail_str}</div>", unsafe_allow_html=True)
                            with a_col3:
                                st.button("조회", key=f"btn_eq_{lot_num}_multi", on_click=set_selected_lot, args=(lot_num,), use_container_width=True)
                            
                            st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #F3F4F6;'>", unsafe_allow_html=True)

                    # ----------------------------------------------------
                    # 3. 알림이 하나도 없을 경우의 처리
                    # ----------------------------------------------------
                    if alert_count == 0:
                        st.markdown("<div style='display: flex; align-items: center; justify-content: center; height: 100%; color: #10B981; font-weight: bold;'>현재 공정에 발생한 경고 알림이 없습니다.</div>", unsafe_allow_html=True)

            # --- 공통: 색상맵 준비 ---
            if not filtered_df.empty:
                filtered_df['Class_str'] = filtered_df['Class'].astype(str)
                unique_classes = sorted(filtered_df['Class'].unique())
                color_map = {str(cls): px.colors.qualitative.Plotly[i % len(px.colors.qualitative.Plotly)] for i, cls in enumerate(unique_classes)}
            else:
                color_map = {}

            st.markdown("<br>", unsafe_allow_html=True)
            
            # 상위 제목 코드
            st.markdown(f"<h4 style='color: #1E3A8A; margin-bottom: 10px; font-weight: bold;'>🔍 결함 심층 분석 {chart_title_suffix}</h4>", unsafe_allow_html=True)

            # 세 개의 차트를 모두 감싸는 '통합 컨테이너(박스)' 생성
            with st.container(border=True):
                # 컬럼을 박스 안으로 이동시켰습니다.
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
                            height=400
                        )
                        fig_map.add_shape(
                            type="circle",
                            x0=-WAFER_RADIUS, y0=-WAFER_RADIUS,
                            x1=WAFER_RADIUS, y1=WAFER_RADIUS,
                            line_color="#9CA3AF", line_width=2
                        )
                        fig_map.update_layout(
                            xaxis=dict(visible=False, range=[-WAFER_RADIUS*1.1, WAFER_RADIUS*1.1]),
                            yaxis=dict(visible=False, range=[-WAFER_RADIUS*1.1, WAFER_RADIUS*1.1], scaleanchor="x", scaleratio=1),
                            margin=dict(l=0, r=0, t=10, b=0),
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5)
                        )
                        map_event = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun", selection_mode="points")
                    else:
                        map_event = None
                        st.info("해당 조건의 맵 데이터가 없습니다.")

                with row2_mid:
                    st.markdown(f"**결함 특성화 지표** {chart_title_suffix}")
                    if map_event and map_event.selection.points:
                        sel_row = filtered_df[filtered_df['Defect_ID'] == map_event.selection.points[0]["customdata"][0]]
                        radar_vals = ((sel_row[radar_features_eng].values[0] - radar_min) / radar_denom).tolist()
                        st.caption(f"👆 선택된 개별 결함의 프로필 (유형: {sel_row['Class_str'].values[0]})")
                    else:
                        radar_vals = ((filtered_df[radar_features_eng].mean() - radar_min) / radar_denom).tolist() if not filtered_df.empty else [0]*len(radar_features_eng)
                        
                    fig_radar = go.Figure(data=go.Scatterpolar(
                        r=radar_vals + [radar_vals[0]],
                        theta=radar_features_kor + [radar_features_kor[0]],
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
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)'
                    )
                    st.plotly_chart(fig_radar, use_container_width=True)

                with row2_right:
                    if not filtered_df.empty:
                        st.markdown(f"**결함 유형 통계** {chart_title_suffix}")
                        class_counts = filtered_df['Class'].value_counts().reset_index()
                        class_counts.columns = ['Class', 'Count']
                        class_counts['Class_str'] = class_counts['Class'].astype(str)
                        class_counts['Percent'] = (class_counts['Count'] / class_counts['Count'].sum()) * 100
                        class_counts = class_counts.sort_values('Percent', ascending=False).reset_index(drop=True)
                        
                        # 💡 수정: 도넛 차트 개별 박스 제거, 코드를 바깥으로 한 칸 내어쓰기(Un-indent) 함
                        fig_donut = go.Figure(go.Pie(
                            labels=class_counts['Class_str'],
                            values=class_counts['Count'],
                            hole=0.65,
                            textinfo='none',
                            hovertemplate="유형 %{label}<br>%{value}건 (%{percent})<extra></extra>",
                            marker=dict(colors=[color_map[cls] for cls in class_counts['Class_str']])
                        ))
                        
                        max_percent = class_counts['Percent'].max()

                        fig_donut.update_layout(
                            showlegend=False,
                            margin=dict(l=10, r=10, t=10, b=0),
                            height=200,
                            annotations=[dict(
                                text=f"{max_percent:.0f}%", 
                                x=0.5, y=0.5, font_size=32, showarrow=False, font=dict(color="#374151") 
                            )],
                            paper_bgcolor='rgba(0,0,0,0)',
                            plot_bgcolor='rgba(0,0,0,0)',
                            hoverlabel=dict(font_size=18, font_family="sans-serif")
                        )
                        st.plotly_chart(fig_donut, use_container_width=True)
                        
                        legend_html = "<div style='display:flex; flex-direction:column; padding: 10px 15px 5px 15px;'>"
                        for i, row in class_counts.head(5).iterrows(): 
                            legend_html += f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;'><div style='display:flex; align-items:center;'><span style='color:{color_map[row['Class_str']]}; font-size:16px; margin-right:10px;'>●</span><span style='color:#4B5563; font-size:14px; font-weight:bold;'>유형 {row['Class_str']}</span></div><div style='font-weight:600; color:#1F2937; font-size:14px;'>{row['Percent']:.0f}%</div></div>"
                        
                        if len(class_counts) > 5:
                            legend_html += f"<div style='text-align:right; font-size:12px; color:#9CA3AF; margin-top:2px;'>+ 외 {len(class_counts)-5}개 유형</div>"
                        st.markdown(legend_html + "</div>", unsafe_allow_html=True)

        # ==========================================
        # (이 밑으로는 우측 사이드바 코드 with side_col: 가 이어집니다)

        # ==========================================
        # ✅ 우측 사이드바
        # ==========================================
        # ==========================================
        # ✅ 우측 사이드바
        # ==========================================
        # ==========================================
        # ✅ 우측 사이드바
        # ==========================================
        with side_col:
            # 💡 제목에도 현재 기준이 되는 Lot 번호가 표시되도록 수정
            st.markdown(
                f"<h4 style='color: #1E3A8A; margin-top: 15px; margin-bottom: 10px; font-weight: bold;'>노광 변수 모니터링 (Lot: {target_lot_for_eq})</h4>",
                unsafe_allow_html=True
            )
            
            # 💡 선택된 웨이퍼의 소속 Lot 번호로 장비 데이터 호출!
            df_eq = get_simulated_equipment_data(target_lot_for_eq)
            
            current_dose = df_eq['Dose'].iloc[-1]
            current_focus = df_eq['Focus'].iloc[-1]
            
            
            dose_status = "OK" if abs(current_dose - 25.0) <= 1.0 else "WARNING"
            dose_color = "#10B981" if dose_status == "OK" else "#EF4444"
            dose_bg_rect = "rgba(16, 185, 129, 0.15)" if dose_status == "OK" else "rgba(239, 68, 68, 0.15)"
            
            focus_status = "NOMINAL" if abs(current_focus) <= 0.08 else "WARNING"
            focus_color = "#10B981" if focus_status == "NOMINAL" else "#EF4444"
            focus_bg_rect = "rgba(16, 185, 129, 0.15)" if focus_status == "NOMINAL" else "rgba(239, 68, 68, 0.15)"

            TEXT_MAIN = "#1E3A8A"
            TEXT_SUB = "#4B5563"

            with st.container(border=True):
                col_eq, col_chart = st.columns([1, 1.4], gap="small")
                
                with col_eq:
                    svg_equipment = f"""<div style="background-color: transparent; height: 380px; width: 100%; display: flex; justify-content: center; align-items: center;">
<svg viewBox="0 0 250 400" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
<rect x="85" y="20" width="30" height="20" rx="3" fill="#94A3B8"/>
<circle cx="100" cy="40" r="10" fill="#E0F2FE" filter="drop-shadow(0 0 8px #60A5FA)"/>
<polygon points="100,40 50,140 150,140" fill="url(#beamGrad1)"/>
<polygon points="50,150 100,330 150,150" fill="url(#beamGrad2)"/>
<defs>
<linearGradient id="beamGrad1" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="rgba(96, 165, 250, 0.4)"/><stop offset="100%" stop-color="rgba(96, 165, 250, 0.05)"/></linearGradient>
<linearGradient id="beamGrad2" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="rgba(96, 165, 250, 0.15)"/><stop offset="100%" stop-color="rgba(96, 165, 250, 0.7)"/></linearGradient>
</defs>
<rect x="20" y="140" width="160" height="10" rx="2" fill="#6B7280"/>
<rect x="40" y="143" width="120" height="4" fill="#D1D5DB"/>
<path d="M 30 170 L 170 170 L 170 290 L 30 290 Z" fill="none" stroke="#9CA3AF" stroke-width="2"/>
<rect x="40" y="180" width="120" height="30" rx="15" fill="#9CA3AF"/>
<rect x="50" y="220" width="100" height="40" rx="5" fill="#6B7280"/>
<rect x="60" y="270" width="80" height="15" rx="7" fill="#9CA3AF"/>
<ellipse cx="100" cy="345" rx="75" ry="12" fill="#6B7280"/>
<ellipse cx="100" cy="340" rx="65" ry="9" fill="#475569"/>
<rect x="80" y="345" width="40" height="35" fill="#9CA3AF"/>
<text x="40" y="135" fill="{TEXT_MAIN}" font-size="9" font-family="sans-serif" text-anchor="end">MASK</text>
<text x="25" y="235" fill="{TEXT_MAIN}" font-size="9" font-family="sans-serif" text-anchor="end">LENS</text>
<text x="25" y="343" fill="{TEXT_MAIN}" font-size="9" font-family="sans-serif" text-anchor="end">WAFER</text>
<g transform="translate(150, 20)">
<rect x="0" y="0" width="95" height="45" rx="5" fill="{dose_bg_rect}" stroke="{dose_color}" stroke-width="1.5"/>
<text x="8" y="15" fill="{TEXT_SUB}" font-size="9" font-family="sans-serif">DOSE</text>
<text x="8" y="33" fill="{dose_color}" font-size="16" font-weight="bold" font-family="sans-serif">{current_dose:.1f} mJ</text>
</g>
<line x1="115" y1="40" x2="150" y2="40" stroke="{dose_color}" stroke-width="1.5"/>
<circle cx="115" cy="40" r="3" fill="{dose_color}"/>
<g transform="translate(150, 310)">
<rect x="0" y="0" width="95" height="45" rx="5" fill="{focus_bg_rect}" stroke="{focus_color}" stroke-width="1.5"/>
<text x="8" y="15" fill="{TEXT_SUB}" font-size="9" font-family="sans-serif">FOCUS</text>
<text x="8" y="33" fill="{focus_color}" font-size="16" font-weight="bold" font-family="sans-serif">{current_focus:+.2f} μm</text>
</g>
<line x1="100" y1="340" x2="150" y2="330" stroke="{focus_color}" stroke-width="1.5"/>
<circle cx="100" cy="340" r="3" fill="{focus_color}"/>
</svg></div>"""
                    st.markdown(svg_equipment, unsafe_allow_html=True)
                    
                with col_chart:
                    outliers_d = df_eq[(df_eq['Dose'] > 26.0) | (df_eq['Dose'] < 24.0)]
                    outliers_f = df_eq[(df_eq['Focus'] > 0.08) | (df_eq['Focus'] < -0.08)]
                    
                    fig_dose = px.line(df_eq, x='Time', y='Dose')
                    fig_dose.update_traces(
                        line_color='#1E3A8A', line_width=2.5,
                        hovertemplate='<b>시간:</b> %{x|%H:%M}<br><b>Dose:</b> %{y:.2f} mJ<extra></extra>'
                    )
                    fig_dose.update_layout(
                        height=190, margin=dict(l=0, r=10, t=30, b=10),
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        xaxis=dict(visible=False, showgrid=False),
                        yaxis=dict(visible=False, showgrid=False, range=[22.5, 27.5]),
                        title=dict(text="Dose Trend (UCL/LCL)", font=dict(size=14, color='#1E3A8A', family="sans-serif"), x=0.5, xanchor='center', y=0.95),
                        showlegend=False, hovermode="x unified",
                        # 💡 Dose 툴팁 크기 키우기
                        hoverlabel=dict(font_size=18, font_family="sans-serif")
                    )
                    fig_dose.add_hline(y=26.0, line_dash="dash", line_color="#EF4444", line_width=1.5, annotation_text="UCL", annotation_position="top left", annotation_font_size=10, annotation_font_color="#EF4444")
                    fig_dose.add_hline(y=25.0, line_dash="dot", line_color="#10B981", line_width=1.5, annotation_text="TGT", annotation_position="top left", annotation_font_size=10, annotation_font_color="#10B981")
                    fig_dose.add_hline(y=24.0, line_dash="dash", line_color="#EF4444", line_width=1.5, annotation_text="LCL", annotation_position="bottom left", annotation_font_size=10, annotation_font_color="#EF4444")
                    if not outliers_d.empty:
                        fig_dose.add_trace(go.Scatter(x=outliers_d['Time'], y=outliers_d['Dose'], mode='markers', marker=dict(color='#EF4444', size=7), hoverinfo='skip', showlegend=False))
                    
                    fig_focus = px.line(df_eq, x='Time', y='Focus')
                    fig_focus.update_traces(
                        line_color='#1E3A8A', line_width=2.5,
                        hovertemplate='<b>시간:</b> %{x|%H:%M}<br><b>Focus:</b> %{y:.5f} μm<extra></extra>'
                    )
                    fig_focus.update_layout(
                        height=190, margin=dict(l=0, r=10, t=30, b=10),
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        xaxis=dict(visible=False, showgrid=False),
                        yaxis=dict(visible=False, showgrid=False, range=[-0.15, 0.15], hoverformat='.5f', tickformat='.5f'),
                        title=dict(text="Focus Trend (UCL/LCL)", font=dict(size=14, color='#1E3A8A', family="sans-serif"), x=0.5, xanchor='center', y=0.95),
                        showlegend=False, hovermode="x unified",
                        # 💡 Focus 툴팁 크기 키우기
                        hoverlabel=dict(font_size=18, font_family="sans-serif")
                    )
                    fig_focus.add_hline(y=0.08, line_dash="dash", line_color="#EF4444", line_width=1.5, annotation_text="UCL", annotation_position="top left", annotation_font_size=10, annotation_font_color="#EF4444")
                    fig_focus.add_hline(y=0.00, line_dash="dot", line_color="#10B981", line_width=1.5, annotation_text="TGT", annotation_position="top left", annotation_font_size=10, annotation_font_color="#10B981")
                    fig_focus.add_hline(y=-0.08, line_dash="dash", line_color="#EF4444", line_width=1.5, annotation_text="LCL", annotation_position="bottom left", annotation_font_size=10, annotation_font_color="#EF4444")
                    if not outliers_f.empty:
                        fig_focus.add_trace(go.Scatter(x=outliers_f['Time'], y=outliers_f['Focus'], mode='markers', marker=dict(color='#EF4444', size=7), hoverinfo='skip', showlegend=False))
                    
                    st.plotly_chart(fig_dose, use_container_width=True, config={'displayModeBar': False})
                    st.markdown("<div style='margin-top: -15px;'></div>", unsafe_allow_html=True)
                    st.plotly_chart(fig_focus, use_container_width=True, config={'displayModeBar': False})

            # 공정 환경 모니터링
            st.markdown(f"<h4 style='color: #1E3A8A; margin-top: 25px; font-weight: bold;'>환경 변수 모니터링</h4>", unsafe_allow_html=True)
            
            def make_env_chart(df_in, col, title, unit, target, ucl, lcl, fmt='.2f'):
                fig = px.line(df_in, x='Time', y=col)
                fig.update_traces(
                    line_color='#1E3A8A', line_width=2,
                    hovertemplate=f'<b>시간:</b> %{{x|%H:%M}}<br><b>{title}:</b> %{{y:{fmt}}} {unit}<extra></extra>'
                )
                fig.update_layout(
                    height=160, margin=dict(l=0, r=10, t=30, b=10),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(visible=False, showgrid=False),
                    yaxis=dict(visible=False, hoverformat=fmt),
                    # 💡 수정: 폰트 크기 13으로 증가, xanchor='center'로 완벽한 중앙 정렬
                    title=dict(text=f"{title} ({unit})", font=dict(size=13, color='#1E3A8A', family="sans-serif"), x=0.5, xanchor='center', y=0.95),
                    showlegend=False, hovermode="x unified",
                    # 💡 여기에 hoverlabel 속성을 추가합니다! (글씨 크기 15)
                    hoverlabel=dict(font_size=18, font_family="sans-serif") 
                )
                
                fig.add_hline(y=ucl, line_dash="dash", line_color="#EF4444", line_width=1.2, annotation_text="UCL", annotation_position="top left")
                fig.add_hline(y=target, line_dash="dot", line_color="#10B981", line_width=1.0)
                fig.add_hline(y=lcl, line_dash="dash", line_color="#EF4444", line_width=1.2, annotation_text="LCL", annotation_position="bottom left")
                
                # 💡 추가: UCL 이상, LCL 이하인 이상치(Outlier)에 빨간 점 찍기
                outliers = df_in[(df_in[col] > ucl) | (df_in[col] < lcl)]
                if not outliers.empty:
                    fig.add_trace(go.Scatter(
                        x=outliers['Time'], 
                        y=outliers[col], 
                        mode='markers', 
                        marker=dict(color='#EF4444', size=7), 
                        hoverinfo='skip', 
                        showlegend=False
                    ))
                    
                return fig

            # --- 공정 환경 모니터링 컨테이너 ---
            with st.container(border=True):
                env_c1, env_c2 = st.columns(2)
                with env_c1:
                    st.plotly_chart(make_env_chart(df_eq, 'CD', 'CD X-bar', 'nm', 45.0, 47.0, 43.0), use_container_width=True, config={'displayModeBar': False})
                    st.plotly_chart(make_env_chart(df_eq, 'Temp', 'Chamber Temp', '°C', 22.0, 22.5, 21.5), use_container_width=True, config={'displayModeBar': False})
                with env_c2:
                    st.plotly_chart(make_env_chart(df_eq, 'Particles', 'Particles', 'ea', 5, 15, 0, fmt='.0f'), use_container_width=True, config={'displayModeBar': False})
                    st.plotly_chart(make_env_chart(df_eq, 'Humidity', 'Chamber Humid', '%', 45.0, 48.0, 42.0), use_container_width=True, config={'displayModeBar': False})

            # =============== 💡 수정된 부분: 박스 바깥으로 완전히 뺐습니다! ===============
            st.markdown(f"<h4 style='color: #1E3A8A; margin-top: 25px; margin-bottom: 10px; font-weight: bold;'>작업 진행 및 장비수명</h4>", unsafe_allow_html=True)
            
            with st.container(border=True):
                cur_equip = df_eq['Equip_Life'].iloc[-1]
                cur_shift = df_eq['Shift_Prog'].iloc[-1]
                maint_msg = df_eq['Maint_Status'].iloc[-1]

                st.caption(f"<span style='font-size: 14px; color: #4B5563; font-weight: bold;'>작업 진행률 ({cur_shift:.0f}%)</span>", unsafe_allow_html=True)
                st.progress(cur_shift / 100)

                st.caption(f"<span style='font-size: 14px; color: #4B5563; font-weight: bold;'>장비 수명 ({100-cur_equip:.0f}%)</span>", unsafe_allow_html=True)
                st.progress((100 - cur_equip) / 100) # 장비 수명이 남은 비율로 정상 계산되도록 수정

                st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
                if "장비 교체 필요" in maint_msg:
                    st.error(f"**{maint_msg}**")
                elif "점검 필요" in maint_msg:
                    st.warning(f"**{maint_msg}**")
                else:

                    st.success(f"**{maint_msg}**")


