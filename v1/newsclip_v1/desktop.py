"""데스크톱 앱(설치본) 실행 보조: 포트 선택 · 앱 창 열기 · 창이 닫히면 서버 종료 · 점검.

설치본은 이 서버를 프로세스 안에서 띄우고 Edge/Chrome 의 앱 전용 창(--app)으로 연다.
화면 JS 가 5초마다 /api/ping 을 보내므로, 창이 닫혀 신호가 끊기면 서버도 스스로 끝난다.
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
IDLE_SECONDS = 25  # 마지막 신호 뒤 이 시간이 지나면 종료 (화면이 5초마다 신호를 보낸다)
FIRST_PING_SECONDS = 120  # 창이 아예 열리지 않은 경우의 안전장치
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


def open_window(url: str) -> None:
    browser = find_app_browser()
    if browser:
        profile = data_dir() / "window-profile"  # 별도 프로필 → 평소 브라우저와 섞이지 않는다
        subprocess.Popen(  # noqa: S603
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


def watch_and_exit(state: AppState, idle: float = IDLE_SECONDS) -> None:
    """화면 신호(ping)가 한 번이라도 왔고 이후 끊겨 유예 시간이 지나면 프로세스를 끝낸다."""
    started = time.monotonic()
    while True:
        time.sleep(2)
        now = time.monotonic()
        if state.pinged:
            if now - state.last_ping > idle:
                os._exit(0)
        elif now - started > FIRST_PING_SECONDS:
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
    port, reuse = pick_port()
    url = f"http://localhost:{port}"
    if reuse:  # 이미 떠 있는 앱이 있으면 창만 새로 연다
        open_window(url)
        return 0
    server = make_server(port)
    threading.Thread(target=open_window, args=(url,), daemon=True).start()
    threading.Thread(target=watch_and_exit, args=(server.app_state,), daemon=True).start()  # type: ignore[attr-defined]
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
