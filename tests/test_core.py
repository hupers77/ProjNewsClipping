from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from newsclip import config
from newsclip.collector import collect, parse_feed
from newsclip.config import Keyword, Source
from newsclip.emailer import (
    build_draft,
    build_eml,
    draft_from_dict,
    draft_to_dict,
    mailto_url,
    render_html,
)
from newsclip.review import review
from newsclip.store import APPROVED, REJECTED, Store
from newsclip.text import normalize_url, summarize

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWSCLIP_HOME", str(tmp_path))


def row(n: int, title: str, hours: float = 1, source: str = "s1", **kw):
    url = f"https://example.com/{n}"
    return {
        "url_hash": f"h{n}",
        "url": url,
        "title": title,
        "source_id": source,
        "source_name": source,
        "category": "it",
        "published_at": (NOW - timedelta(hours=hours)).isoformat(),
        **kw,
    }


def feed_xml(entries: list[tuple[str, str, datetime]]) -> bytes:
    items = "".join(
        f"<item><title>{t}</title><link>{u}</link><description>요약 {t}</description>"
        f"<pubDate>{d:%a, %d %b %Y %H:%M:%S +0000}</pubDate></item>"
        for t, u, d in entries
    )
    return f"<?xml version='1.0'?><rss version='2.0'><channel><title>x</title>{items}</channel></rss>".encode()


def test_normalize_url_strips_tracking():
    assert normalize_url("HTTPS://Ex.com/a/?utm_source=x&b=2&a=1#f") == "https://ex.com/a?a=1&b=2"


def test_summarize_limits_chars():
    text = "첫 문장입니다. " * 50
    out = summarize(text, 40)
    assert len(out) <= 40 and out.startswith("첫 문장입니다.")


def test_config_roundtrip():
    s = config.load()
    assert s.sources  # 기본 소스
    s.collect.days = 5
    s.filters.exclude_keywords = ["광고"]
    s.filters.include_keywords = [Keyword("AI", 20)]
    config.save(s)
    s2 = config.load()
    assert s2.collect.days == 5 and s2.filters.exclude_keywords == ["광고"]
    assert s2.filters.include_keywords[0].bonus == 20


def test_parse_feed_filters_old_and_strips_outlet():
    xml = feed_xml(
        [
            ("새 기사 - 매체A", "https://a.com/1?utm_x=1", NOW - timedelta(hours=2)),
            ("옛 기사", "https://a.com/2", NOW - timedelta(days=9)),
        ]
    )
    src = Source("a", "A", "rss", "https://a.com/rss")
    items = parse_feed(xml, src, NOW - timedelta(days=3), 10)
    assert [i["url"] for i in items] == ["https://a.com/1"]


def test_collect_is_idempotent_and_extracts_content():
    xml = feed_xml([("AI 소식", "https://a.com/1", datetime.now(UTC) - timedelta(hours=1))])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rss":
            return httpx.Response(200, content=xml)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200, text="<html><body><article>" + "본문 " * 50 + "</article></body></html>"
        )

    s = config.from_dict({"sources": [{"id": "a", "name": "A", "url": "https://a.com/rss"}]})
    s.collect.content_max_chars = 30
    store = Store()
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    first = collect(s, store, client=client)
    second = collect(s, store, client=client)
    assert first.new_total == 1 and second.new_total == 0
    art = store.articles_since(datetime.now(UTC) - timedelta(days=1))[0]
    assert len(art.content) <= 30


def test_review_excludes_scores_and_clusters():
    s = config.from_dict({})
    s.filters.exclude_keywords = ["광고"]
    s.filters.include_keywords = [Keyword("GPT", 60)]
    store = Store()
    store.add_articles(
        [
            row(1, "GPT-6 공개, 성능 대폭 향상", source="a"),
            row(2, "GPT-6 공개 성능 대폭 향상됐다", hours=2, source="b"),
            row(3, "광고 포함 소식", source="a"),
            row(4, "전혀 다른 반도체 이야기", hours=60, source="c"),
        ]
    )
    res = review(s, store, NOW)
    assert [a.id for a, _ in res.excluded] == [3]
    top = res.candidates[0]
    assert len(top.members) == 2 and top.matched == ["GPT"]
    assert top.score > res.candidates[1].score
    assert top.is_candidate


def test_decision_and_candidate_limits():
    s = config.from_dict({})
    s.review.max_candidates = 1
    s.review.min_score = 0
    store = Store()
    store.add_articles(
        [row(1, "알파 베타 감마 델타"), row(2, "완전히 다른 제목입니다 하하", hours=5)]
    )
    res = review(s, store, NOW)
    assert [c.is_candidate for c in res.candidates] == [True, False]
    store.set_decision([res.candidates[1].rep.id], APPROVED)  # 승인은 항상 후보
    store.set_decision([res.candidates[0].rep.id], REJECTED)  # 거절은 후보에서 빠짐
    res = review(s, store, NOW)
    by_id = {c.rep.id: c for c in res.candidates}
    assert by_id[2].is_candidate and not by_id[1].is_candidate


def test_email_draft_roundtrip_and_render():
    s = config.from_dict({})
    store = Store()
    store.add_articles([row(1, "<제목> & 테스트", summary="요약 문장입니다.")])
    store.set_decision([1], APPROVED)
    cands = [c for c in review(s, store, NOW).candidates if c.decision == APPROVED]
    d = build_draft(cands, s.email, None, today=NOW.date())
    assert d.subject == "뉴스 클리핑 2026-10-09" and d.items[0].summary == "요약 문장입니다."
    d.items[0].summary = "고친 요약"
    d2 = build_draft(cands, s.email, draft_from_dict(draft_to_dict(d)))
    assert d2.items[0].summary == "고친 요약"  # 편집 유지
    html = render_html(d2)
    assert "&lt;제목&gt;" in html and "고친 요약" in html
    d2.items[0].include = False
    assert "고친 요약" not in render_html(d2)
    eml = build_eml(d2, NOW)
    assert b"X-Unsent: 1" in eml
    assert mailto_url(d2).startswith("mailto:?subject=")
