"""ProjNewsClipping — Streamlit 진입점: `uv run streamlit run app.py`."""

import streamlit as st

SITE_TITLE = "뉴스 클리핑 사이트"
GITHUB_URL = "https://github.com/hupers77/ProjNewsClipping"

st.set_page_config(page_title=SITE_TITLE, page_icon="📰", layout="wide")

pages = [
    st.Page("views/candidates.py", title="후보 리스트", icon="📰", default=True),
    st.Page("views/email.py", title="이메일 보기·편집", icon="✉️"),
    st.Page("views/settings.py", title="환경 설정", icon="⚙️"),
    st.Page("views/guide.py", title="사용법", icon="📖"),
]
nav = st.navigation(pages)

# 모든 화면 상단 제목 (각 페이지 본문보다 먼저 그려진다)
# 사이트 제목(2.2rem)이 각 화면의 제목·소제목보다 항상 크도록 화면 제목 크기를 줄인다
st.markdown(
    """
<style>
.site-title{font-size:2.2rem;font-weight:700;line-height:1.3;margin:0 0 .25rem}
[data-testid="stMainBlockContainer"] h1{font-size:1.6rem;padding:.5rem 0}
[data-testid="stMainBlockContainer"] h2{font-size:1.35rem;padding:.5rem 0}
[data-testid="stMainBlockContainer"] h3{font-size:1.15rem;padding:.4rem 0}
</style>
""",
    unsafe_allow_html=True,
)
st.markdown(f'<div class="site-title">📰 {SITE_TITLE}</div>', unsafe_allow_html=True)
st.divider()

st.sidebar.divider()
st.sidebar.markdown(f"🔗 [GitHub]({GITHUB_URL})")

nav.run()
