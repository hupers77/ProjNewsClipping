"""로컬 HTTP 서버 (표준 라이브러리). JSON API + 서버 렌더링 HTML.

보안: 127.0.0.1 에만 바인딩하고, Host 헤더를 검사하며(DNS 리바인딩 방지),
상태를 바꾸는 POST 는 사용자 지정 헤더(X-NewsClip)와 같은 출처(Origin)만 허용한다.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import threading
import time
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from newsclip import collector, paths
from newsclip.emailer import (
    Draft,
    build_eml,
    draft_from_dict,
    mailto_url,
    open_in_mail_client,
    render_html,
    save_eml,
)
from newsclip.review import review
from newsclip.store import APPROVED, PENDING, REJECTED
from newsclip_v1 import config, pages, service
from newsclip_v1.store import Store2

logger = logging.getLogger(__name__)

MAX_BODY = 8_000_000
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
GUIDE_PY = Path(__file__).resolve().parent.parent / "guide.py"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppState:
    """서버 프로세스 전체가 공유하는 상태 (수집 작업 · 접속 감시)."""

    def __init__(self, port: int, static_dir: Path = STATIC_DIR, guide_py: Path = GUIDE_PY) -> None:
        self.port = port
        self.static_dir = static_dir
        self.guide_py = guide_py
        self.lock = threading.Lock()
        self.job: dict[str, Any] = {"running": False, "message": "", "error": "", "report": {}}
        self.last_ping = 0.0
        self.pinged = False

    # 수집 작업 ------------------------------------------------------
    def start_collect(self) -> bool:
        with self.lock:
            if self.job["running"]:
                return False
            self.job = {"running": True, "message": "수집을 시작합니다…", "error": "", "report": {}}
        threading.Thread(target=self._run_collect, daemon=True).start()
        return True

    def _set_message(self, message: str) -> None:
        with self.lock:
            self.job["message"] = message

    def _run_collect(self) -> None:
        try:
            settings = config.load()
            store = Store2()
            report = collector.collect(settings, store, progress=self._set_message)
            purged = service.purge_expired(settings, store)
            data = {
                "new_total": report.new_total,
                "content_fetched": report.content_fetched,
                "purged": purged,
                "sources": [
                    {"source": r.source, "fetched": r.fetched, "new": r.new, "error": r.error}
                    for r in report.results
                ],
            }
            with self.lock:
                self.job.update(running=False, message="완료", report=data)
        except Exception as exc:  # noqa: BLE001 - 어떤 실패든 화면에 알린다
            logger.exception("collect failed")
            with self.lock:
                self.job.update(running=False, error=f"수집 실패: {type(exc).__name__}: {exc}")


class Handler(BaseHTTPRequestHandler):
    server_version = "NewsClipping/1.0"
    state: AppState  # 서버가 주입

    # 공통 -----------------------------------------------------------
    def log_message(self, fmt: str, *args: Any) -> None:  # 콘솔 소음 제거
        logger.debug("%s - %s", self.address_string(), fmt % args)

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in {"localhost", "127.0.0.1", "[::1]"}

    def _send(
        self, status: int, body: bytes, ctype: str, extra: dict[str, str] | None = None
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str, status: int = 200) -> None:
        self._send(status, text.encode("utf-8"), "text/html; charset=utf-8")

    def _json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status)

    def _body_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("요청이 너무 큽니다")
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(data, dict):
            raise ValueError("잘못된 요청 형식입니다")
        return data

    # GET ------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        if not self._host_ok():
            return self._error(HTTPStatus.FORBIDDEN, "허용되지 않은 호스트입니다")
        path = urlsplit(self.path).path
        try:
            if path == "/":
                return self._page_candidates()
            if path == "/email":
                return self._page_email()
            if path == "/settings":
                return self._html(pages.settings_page(config.load(), paths.config_path()))
            if path == "/guide":
                return self._html(pages.guide_page(self.state.guide_py, (PROJECT_ROOT / "v1",)))
            if path.startswith("/static/"):
                return self._static(path[len("/static/") :])
            if path == "/api/collect/status":
                with self.state.lock:
                    return self._json(dict(self.state.job))
            if path == "/health":
                return self._json({"app": "NewsClipping", "version": "1.0"})
            if path == "/favicon.ico":
                return self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
        except Exception as exc:  # noqa: BLE001
            logger.exception("GET %s failed", path)
            return self._html(f"<pre>오류: {type(exc).__name__}: {exc}</pre>", 500)
        self._html("<h1>404</h1><p>페이지를 찾을 수 없습니다.</p>", 404)

    def _static(self, name: str) -> None:
        target = (self.state.static_dir / name).resolve()
        if self.state.static_dir.resolve() not in target.parents or not target.is_file():
            return self._error(HTTPStatus.NOT_FOUND, "파일이 없습니다")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in {"application/javascript"}:
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    def _page_candidates(self) -> None:
        settings, store = config.load(), Store2()
        service.purge_expired(
            settings, store
        )  # 화면을 열 때마다 오래된 기사 정리 (가벼운 DELETE 한 번)
        result = review(settings, store)
        with self.state.lock:
            running = bool(self.state.job["running"])
        last_sent = store.get_kv(service.LAST_SENT_KEY)
        self._html(
            pages.candidates_page(
                settings,
                result,
                collecting=running,
                last_sent=last_sent if isinstance(last_sent, str) else None,
            )
        )

    def _page_email(self) -> None:
        store = Store2()
        last_sent = store.get_kv(service.LAST_SENT_KEY)
        self._html(
            pages.email_page(
                service.load_draft(store), last_sent if isinstance(last_sent, str) else None
            )
        )

    # POST -----------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        if not self._host_ok():
            return self._error(HTTPStatus.FORBIDDEN, "허용되지 않은 호스트입니다")
        if self.headers.get("X-NewsClip") != "1":
            return self._error(HTTPStatus.FORBIDDEN, "허용되지 않은 요청입니다")
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "::1"}:
            return self._error(HTTPStatus.FORBIDDEN, "허용되지 않은 출처입니다")
        path = urlsplit(self.path).path
        routes = {
            "/api/ping": self._api_ping,
            "/api/decision": self._api_decision,
            "/api/collect": self._api_collect,
            "/api/make-email": self._api_make_email,
            "/api/email/save": self._api_email_save,
            "/api/email/preview": self._api_email_preview,
            "/api/email/open": self._api_email_open,
            "/api/email/mailto": self._api_email_mailto,
            "/api/email/export": self._api_email_export,
            "/api/email/sent": self._api_email_sent,
            "/api/email/revert": self._api_email_revert,
            "/api/settings": self._api_settings,
        }
        handler = routes.get(path)
        if handler is None:
            return self._error(HTTPStatus.NOT_FOUND, "알 수 없는 요청입니다")
        try:
            handler(self._body_json())
        except (ValueError, KeyError, TypeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc) or "잘못된 요청입니다")
        except Exception as exc:  # noqa: BLE001
            logger.exception("POST %s failed", path)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(exc).__name__}: {exc}")

    def _api_ping(self, _: dict[str, Any]) -> None:
        self.state.last_ping = time.monotonic()
        self.state.pinged = True
        self._json({"ok": True})

    def _api_decision(self, data: dict[str, Any]) -> None:
        ids = [int(i) for i in data["ids"]]
        rep = int(data["id"])
        decision = data.get("decision", "")
        if decision not in (APPROVED, REJECTED, PENDING):
            raise ValueError("알 수 없는 결정입니다")
        if rep not in ids:
            raise ValueError("대표 기사가 묶음에 없습니다")
        store = Store2()
        store.set_decision(ids, PENDING)  # 대표 기사에만 결정을 기록한다
        if decision:
            store.set_decision([rep], decision)
        self._json({"ok": True})

    def _api_collect(self, _: dict[str, Any]) -> None:
        started = self.state.start_collect()
        self._json({"started": started})

    def _api_make_email(self, data: dict[str, Any]) -> None:
        try:
            draft = service.make_email(
                config.load(), Store2(), clear_undecided=bool(data.get("clear_undecided", True))
            )
        except service.NothingApproved as exc:
            raise ValueError(str(exc)) from None
        self._json({"ok": True, "items": len(draft.items)})

    def _draft_from(self, data: dict[str, Any]) -> Draft:
        raw = data.get("draft")
        if not isinstance(raw, dict):
            raise ValueError("초안 데이터가 없습니다")
        raw.setdefault("sender", "")
        for item in raw.get("items", []):
            item.setdefault("links", [])
            item.setdefault("include", True)
        return draft_from_dict(raw)

    def _api_email_save(self, data: dict[str, Any]) -> None:
        service.save_draft(Store2(), self._draft_from(data))
        self._json({"ok": True})

    def _api_email_preview(self, data: dict[str, Any]) -> None:
        self._json({"html": render_html(self._draft_from(data))})

    def _api_email_open(self, data: dict[str, Any]) -> None:
        draft = self._draft_from(data)
        service.save_draft(Store2(), draft)
        path = save_eml(draft, datetime.now().astimezone())
        open_in_mail_client(path)
        self._json({"ok": True, "path": str(path)})

    def _api_email_mailto(self, data: dict[str, Any]) -> None:
        draft = self._draft_from(data)
        service.save_draft(Store2(), draft)
        self._json({"url": mailto_url(draft)})

    def _api_email_export(self, data: dict[str, Any]) -> None:
        draft = self._draft_from(data)
        service.save_draft(Store2(), draft)
        kind = data.get("kind")
        if kind == "eml":
            payload = build_eml(draft, datetime.now().astimezone())
            name, mime = "clipping.eml", "message/rfc822"
        elif kind == "html":
            payload = render_html(draft).encode("utf-8")
            name, mime = "clipping.html", "text/html"
        else:
            raise ValueError("알 수 없는 형식입니다")
        self._json(
            {"filename": name, "mime": mime, "data": base64.b64encode(payload).decode("ascii")}
        )

    def _api_email_sent(self, _: dict[str, Any]) -> None:
        self._json({"ok": True, "count": service.mark_sent(Store2())})

    def _api_email_revert(self, _: dict[str, Any]) -> None:
        self._json({"ok": True, "count": service.revert_draft(Store2())})

    def _api_settings(self, data: dict[str, Any]) -> None:
        raw_sources = data.get("sources")
        # 빈 목록은 from_dict 가 기본 소스로 채워 버리므로, 변환 전에 원본을 검사한다
        if not isinstance(raw_sources, list) or not any(
            isinstance(s, dict) and s.get("enabled") for s in raw_sources
        ):
            raise ValueError("사용할 사이트가 하나 이상 있어야 합니다")
        settings = config.from_dict(data)
        ids = [s.id for s in settings.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("사이트 ID 가 중복되었습니다")
        requested = data.get("collect", {}).get("retention_days")
        config.save(settings)
        purged = service.purge_expired(settings, Store2())
        message = "저장했습니다."
        if purged:
            message += f" 보관 기간이 지난 기사 {purged}건을 삭제했습니다."
        if requested is not None and int(requested) < settings.collect.retention_days:
            message += f" (보관 기간은 수집 기간보다 짧을 수 없어 {settings.collect.retention_days}일로 맞췄습니다)"
        self._json(
            {"ok": True, "message": message, "retention_days": settings.collect.retention_days}
        )


def make_server(port: int, *, state: AppState | None = None) -> ThreadingHTTPServer:
    state = state or AppState(port)

    class Bound(Handler):
        pass

    Bound.state = state
    server = ThreadingHTTPServer(("127.0.0.1", port), Bound)
    server.daemon_threads = True
    server.app_state = state  # type: ignore[attr-defined]
    return server


def utc_now() -> datetime:  # 테스트에서 대체하기 쉽도록
    return datetime.now(UTC)
