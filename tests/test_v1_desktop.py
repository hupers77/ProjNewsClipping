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
