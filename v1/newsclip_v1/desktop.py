"""데스크톱 앱(설치본) 실행 보조: 포트 선택 · 앱 창 열기 · 창이 닫히면 서버 종료 · 점검.

설치본은 이 서버를 프로세스 안에서 띄우고 Edge/Chrome 의 앱 전용 창(--app)으로 연다.
화면 JS 가 5초마다 /api/alive 을 보내므로, 창이 닫혀 신호가 끊기면 서버도 스스로 끝난다.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from newsclip_v1.server import AppState, make_server

DEFAULT_PORT = 8520
APP_NAME = "ProjNewsClipping"
# 앱 창 프로세스를 알 수 있으면 그 프로세스가 끝났을 때만 종료한다. 화면 신호(ping)는 절전·최소화로
# 타이머가 멈추는 일이 잦아서 종료 판단의 유일한 근거로 쓰면 창이 열려 있는데 서버가 죽는다.
IDLE_SECONDS_NO_WINDOW_PROCESS = 300  # 창 프로세스를 모를 때(기본 브라우저)만 쓰는 긴 유예 시간
WINDOW_EXIT_GRACE_SECONDS = 15  # 창 프로세스가 끝난 뒤 새 창(재실행)을 기다리는 시간
FIRST_PING_SECONDS = 180  # 창이 아예 열리지 않은 경우의 안전장치
SMOKE_LOG = Path(tempfile.gettempdir()) / "newsclip-smoke.log"


def data_dir() -> Path:
    from platformdirs import user_data_dir

    path = Path(os.environ.get("NEWSCLIP_HOME") or user_data_dir(APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def redirect_output_when_windowed() -> None:
    """콘솔 없는 exe 는 stdout/stderr 가 None 이라 로깅이 깨진다 → 파일로 돌린다."""
    if sys.stdout is None or sys.stderr is None:
        log = open(data_dir() / "app.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def enable_crash_log() -> None:
    """프로세스가 비정상 종료(네이티브 충돌)할 때 원인이 app.log 에 남도록 한다."""
    import faulthandler
    import logging

    try:
        log = open(data_dir() / "app.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        faulthandler.enable(file=log)
        logging.basicConfig(
            level=logging.INFO, stream=log, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        log.write(f"--- 시작 {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    except OSError:
        pass


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def is_our_server(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
            return bool(json.loads(r.read()).get("app") == "NewsClipping")
    except (OSError, ValueError):
        return False


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def pick_port(default: int = DEFAULT_PORT) -> tuple[int, bool]:
    """(포트, 이미 실행 중인 우리 앱을 재사용하는지)."""
    if not port_open(default):
        return default, False
    if is_our_server(default):
        return default, True
    return free_port(), False


def find_app_browser() -> str | None:
    """--app 모드를 지원하는 Edge/Chrome 실행 파일."""
    for name in ("msedge", "chrome", "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    roots = [os.environ.get(k) for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
    rels = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
    for root in filter(None, roots):
        for rel in rels:
            candidate = Path(root) / rel
            if candidate.exists():
                return str(candidate)
    mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    return str(mac) if mac.exists() else None


def open_window(url: str) -> subprocess.Popen | None:
    """앱 창을 연다. 창 프로세스를 돌려주며, 기본 브라우저로 연 경우에는 None."""
    browser = find_app_browser()
    if browser:
        profile = data_dir() / "window-profile"  # 별도 프로필 → 평소 브라우저와 섞이지 않는다
        return subprocess.Popen(  # noqa: S603
            [
                browser,
                f"--app={url}",
                f"--user-data-dir={profile}",
                "--window-size=1360,900",
                "--no-first-run",
                "--no-default-browser-check",
            ]
        )
    else:
        import webbrowser

        webbrowser.open(url)
        return None


def should_exit(
    *,
    window_alive: bool | None,
    window_ended_for: float,
    pinged: bool,
    since_last_ping: float,
    since_start: float,
) -> bool:
    """서버를 끝낼지 판단한다 (테스트하기 쉽도록 순수 함수).

    window_alive: 앱 창 프로세스가 살아 있는지 (None = 프로세스를 모름)
    window_ended_for: 창 프로세스가 끝난 지 몇 초째인지
    """
    if window_alive is True:
        return False  # 창이 열려 있으면 신호가 끊겨도 종료하지 않는다 (절전 복귀·최소화 대비)
    if window_alive is False:
        # 창 프로세스가 끝났어도 화면 신호가 최근에 왔다면 창이 열려 있는 것이다
        recently_alive = pinged and since_last_ping < 2 * WINDOW_EXIT_GRACE_SECONDS
        return window_ended_for > WINDOW_EXIT_GRACE_SECONDS and not recently_alive
    # 창 프로세스를 모르는 경우: 화면 신호로만 판단한다
    if pinged:
        return since_last_ping > IDLE_SECONDS_NO_WINDOW_PROCESS
    return since_start > FIRST_PING_SECONDS


def watch_and_exit(state: AppState, window: dict) -> None:
    """앱 창이 닫히면(또는 신호가 오래 끊기면) 프로세스를 끝낸다. window['proc'] 는 앱 창 프로세스."""
    started = time.monotonic()
    proc_seen_at: float | None = None
    ended_at: float | None = None
    while True:
        time.sleep(2)
        now = time.monotonic()
        proc = window.get("proc")
        alive: bool | None = None
        if proc is not None:
            proc_seen_at = proc_seen_at or now
            alive = proc.poll() is None
            if alive:
                ended_at = None
            elif ended_at is None:
                ended_at = now
            if alive is False and ended_at - proc_seen_at < 10:
                alive = None  # 곧바로 끝났다면 다른 프로세스로 넘긴 것(핸드오프) — 신호로만 판단
        if should_exit(
            window_alive=alive,
            window_ended_for=(now - ended_at) if ended_at else 0.0,
            pinged=state.pinged,
            since_last_ping=now - state.last_ping,
            since_start=now - started,
        ):
            os._exit(0)


def smoke() -> int:
    """번들 안에서 서버를 띄우고 모든 화면을 요청해 import/렌더링 오류가 없는지 확인한다."""
    os.environ["NEWSCLIP_HOME"] = tempfile.mkdtemp(prefix="newsclip-smoke-")
    lines: list[str] = []
    failed = False
    try:
        server = make_server(free_port())
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        checks = [
            ("/", "후보 리스트"),
            ("/email", "이메일"),
            ("/settings", "기사 보관 기간"),
            ("/guide", "발송 처리"),
            ("/static/app.js", "initCandidates"),
            ("/static/app.css", "--accent"),
            ("/health", "NewsClipping"),
        ]
        for path, marker in checks:
            try:
                with urllib.request.urlopen(base + path, timeout=60) as r:
                    ok = r.status == 200 and marker in r.read().decode("utf-8")
                error = "" if ok else f"marker {marker!r} not found"
            except Exception as exc:  # noqa: BLE001 - 어떤 실패든 점검 결과로 남긴다
                ok, error = False, f"{type(exc).__name__}: {exc}"
            lines.append(f"{'ok  ' if ok else 'FAIL'} {path} {error}".rstrip())
            failed = failed or not ok
        server.shutdown()
    except Exception as exc:  # noqa: BLE001
        lines.append(f"FAIL server: {type(exc).__name__}: {exc}")
        failed = True
    report = "\n".join(lines) + "\n"
    SMOKE_LOG.write_text(report, encoding="utf-8")
    if sys.stdout is not None:
        print(report, end="", flush=True)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--smoke" in argv:
        return smoke()
    redirect_output_when_windowed()
    enable_crash_log()
    port, reuse = pick_port()
    url = f"http://localhost:{port}"
    if reuse:  # 이미 떠 있는 앱이 있으면 창만 새로 연다
        open_window(url)
        return 0
    server = make_server(port)
    window: dict = {"proc": None}

    def launch() -> None:
        window["proc"] = open_window(url)

    threading.Thread(target=launch, daemon=True).start()
    threading.Thread(
        target=watch_and_exit,
        args=(server.app_state, window),  # type: ignore[attr-defined]
        daemon=True,
    ).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
