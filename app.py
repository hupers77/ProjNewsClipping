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
st.markdown(f"#### 📰 {SITE_TITLE}")
st.divider()

st.sidebar.divider()
st.sidebar.markdown(f"🔗 [GitHub]({GITHUB_URL})")

nav.run()
