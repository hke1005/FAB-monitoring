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
        'Focus': gen
