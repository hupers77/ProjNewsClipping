"""v1 설치본 보조 로직: 포트 선택 · 재사용 판단 · 점검(smoke)."""

from __future__ import annotations

import threading

import pytest

from newsclip_v1 import desktop
from newsclip_v1.server import make_server


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWSCLIP_HOME", str(tmp_path))


def test_pick_port_uses_default_when_free_and_reuses_our_server():
    free = desktop.free_port()
    assert desktop.pick_port(free) == (free, False)
    server = make_server(free)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert desktop.is_our_server(free)
        assert desktop.pick_port(free) == (free, True)  # 이미 떠 있는 우리 앱 → 창만 연다
    finally:
        server.shutdown()


def test_pick_port_avoids_a_port_taken_by_something_else():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        taken = s.getsockname()[1]
        port, reuse = desktop.pick_port(taken)
    assert port != taken and reuse is False


def test_smoke_passes_from_source(tmp_path):
    assert desktop.smoke() == 0
    assert "FAIL" not in desktop.SMOKE_LOG.read_text(encoding="utf-8")


def test_server_stays_up_while_window_is_open_even_without_pings():
    """절전 복귀·최소화로 화면 신호가 끊겨도 앱 창이 살아 있으면 서버를 끝내지 않는다."""
    assert not desktop.should_exit(
        window_alive=True, window_ended_for=0, pinged=True, since_last_ping=3600, since_start=7200
    )


def test_server_exits_after_the_window_process_ended():
    base = dict(pinged=True, since_start=1000)
    assert desktop.should_exit(window_alive=False, window_ended_for=20, since_last_ping=120, **base)
    # 막 끝났거나(재실행 대기), 화면 신호가 아직 오고 있으면 끝내지 않는다
    assert not desktop.should_exit(
        window_alive=False, window_ended_for=5, since_last_ping=120, **base
    )
    assert not desktop.should_exit(
        window_alive=False, window_ended_for=20, since_last_ping=5, **base
    )


def test_without_a_window_process_only_long_silence_ends_the_server():
    base = dict(window_alive=None, window_ended_for=0, since_start=1000)
    assert not desktop.should_exit(pinged=True, since_last_ping=60, **base)
    assert desktop.should_exit(pinged=True, since_last_ping=400, **base)
    assert desktop.should_exit(pinged=False, since_last_ping=0, **{**base, "since_start": 200})
