"""데스크톱 앱 실행 진입점 (PyInstaller 로 묶여 NewsClipping.exe 가 된다).

Streamlit 서버를 이 프로세스 안에서 띄우고, 앱 전용 창(Edge/Chrome --app 모드)으로 연다.
창을 닫아 접속이 모두 끊기면 서버도 자동으로 종료한다.

    NewsClipping.exe           # 평소 실행
    NewsClipping.exe --smoke   # 점검: 모든 화면 스크립트를 실행해 import 오류가 없는지 확인
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

DEFAULT_PORT = 8520
IDLE_GRACE_SECONDS = 20  # 마지막 접속이 끊긴 뒤 이 시간이 지나면 종료 (새로고침 여유)
APP_NAME = "ProjNewsClipping"


def resource_dir() -> Path:
    """app.py / views / .streamlit 이 있는 폴더 (PyInstaller 번들 또는 저장소 루트)."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(__file__).resolve().parent.parent


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
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def pick_port() -> tuple[int, bool]:
    """(포트, 이미 실행 중인 우리 서버를 재사용하는지)."""
    if not port_open(DEFAULT_PORT):
        return DEFAULT_PORT, False
    if is_our_server(DEFAULT_PORT):
        return DEFAULT_PORT, True
    return free_port(), False


def find_app_browser() -> str | None:
    """--app 모드를 지원하는 Edge/Chrome 실행 파일."""
    for name in ("msedge", "chrome", "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    roots = [os.environ.get(k) for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
    rels = [
        r"Microsoft\Edge\Application\msedge.exe",
        r"Google\Chrome\Application\chrome.exe",
    ]
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


def active_sessions() -> int | None:
    try:
        from streamlit.runtime import Runtime

        return int(Runtime.instance()._session_mgr.num_active_sessions())  # noqa: SLF001
    except Exception:  # noqa: BLE001 - 내부 API 이므로 실패하면 감시를 포기한다
        return None


def watch_and_exit() -> None:
    """접속이 한 번이라도 있었고 이후 끊긴 채 유예 시간이 지나면 프로세스를 끝낸다."""
    seen = False
    idle_since: float | None = None
    started = time.monotonic()
    while True:
        time.sleep(2)
        n = active_sessions()
        if n is None:
            continue
        if n > 0:
            seen, idle_since = True, None
        else:
            idle_since = idle_since or time.monotonic()
            limit = IDLE_GRACE_SECONDS if seen else 120  # 창이 안 열린 경우의 안전장치
            if time.monotonic() - (idle_since if seen else started) > limit:
                os._exit(0)


def run_streamlit(port: int) -> None:
    from streamlit.web import bootstrap

    root = resource_dir()
    os.chdir(root)  # st.Page("views/...") 가 앱 폴더 기준이므로
    flags = {
        "server.port": port,
        "server.address": "127.0.0.1",
        "server.headless": True,
        "server.fileWatcherType": "none",
        "browser.gatherUsageStats": False,
        "global.developmentMode": False,
        "theme.base": "light",
    }
    bootstrap.load_config_options(flags)
    bootstrap.run(str(root / "app.py"), False, [], flags)


SMOKE_LOG = Path(__import__("tempfile").gettempdir()) / "newsclip-smoke.log"


def smoke() -> int:
    """번들 안에서 모든 화면 스크립트를 실행해 import/문법 오류가 없는지 확인한다.

    콘솔 없는 exe 에서도 결과를 볼 수 있도록 같은 내용을 SMOKE_LOG 파일에도 남긴다.
    종료 코드: 0 = 모두 정상.
    """
    import tempfile

    from streamlit.testing.v1 import AppTest

    os.environ["NEWSCLIP_HOME"] = tempfile.mkdtemp(prefix="newsclip-smoke-")
    root = resource_dir()
    os.chdir(root)
    lines: list[str] = []
    failed = False
    for script in (
        "app.py",
        "views/candidates.py",
        "views/email.py",
        "views/settings.py",
        "views/guide.py",
    ):
        try:
            at = AppTest.from_file(str(root / script), default_timeout=60).run()
            errors = [str(e.value) for e in at.exception]
        except Exception as exc:  # noqa: BLE001 - 어떤 실패든 점검 결과로 남긴다
            errors = [f"{type(exc).__name__}: {exc}"]
        lines.append(f"{'FAIL' if errors else 'ok  '} {script} {' | '.join(errors)}".rstrip())
        failed = failed or bool(errors)
    report = "\n".join(lines) + "\n"
    SMOKE_LOG.write_text(report, encoding="utf-8")
    if sys.stdout is not None:
        print(report, end="", flush=True)
    return 1 if failed else 0


def main() -> int:
    # 번들 실행은 site-packages 밖이라 Streamlit 이 개발 모드로 오인한다 (server.port 와 충돌)
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    if "--smoke" in sys.argv:
        return smoke()
    redirect_output_when_windowed()
    port, reuse = pick_port()
    url = f"http://localhost:{port}"
    if reuse:  # 이미 떠 있는 앱이 있으면 창만 새로 연다
        open_window(url)
        return 0

    def opener() -> None:
        for _ in range(150):
            if is_our_server(port):
                open_window(url)
                return
            time.sleep(0.2)

    threading.Thread(target=opener, daemon=True).start()
    threading.Thread(target=watch_and_exit, daemon=True).start()
    run_streamlit(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
