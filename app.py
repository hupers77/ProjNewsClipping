"""ProjNewsClipping — Streamlit 진입점: `uv run streamlit run app.py`."""

import streamlit as st

st.set_page_config(page_title="뉴스 클리핑", page_icon="📰", layout="wide")

pages = [
    st.Page("views/candidates.py", title="후보 리스트", icon="📰", default=True),
    st.Page("views/email.py", title="이메일 보기·편집", icon="✉️"),
    st.Page("views/settings.py", title="환경 설정", icon="⚙️"),
    st.Page("views/guide.py", title="사용법", icon="📖"),
]
st.navigation(pages).run()
