"""후보 리스트: 수집 · 검토(승인/거절) · 이메일 만들기."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import streamlit as st

from newsclip import config
from newsclip.collector import collect
from newsclip.emailer import CATEGORY_LABELS
from newsclip.review import Candidate, review
from newsclip.store import APPROVED, PENDING, REJECTED, Store

settings = config.load()
store = Store()

st.title("📰 후보 리스트")


def _decide(c: Candidate, decision: str) -> None:
    """대표 기사에만 결정을 기록하고 같은 묶음의 나머지는 미결정으로 둔다."""
    store.set_decision(c.ids, PENDING)
    if decision:
        store.set_decision([c.rep.id], decision)


def _local(dt: datetime) -> str:
    return dt.astimezone().strftime("%m-%d %H:%M")


top = st.columns([1.3, 1.3, 3])
if top[0].button("🔄 지금 수집", type="primary", width="stretch"):
    with st.status("기사를 수집하는 중…", expanded=True) as status:
        report = collect(settings, store, progress=st.write)
        store.purge_older_than(datetime.now(UTC) - timedelta(days=max(30, settings.collect.days)))
        status.update(
            label=f"새 기사 {report.new_total}건 수집 (본문 추출 {report.content_fetched}건)",
            state="complete",
        )
    bad = [r for r in report.results if r.error]
    for r in bad:
        st.warning(f"{r.source}: {r.error}")

result = review(settings, store)
approved = [c for c in result.candidates if c.decision == APPROVED]

if approved:  # 승인된 기사가 있어 이메일을 만들 수 있으면 녹색으로 강조
    st.markdown(
        "<style>.st-key-make_email button{background:#1f9d55;border-color:#1f9d55;color:#fff}"
        ".st-key-make_email button:hover{background:#17804a;border-color:#17804a;color:#fff}"
        "</style>",
        unsafe_allow_html=True,
    )
if top[1].button(
    f"✉️ 이메일 만들기 ({len(approved)})",
    key="make_email",
    disabled=not approved,
    width="stretch",
):
    st.switch_page("views/email.py")
top[2].caption(
    f"최근 {settings.collect.days}일 · 기사 묶음 {len(result.candidates)}건 · "
    f"제외 {len(result.excluded)}건 · 승인 {len(approved)}건"
)

with st.container(border=True):
    f = st.columns([2, 2, 1.4, 1.4])
    cats = sorted({c.rep.category for c in result.candidates})
    sel_cats = f[0].multiselect(
        "분류", cats, default=cats, format_func=lambda k: CATEGORY_LABELS.get(k, k)
    )
    state = f[1].radio(
        "상태", ["전체", "미검토", "승인", "거절"], horizontal=True, label_visibility="visible"
    )
    only_cand = f[2].toggle("후보만 보기", value=True, help="점수 기준에 못 미친 기사는 숨깁니다")
    show_excl = f[3].toggle("제외된 기사 보기", value=False)
    query = st.text_input("제목 검색", placeholder="검색어", label_visibility="collapsed")


def _visible(c: Candidate) -> bool:
    if c.rep.category not in sel_cats:
        return False
    if state == "미검토" and c.decision != PENDING:
        return False
    if state == "승인" and c.decision != APPROVED:
        return False
    if state == "거절" and c.decision != REJECTED:
        return False
    if only_cand and not c.is_candidate and c.decision != REJECTED:
        return False
    return not query or query.lower() in " ".join(m.title.lower() for m in c.members)


shown = [c for c in result.candidates if _visible(c)]
if not result.candidates:
    st.info(
        "기사가 없습니다. 위의 **지금 수집**을 눌러 시작하세요. (소스·기간은 환경 설정에서 바꿉니다)"
    )

for c in shown:
    rep = c.rep
    badge = {APPROVED: "✅ 승인", REJECTED: "🚫 거절", PENDING: ""}[c.decision]
    with st.container(border=True):
        left, right = st.columns([6, 1.4])
        with left:
            st.markdown(f"**[{rep.title}]({rep.url})** {badge}")
            meta = [
                CATEGORY_LABELS.get(rep.category, rep.category),
                rep.source_name,
                _local(rep.when),
                f"점수 {c.score}",
            ]
            if len(c.members) > 1:
                meta.append(f"관련 {len(c.members) - 1}건")
            if c.matched:
                meta.append("🔑 " + ", ".join(c.matched))
            st.caption(" · ".join(meta))
            snippet = rep.summary or rep.content[:200]
            if snippet:
                st.write(snippet[:240] + ("…" if len(snippet) > 240 else ""))
            with st.expander("본문 · 관련 기사 · 점수 상세"):
                st.write(rep.content or "_(본문을 추출하지 못했습니다 — 요약만 사용합니다)_")
                if c.related:
                    st.markdown("**관련 기사**")
                    for m in c.related:
                        st.markdown(f"- [{m.title}]({m.url}) · {m.source_name}")
                st.caption(
                    f"신선도 {c.freshness} · 키워드 {c.keyword} · 화제성 {c.buzz} "
                    f"(가중치는 환경 설정 > 후보 선정)"
                )
        with right:
            if c.decision == APPROVED:
                st.button(
                    "승인 취소",
                    key=f"un{rep.id}",
                    on_click=_decide,
                    args=(c, PENDING),
                    width="stretch",
                )
            else:
                st.button(
                    "✅ 승인",
                    key=f"ok{rep.id}",
                    type="primary",
                    on_click=_decide,
                    args=(c, APPROVED),
                    width="stretch",
                )
                if c.decision == REJECTED:
                    st.button(
                        "거절 취소",
                        key=f"un{rep.id}",
                        on_click=_decide,
                        args=(c, PENDING),
                        width="stretch",
                    )
                else:
                    st.button(
                        "🚫 거절",
                        key=f"no{rep.id}",
                        on_click=_decide,
                        args=(c, REJECTED),
                        width="stretch",
                    )

if result.candidates and not shown:
    st.caption("조건에 맞는 기사가 없습니다. 필터를 바꿔 보세요.")

if show_excl and result.excluded:
    st.subheader(f"제외된 기사 {len(result.excluded)}건")
    for art, word in result.excluded:
        st.markdown(f"- [{art.title}]({art.url}) · {art.source_name} · 제외어 `{word}`")
