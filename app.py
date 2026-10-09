"""ProjNewsClipping — Streamlit 진입점: `uv run streamlit run app.py`."""

import streamlit as st

from newsclip import buildinfo

SITE_TITLE = "뉴스 클리핑 사이트"
GITHUB_URL = "https://github.com/hupers77/ProjNewsClipping"
BLOG_URL = "https://blog.naver.com/hupers"

st.set_page_config(page_title=SITE_TITLE, page_icon="📰", layout="wide")

pages = [
    st.Page("views/candidates.py", title="후보 리스트", icon="📰", default=True),
    st.Page("views/email.py", title="이메일 보기·편집", icon="✉️"),
    st.Page("views/settings.py", title="환경 설정", icon="⚙️"),
    st.Page("views/guide.py", title="사용법", icon="📖"),
]
# 사이드바를 직접 구성하기 위해 기본 메뉴는 숨기고 st.page_link 로 메뉴를 그린다
nav = st.navigation(pages, position="hidden")

# 사이트 제목은 사이드바에만 둔다. 본문 상단은 여백·제목 크기를 줄여 공간을 확보한다
st.markdown(
    """
<style>
[data-testid="stMainBlockContainer"]{padding-top:2.5rem}
[data-testid="stMainBlockContainer"] h1{font-size:1.6rem;padding:.5rem 0}
[data-testid="stMainBlockContainer"] h2{font-size:1.35rem;padding:.5rem 0}
[data-testid="stMainBlockContainer"] h3{font-size:1.15rem;padding:.4rem 0}
.side-brand{font-size:1.45rem;font-weight:800;line-height:1.25;margin:.2rem 0 0}
.side-tag{font-size:.8rem;opacity:.65;margin:.15rem 0 0}
.side-label{font-size:.72rem;font-weight:700;letter-spacing:.08em;opacity:.55;margin:.4rem 0 .1rem}
.side-info{font-size:.85rem;line-height:1.8}
[data-testid="stSidebar"] hr{margin:.9rem 0}
</style>
""",
    unsafe_allow_html=True,
)
with st.sidebar:
    st.markdown(
        f'<div class="side-brand">📰 {SITE_TITLE}</div>'
        '<div class="side-tag">주요 뉴스를 모아 후보를 고르고 메일로 만듭니다</div>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown('<div class="side-label">메뉴</div>', unsafe_allow_html=True)
    for page in pages:
        st.page_link(page)
    st.divider()
    st.markdown('<div class="side-label">정보</div>', unsafe_allow_html=True)
    st.markdown(f"소스 보기 : [GitHub]({GITHUB_URL})  \n개발자 블로그 : [{BLOG_URL}]({BLOG_URL})")
    st.divider()
    st.caption(f"최종 개발 버전·일자 : {buildinfo.label()}")

nav.run()
