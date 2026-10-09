"""SQLite 저장소 (표준 sqlite3)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from newsclip import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url_hash TEXT NOT NULL UNIQUE,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  source_id TEXT NOT NULL,
  source_name TEXT NOT NULL,
  category TEXT NOT NULL,
  lang TEXT NOT NULL DEFAULT '',
  published_at TEXT,
  collected_at TEXT NOT NULL,
  decision TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_articles_pub ON articles(published_at);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

APPROVED, REJECTED, PENDING = "approved", "rejected", ""


@dataclass
class Article:
    id: int
    url: str
    title: str
    summary: str
    content: str
    source_id: str
    source_name: str
    category: str
    lang: str
    published_at: datetime | None
    collected_at: datetime
    decision: str

    @property
    def when(self) -> datetime:
        return self.published_at or self.collected_at


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _row(r: sqlite3.Row) -> Article:
    return Article(
        id=r["id"],
        url=r["url"],
        title=r["title"],
        summary=r["summary"],
        content=r["content"],
        source_id=r["source_id"],
        source_name=r["source_name"],
        category=r["category"],
        lang=r["lang"],
        published_at=_dt(r["published_at"]),
        collected_at=datetime.fromisoformat(r["collected_at"]),
        decision=r["decision"],
    )


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.db_path()
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def known_hashes(self) -> set[str]:
        with closing(self._conn()) as conn:
            return {r[0] for r in conn.execute("SELECT url_hash FROM articles")}

    def add_articles(self, rows: Iterable[dict[str, object]]) -> int:
        """url_hash 가 이미 있으면 건너뛴다. 새로 들어간 건수를 돌려준다."""
        now = datetime.now(UTC).isoformat()
        added = 0
        with closing(self._conn()) as conn, conn:
            for r in rows:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO articles (url_hash,url,title,summary,content,source_id,"
                    "source_name,category,lang,published_at,collected_at) "
                    "VALUES (:url_hash,:url,:title,:summary,:content,:source_id,:source_name,"
                    ":category,:lang,:published_at,:collected_at)",
                    {
                        "summary": "",
                        "content": "",
                        "lang": "",
                        "published_at": None,
                        **r,
                        "collected_at": now,
                    },
                )
                added += cur.rowcount
        return added

    def articles_since(self, since: datetime) -> list[Article]:
        """발행(없으면 수집) 시각이 since 이후인 기사."""
        with closing(self._conn()) as conn:
            rows = conn.execute(
                "SELECT * FROM articles WHERE COALESCE(published_at, collected_at) >= ? "
                "ORDER BY COALESCE(published_at, collected_at) DESC",
                (since.astimezone(UTC).isoformat(),),
            )
            return [_row(r) for r in rows]

    def get(self, ids: Iterable[int]) -> list[Article]:
        ids = list(ids)
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        with closing(self._conn()) as conn:
            rows = conn.execute(f"SELECT * FROM articles WHERE id IN ({marks})", ids)
            return [_row(r) for r in rows]

    def set_decision(self, ids: Iterable[int], decision: str) -> None:
        with closing(self._conn()) as conn, conn:
            conn.executemany(
                "UPDATE articles SET decision=? WHERE id=?", [(decision, i) for i in ids]
            )

    def purge_older_than(self, before: datetime) -> int:
        """승인한 기사는 남기고 오래된 기사를 지운다."""
        with closing(self._conn()) as conn, conn:
            cur = conn.execute(
                "DELETE FROM articles WHERE COALESCE(published_at, collected_at) < ? "
                "AND decision != ?",
                (before.astimezone(UTC).isoformat(), APPROVED),
            )
            return cur.rowcount

    def get_kv(self, key: str) -> object | None:
        with closing(self._conn()) as conn:
            r = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return json.loads(r[0]) if r else None

    def set_kv(self, key: str, value: object) -> None:
        with closing(self._conn()) as conn, conn:
            conn.execute(
                "INSERT INTO kv(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )
