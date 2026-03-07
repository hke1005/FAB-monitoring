import streamlit as st

st.set_page_config(page_title="제조 결함 대시보드", page_icon="🏭", layout="wide")

st.markdown("""
<style>
/* 사이드바 메뉴 글자 크기 */
[data-testid="stSidebarNav"] a,
[data-testid="stSidebarNav"] span {
    font-size: 1.1rem !important;
}

/* 메뉴 간격 */
[data-testid="stSidebarNav"] li {
    margin-bottom: 0.5rem;
}

/* 사이드바 맨 위 제목 */
[data-testid="stSidebarNav"]::before {
    content: "용인 FAB Monitor";
    display: block;
    font-size: 1.7rem;
    font-weight: 700;
    margin: 0.5rem 0 1rem 0.3rem;
    padding-bottom: 0.8rem;
    border-bottom: 1px solid rgba(49, 51, 63, 0.2);
}
</style>
""", unsafe_allow_html=True)

pages = [
    st.Page("overview.py", title="Overview", default=True),
    st.Page("PC_tab.py", title="PC"),
    st.Page("RMG_tab.py", title="RMG"),
    st.Page("CBCMP_tab.py", title="CBCMP"),
]

pg = st.navigation(pages)
pg.run()
