"""이메일 보기·편집: 승인한 기사로 만든 초안을 고치고 저장하고 메일 클라이언트로 연다."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from newsclip import config
from newsclip.emailer import (
    CATEGORY_LABELS,
    Draft,
    EmailItem,
    Link,
    build_draft,
    build_eml,
    draft_from_dict,
    draft_to_dict,
    mailto_url,
    open_in_mail_client,
    render_html,
    render_text,
    save_eml,
)
from newsclip.review import review
from newsclip.store import APPROVED, Store

KEY = "email_draft"
PANEL_HEIGHT = 760  # 편집·미리보기 패널 높이(px)
settings = config.load()
store = Store()

st.title("✉️ 이메일 보기·편집")

approved = [c for c in review(settings, store).candidates if c.decision == APPROVED]
if not approved:
    st.info("승인한 기사가 없습니다. 후보 리스트에서 기사를 승인한 뒤 다시 오세요.")
    if st.button("← 후보 리스트"):
        st.switch_page("views/candidates.py")
    st.stop()

saved = store.get_kv(KEY)
existing = draft_from_dict(saved) if isinstance(saved, dict) else None
draft = build_draft(approved, settings.email, existing)


def _reset_widgets() -> None:
    for k in [k for k in st.session_state if str(k).startswith("em_")]:
        del st.session_state[k]


def _regenerate() -> None:
    _reset_widgets()
    store.set_kv(KEY, None)


head = st.columns([1, 1, 4])
head[0].button("← 후보 리스트", on_click=st.switch_page, args=("views/candidates.py",))
head[1].button(
    "🔁 초안 다시 만들기",
    on_click=_regenerate,
    help="편집한 내용을 버리고 승인 목록으로 처음부터 다시 만듭니다",
)

# 미리보기가 가로 스크롤 없이 보이도록 편집 영역은 좁게(1:2), 사이드바·여백도 줄인다
st.markdown(
    """
<style>
[data-testid="stSidebar"]{width:200px !important;min-width:200px !important}
[data-testid="stMainBlockContainer"]{padding-left:1.5rem;padding-right:1.5rem;max-width:none}
</style>
""",
    unsafe_allow_html=True,
)
edit_col, preview_col = st.columns([1, 2], gap="medium")

with edit_col:
    st.subheader("편집")
    # 편집·미리보기 두 패널을 같은 높이로 맞춘다 (편집 내용이 길면 패널 안에서 스크롤)
    with st.container(height=PANEL_HEIGHT, border=True):
        subject = st.text_input("제목", draft.subject, key="em_subject")
        sender = st.text_input(
            "보내는 사람", draft.sender, key="em_from", placeholder="홍길동 <me@example.com>"
        )
        recipients = st.text_input(
            "받는 사람", draft.recipients, key="em_to", placeholder="a@example.com, b@example.com"
        )
        intro = st.text_area("도입 문구", draft.intro, key="em_intro", height=80)
        items: list[EmailItem] = []
        for it in draft.items:
            label = CATEGORY_LABELS.get(it.category, it.category)
            with st.expander(f"[{label}] {it.title}", expanded=False):
                include = st.checkbox("메일에 포함", it.include, key=f"em_inc{it.article_id}")
                title = st.text_input("제목", it.title, key=f"em_t{it.article_id}")
                summary = st.text_area("요약", it.summary, key=f"em_s{it.article_id}", height=120)
                links_df = st.data_editor(
                    pd.DataFrame(
                        [vars(k) for k in it.links] or [{"title": "", "outlet": "", "url": ""}]
                    ),
                    num_rows="dynamic",
                    hide_index=True,
                    width="stretch",
                    key=f"em_l{it.article_id}",
                    column_config={
                        "title": st.column_config.TextColumn("링크 제목"),
                        "outlet": st.column_config.TextColumn("매체"),
                        "url": st.column_config.TextColumn("주소"),
                    },
                )
                links = [
                    Link(str(r["title"]), str(r["outlet"] or ""), str(r["url"]))
                    for _, r in links_df.iterrows()
                    if str(r["url"]).strip() and str(r["url"]) != "None"
                ]
                items.append(EmailItem(it.article_id, it.category, title, summary, links, include))
        outro = st.text_area("맺음 문구", draft.outro, key="em_outro", height=80)

current = Draft(subject, recipients, intro, outro, sender, items)

with preview_col:
    st.subheader("미리보기")
    with st.container(height=PANEL_HEIGHT, border=True):
        st.iframe(render_html(current), height="stretch")

st.divider()
actions = st.columns(5)
if actions[0].button("💾 저장", width="stretch"):
    store.set_kv(KEY, draft_to_dict(current))
    st.toast("저장했습니다.")

if actions[1].button(
    "📨 메일 창 열기",
    type="primary",
    width="stretch",
    help="기본 메일 클라이언트에서 새 메일 창(HTML 본문)을 엽니다",
):
    store.set_kv(KEY, draft_to_dict(current))
    try:
        path = save_eml(current, datetime.now().astimezone())
        open_in_mail_client(path)
        st.success(f"기본 메일 클라이언트로 열었습니다: `{path}`")
    except Exception as exc:  # noqa: BLE001 - 사용자에게 원인을 보여 주고 대안을 안내한다
        st.error(f"메일 클라이언트를 열지 못했습니다: {exc}. .eml 다운로드를 이용하세요.")

actions[2].link_button(
    "✉️ mailto (텍스트)",
    mailto_url(current),
    width="stretch",
    help="HTML 서식 없이 텍스트 본문만 담아 메일 창을 엽니다 (길면 잘림)",
)
actions[3].download_button(
    "⬇️ .eml",
    data=build_eml(current, datetime.now().astimezone()),
    file_name="clipping.eml",
    mime="message/rfc822",
    width="stretch",
)
actions[4].download_button(
    "⬇️ .html",
    data=render_html(current),
    file_name="clipping.html",
    mime="text/html",
    width="stretch",
)

with st.expander("텍스트 본문 보기 / 복사"):
    st.code(render_text(current), language=None)
