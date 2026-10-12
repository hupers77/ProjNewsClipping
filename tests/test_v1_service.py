"""v1: 저장소 단계(phase) · 이메일 만들기 · 발송 처리 · 보관 기간 삭제."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from newsclip.store import APPROVED, REJECTED, Store
from newsclip_v1 import config, service
from newsclip_v1.store import ACTIVE, CLEARED, DRAFTED, SENT, Store2


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWSCLIP_HOME", str(tmp_path))


def row(n: int, title: str, hours: float = 1, **kw):
    return {
        "url_hash": f"h{n}",
        "url": f"https://example.com/{n}",
        "title": title,
        "source_id": f"s{n}",
        "source_name": f"매체{n}",
        "category": "it",
        "published_at": (datetime.now(UTC) - timedelta(hours=hours)).isoformat(),
        **kw,
    }


TITLES = {
    1: "알파 베타 감마 델타 첫번째",
    2: "완전히 다른 제목입니다 둘째",
    3: "또 하나의 전혀 다른 소식 셋째",
    4: "광고 포함 소식 넷째 입니다",
}


def seeded() -> tuple[config.Settings, Store2]:
    settings = config.from_dict({})
    settings.filters.exclude_keywords = ["광고"]
    settings.review.min_score = 0
    store = Store2()
    store.add_articles([row(i, t, hours=i) for i, t in TITLES.items()])
    return settings, store


def decide(store: Store2, approved: list[int], rejected: list[int]) -> None:
    store.set_decision(approved, APPROVED)
    store.set_decision(rejected, REJECTED)


def test_phase_column_is_added_to_existing_database(tmp_path):
    legacy = Store(tmp_path / "legacy.db")
    legacy.add_articles([row(1, "기존 앱이 저장한 기사")])
    legacy.set_decision([1], APPROVED)
    store = Store2(tmp_path / "legacy.db")
    articles = store.articles_since(datetime.now(UTC) - timedelta(days=1))
    assert [(a.id, a.decision) for a in articles] == [(1, APPROVED)]
    assert store.counts()[ACTIVE] == 1
    # 두 번 열어도 문제없다 (마이그레이션 멱등)
    Store2(tmp_path / "legacy.db")
    cols = {
        r[1] for r in sqlite3.connect(tmp_path / "legacy.db").execute("PRAGMA table_info(articles)")
    }
    assert "phase" in cols


def test_make_email_moves_approved_and_resets_the_list():
    settings, store = seeded()
    decide(store, approved=[1], rejected=[2])
    draft = service.make_email(settings, store)
    assert [i.article_id for i in draft.items] == [1]
    assert service.load_draft(store) is not None
    phases = {
        i: p
        for p, ids in ((p, store.ids_in_phase(p)) for p in (DRAFTED, CLEARED, ACTIVE))
        for i in ids
    }
    assert phases == {1: DRAFTED, 2: CLEARED, 3: CLEARED, 4: CLEARED}
    # 리스트가 비었고, 같은 기사를 다시 수집해도 들어오지 않는다
    from newsclip.review import review

    assert review(settings, store).candidates == []
    assert store.add_articles([row(1, TITLES[1]), row(2, TITLES[2])]) == 0


def test_make_email_can_keep_undecided_articles():
    settings, store = seeded()
    decide(store, approved=[1], rejected=[2])
    service.make_email(settings, store, clear_undecided=False)
    assert set(store.ids_in_phase(ACTIVE)) == {3, 4}
    assert set(store.ids_in_phase(CLEARED)) == {2}


def test_make_email_requires_an_approval():
    settings, store = seeded()
    with pytest.raises(service.NothingApproved):
        service.make_email(settings, store)
    assert store.counts()[ACTIVE] == 4  # 아무것도 바뀌지 않는다


def test_second_make_email_extends_the_unsent_draft_and_keeps_edits():
    settings, store = seeded()
    decide(store, approved=[1], rejected=[])
    draft = service.make_email(settings, store, clear_undecided=False)
    draft.items[0].summary = "내가 고친 요약"
    draft.subject = "내가 정한 제목"
    service.save_draft(store, draft)
    decide(store, approved=[2], rejected=[])
    merged = service.make_email(settings, store, clear_undecided=False)
    assert [i.article_id for i in merged.items] == [1, 2]
    assert merged.items[0].summary == "내가 고친 요약" and merged.subject == "내가 정한 제목"


def test_mark_sent_clears_the_draft_and_records_articles():
    settings, store = seeded()
    decide(store, approved=[1, 2], rejected=[])
    draft = service.make_email(settings, store)
    draft.items[1].include = False  # 두 번째 항목은 메일에서 뺐다
    service.save_draft(store, draft)
    assert service.mark_sent(store) == 1
    assert service.load_draft(store) is None
    assert store.get_kv(service.LAST_SENT_KEY)
    assert store.ids_in_phase(SENT) == [1]
    assert 2 in store.ids_in_phase(CLEARED) and store.ids_in_phase(DRAFTED) == []


def test_revert_draft_returns_articles_as_approved():
    settings, store = seeded()
    decide(store, approved=[1], rejected=[])
    service.make_email(settings, store)
    assert service.revert_draft(store) == 1
    assert service.load_draft(store) is None
    from newsclip.review import review

    cands = review(settings, store).candidates
    assert [c.rep.id for c in cands] == [1] and cands[0].decision == APPROVED


def test_purge_deletes_everything_older_than_retention_in_every_state():
    settings, store = seeded()
    decide(store, approved=[1], rejected=[2])
    service.make_email(settings, store)  # 1: drafted, 2/3/4: cleared
    store.set_phase([3], SENT)
    settings.collect.retention_days = 30
    # 아직 보관 기간 안: 아무것도 지우지 않는다
    assert service.purge_expired(settings, store) == 0
    # 31일 뒤: 상태와 상관없이 전부 삭제
    later = datetime.now(UTC) + timedelta(days=31)
    assert service.purge_expired(settings, store, now=later) == 4
    assert sum(store.counts().values()) == 0


def test_retention_days_default_and_never_shorter_than_collect_days():
    assert config.from_dict({}).collect.retention_days == 30
    s = config.from_dict({"collect": {"days": 10, "retention_days": 3}})
    assert s.collect.retention_days == 10
    assert config.from_dict({"collect": {"retention_days": "x"}}).collect.retention_days == 30


def test_settings_roundtrip_keeps_retention_and_old_app_can_read_it():
    s = config.from_dict({})
    s.collect.retention_days = 45
    config.save(s)
    assert config.load().collect.retention_days == 45
    from newsclip import config as old

    assert old.load().collect.days == s.collect.days  # 기존 앱 설정 로더도 그대로 읽는다
