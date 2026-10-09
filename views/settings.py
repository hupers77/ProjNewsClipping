"""환경 설정 (로컬 config.yaml 에 저장)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from newsclip import config, paths
from newsclip.config import SOURCE_TYPES, Keyword, Source

settings = config.load()

st.title("⚙️ 환경 설정")
st.caption(
    f"저장 위치: `{paths.config_path()}` (이 컴퓨터에만 저장됩니다) — "
    "값을 고친 뒤 아래 **저장** 버튼을 눌러야 반영됩니다."
)

with st.form("settings", border=False):
    tab_collect, tab_sources, tab_filter, tab_review, tab_email = st.tabs(
        ["수집", "사이트", "키워드", "후보 선정", "이메일"]
    )

    with tab_collect:
        c = settings.collect
        c.days = st.number_input(
            "수집 기간(일)", 1, 30, c.days, help="최근 며칠간의 기사를 대상으로 할지"
        )
        c.fetch_content = st.toggle("기사 본문 추출", value=c.fetch_content)
        c.content_max_chars = st.number_input(
            "본문 추출 글자 수 상한",
            100,
            20000,
            c.content_max_chars,
            step=100,
        )
        c.max_items_per_source = st.number_input(
            "사이트당 최대 수집 건수", 5, 200, c.max_items_per_source
        )
        st.caption(
            "본문은 robots.txt 를 따르며, 요약·검토 용도로만 쓰고 메일에는 짧은 요약과 출처 링크만 담습니다."
        )

    with tab_sources:
        st.write(
            "체크를 끄면 수집하지 않습니다. 유형: `rss`·`sitemap`·`trends_rss`(주소), `google_news`(주소 칸에 검색어), `hackernews`(주소 불필요). "
            "`HN 상위 N`: 인기순 상위 몇 건까지 볼지. `HN 최소 추천`: 추천(점수)이 이 값 이상인 글만 가져옵니다."
        )
        df = pd.DataFrame([vars(s) for s in settings.sources])
        edited = st.data_editor(
            df,
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            column_config={
                "id": st.column_config.TextColumn(
                    "ID", help="영문/숫자 (중복 불가)", required=True
                ),
                "name": st.column_config.TextColumn("이름", required=True),
                "type": st.column_config.SelectboxColumn(
                    "유형", options=SOURCE_TYPES, required=True
                ),
                "url": st.column_config.TextColumn("주소 / 검색어"),
                "category": st.column_config.SelectboxColumn(
                    "분류", options=["ai", "it", "hot"], required=True
                ),
                "lang": st.column_config.SelectboxColumn("언어", options=["ko", "en"]),
                "enabled": st.column_config.CheckboxColumn("사용"),
                "top_n": st.column_config.NumberColumn("HN 상위 N", min_value=1, step=1),
                "min_points": st.column_config.NumberColumn("HN 최소 추천", min_value=0, step=10),
            },
        )

    with tab_filter:
        f = settings.filters
        left, right = st.columns(2)
        with left:
            st.markdown("**제외 키워드** — 한 줄에 하나. 제목·요약에 있으면 후보에서 뺍니다.")
            excl = st.text_area(
                "제외 키워드",
                "\n".join(f.exclude_keywords),
                height=220,
                label_visibility="collapsed",
            )
            f.exclude_in_content = st.toggle(
                "본문에서도 제외 키워드 찾기", value=f.exclude_in_content
            )
        with right:
            st.markdown(
                "**포함 키워드(가산점)** — 제목에 있으면 가산점 전부, 요약·본문에만 있으면 절반."
            )
            kdf = st.data_editor(
                pd.DataFrame(
                    [vars(k) for k in f.include_keywords] or [{"word": "", "bonus": 10.0}]
                ),
                num_rows="dynamic",
                width="stretch",
                hide_index=True,
                column_config={
                    "word": st.column_config.TextColumn("키워드", required=True),
                    "bonus": st.column_config.NumberColumn(
                        "가산점", min_value=0.0, max_value=100.0, step=5.0, default=10.0
                    ),
                },
            )

    with tab_review:
        r = settings.review
        st.caption("LLM 없이 규칙으로 고릅니다. 점수 = 신선도·키워드·화제성의 가중 평균(0~100).")
        a, b, d = st.columns(3)
        r.max_candidates = a.number_input("최대 후보 수", 1, 200, r.max_candidates)
        r.min_score = b.number_input("최소 점수", 0.0, 100.0, float(r.min_score), step=5.0)
        r.per_source_max = d.number_input("매체당 최대 후보 수 (0=무제한)", 0, 50, r.per_source_max)
        r.cluster_threshold = st.slider(
            "같은 사건으로 묶는 제목 유사도",
            0.2,
            0.9,
            float(r.cluster_threshold),
            0.05,
            help="낮출수록 더 많이 묶입니다",
        )
        w1, w2, w3 = st.columns(3)
        r.weight_freshness = w1.slider("가중치: 신선도", 0.0, 1.0, float(r.weight_freshness), 0.05)
        r.weight_keyword = w2.slider("가중치: 키워드", 0.0, 1.0, float(r.weight_keyword), 0.05)
        r.weight_buzz = w3.slider("가중치: 화제성", 0.0, 1.0, float(r.weight_buzz), 0.05)

    with tab_email:
        e = settings.email
        e.subject_template = st.text_input(
            "제목 템플릿", e.subject_template, help="{date} = 오늘 날짜"
        )
        e.sender = st.text_input("보내는 사람", e.sender, help="예: 홍길동 <me@example.com>")
        e.recipients = st.text_input("받는 사람 (쉼표로 구분, 비워도 됨)", e.recipients)
        e.intro = st.text_area("도입 문구", e.intro, height=80)
        e.outro = st.text_area("맺음 문구", e.outro, height=80)
        x, y = st.columns(2)
        e.summary_chars = x.number_input("항목별 요약 글자 수", 50, 1000, e.summary_chars, step=10)
        e.max_links = y.number_input("항목별 출처 링크 수", 1, 10, e.max_links)

    submitted = st.form_submit_button("💾 저장", type="primary")

if submitted:
    ids = [str(row["id"]).strip() for _, row in edited.iterrows() if str(row["id"]).strip()]
    if len(ids) != len(set(ids)):
        st.error("사이트 ID 가 중복되었습니다.")
    else:
        settings.sources = [
            Source(
                id=str(row["id"]).strip(),
                name=str(row["name"]),
                type=str(row["type"]),
                url=str(row["url"] or "").strip(),
                category=str(row["category"]),
                lang=str(row["lang"] or "ko"),
                enabled=bool(row["enabled"]),
            )
            for _, row in edited.iterrows()
            if str(row["id"]).strip()
        ]
        settings.filters.exclude_keywords = [w.strip() for w in excl.splitlines() if w.strip()]
        settings.filters.include_keywords = [
            Keyword(str(row["word"]).strip(), float(row["bonus"] if pd.notna(row["bonus"]) else 10))
            for _, row in kdf.iterrows()
            if str(row["word"]).strip() and str(row["word"]) != "nan"
        ]
        config.save(settings)
        st.success("저장했습니다. 후보 리스트는 저장된 기사로 바로 다시 계산됩니다.")
