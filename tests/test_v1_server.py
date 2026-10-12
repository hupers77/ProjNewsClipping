"""v1: 실제 HTTP 서버를 띄워 화면·API 를 검사한다."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest

from newsclip_v1 import config
from newsclip_v1.server import make_server
from newsclip_v1.store import ACTIVE, CLEARED, DRAFTED, Store2


@pytest.fixture()
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWSCLIP_HOME", str(tmp_path))
    now = datetime.now(UTC)
    Store2().add_articles(
        [
            {
                "url_hash": f"h{i}",
                "url": f"https://e.com/{i}",
                "title": t,
                "summary": "요약 문장입니다.",
                "source_id": f"s{i}",
                "source_name": f"매체{i}",
                "category": "it",
                "published_at": (now - timedelta(hours=i)).isoformat(),
            }
            for i, t in enumerate(
                [
                    "알파 베타 감마 델타 소식",
                    "완전히 다른 제목 하나 둘 셋",
                    "<b>태그</b> 제목 테스트 기사",
                ]
            )
        ]
    )
    settings = config.from_dict({})
    settings.review.min_score = 0
    config.save(settings)
    srv = make_server(0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def get(base: str, path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(base + path, timeout=20) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def post(base: str, path: str, data: dict | None = None, *, headers: dict | None = None):
    h = {"Content-Type": "application/json", "X-NewsClip": "1", **(headers or {})}
    req = urllib.request.Request(base + path, json.dumps(data or {}).encode(), h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_pages_render(server):
    for path, needle in [
        ("/", "후보 리스트"),
        ("/email", "작성 중인 이메일 초안이 없습니다"),
        ("/settings", "기사 보관 기간"),
        ("/guide", "사용법"),
        ("/static/app.js", "initCandidates"),
        ("/static/app.css", "--accent"),
    ]:
        status, body = get(server, path)
        assert status == 200 and needle in body, path
    assert "v1.0" in get(server, "/")[1]


def test_candidate_titles_are_escaped(server):
    body = get(server, "/")[1]
    assert "&lt;b&gt;태그&lt;/b&gt;" in body and "<b>태그</b>" not in body


def test_guide_page_is_rendered_from_guide_py(server, tmp_path):
    body = get(server, "/guide")[1]
    assert "발송 처리" in body and "기사 보관 기간" in body and "30일" in body


def test_post_requires_custom_header_and_local_origin(server):
    req = urllib.request.Request(
        server + "/api/collect", b"{}", {"Content-Type": "application/json"}, method="POST"
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 403
    assert post(server, "/api/ping", headers={"Origin": "https://evil.example"})[0] == 403
    assert post(server, "/api/ping", headers={"Origin": "http://localhost:1"})[0] == 200


def test_foreign_host_header_is_rejected(server):
    req = urllib.request.Request(server + "/", headers={"Host": "evil.example"})
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 403


def test_static_path_traversal_is_blocked(server):
    assert get(server, "/static/../guide.py")[0] == 404
    assert get(server, "/static/%2e%2e/guide.py")[0] == 404


def test_full_flow_decision_make_email_edit_sent(server):
    store = Store2()
    ids = [a.id for a in store.articles_since(datetime.now(UTC) - timedelta(days=1))]
    first = ids[0]
    assert (
        post(server, "/api/decision", {"id": first, "ids": [first], "decision": "approved"})[0]
        == 200
    )
    assert (
        post(server, "/api/decision", {"id": first, "ids": [first], "decision": "weird"})[0] == 400
    )

    assert post(server, "/api/make-email", {"clear_undecided": True})[0] == 200
    assert set(store.ids_in_phase(CLEARED)) == set(ids) - {first}
    assert store.ids_in_phase(DRAFTED) == [first]
    assert "후보 리스트" in get(server, "/")[1] and "기사가 없습니다" in get(server, "/")[1]

    page = get(server, "/email")[1]
    assert 'id="email-form"' in page and "뉴스 클리핑" in page

    # 편집 → 미리보기 → 저장 → 내보내기
    from newsclip_v1 import service

    draft = service.load_draft(store)
    payload = {"draft": json.loads(json.dumps(__import__("dataclasses").asdict(draft)))}
    payload["draft"]["subject"] = "고친 제목"
    status, res = post(server, "/api/email/preview", payload)
    assert status == 200 and "고친 제목" in res["html"]
    assert post(server, "/api/email/save", payload)[0] == 200
    assert service.load_draft(store).subject == "고친 제목"
    status, res = post(server, "/api/email/export", {**payload, "kind": "eml"})
    assert status == 200 and res["filename"].endswith(".eml") and res["data"]
    assert post(server, "/api/email/export", {**payload, "kind": "pdf"})[0] == 400
    assert post(server, "/api/email/mailto", payload)[1]["url"].startswith("mailto:")

    # 발송 처리: 초안이 비워진다
    status, res = post(server, "/api/email/sent")
    assert status == 200 and res["count"] == 1
    assert service.load_draft(store) is None
    assert "작성 중인 이메일 초안이 없습니다" in get(server, "/email")[1]
    assert "마지막 발송 처리" in get(server, "/email")[1]


def test_make_email_without_approval_is_a_clear_error(server):
    status, res = post(server, "/api/make-email", {})
    assert status == 400 and "승인" in res["error"]
    assert Store2().counts()[ACTIVE] == 3  # 아무것도 바뀌지 않았다


def test_revert_returns_articles_to_list(server):
    store = Store2()
    first = store.articles_since(datetime.now(UTC) - timedelta(days=1))[0].id
    post(server, "/api/decision", {"id": first, "ids": [first], "decision": "approved"})
    post(server, "/api/make-email", {})
    assert post(server, "/api/email/revert")[1]["count"] == 1
    assert store.ids_in_phase(ACTIVE) == [first]


def test_settings_save_validates_and_enforces_retention(server):
    s = config.load()
    from dataclasses import asdict

    data = asdict(s)
    data["collect"]["retention_days"] = 1  # 수집 기간(3일)보다 짧다
    status, res = post(server, "/api/settings", data)
    assert status == 200 and res["retention_days"] == 3 and "맞췄습니다" in res["message"]
    assert config.load().collect.retention_days == 3

    data["collect"]["retention_days"] = 45
    assert post(server, "/api/settings", data)[1]["retention_days"] == 45
    assert config.load().collect.retention_days == 45

    for bad in ({**data, "sources": []},):
        assert post(server, "/api/settings", bad)[0] == 400


def test_collect_job_runs_and_reports(server, monkeypatch):
    from newsclip import collector

    def fake_collect(settings, store, progress=None, client=None):
        progress and progress("가짜 수집 중")
        return collector.CollectReport(results=[collector.SourceResult("x", 1, 1, "")])

    monkeypatch.setattr(collector, "collect", fake_collect)
    assert post(server, "/api/collect")[1]["started"] is True
    import time

    for _ in range(50):
        status = json.loads(get(server, "/api/collect/status")[1])
        if not status["running"]:
            break
        time.sleep(0.05)
    assert status["running"] is False and status["report"]["new_total"] == 1


def test_server_survives_many_concurrent_requests(server):
    """수집 중 화면이 보내는 동시 요청이 몰려도 접속이 거부되지 않아야 한다 (대기열 크기)."""
    import urllib.request

    errors: list[str] = []

    def hammer() -> None:
        for _ in range(30):
            try:
                urllib.request.urlopen(server + "/api/collect/status", timeout=10).read()
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))

    threads = [threading.Thread(target=hammer) for _ in range(24)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
