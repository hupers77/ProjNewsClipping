"""v1 저장소: 기존 Store 에 '처리 단계(phase)'를 더한다.

phase:
  active  — 후보 리스트에 보이는 기사 (기본값, 기존 DB 의 모든 기사)
  drafted — '이메일 만들기'로 이메일 초안에 담긴 승인 기사
  sent    — 사용자가 '발송 처리'한 기사
  cleared — '이메일 만들기' 때 목록에서 치워진 기사 (거절·미검토). 이후 수집에서 다시 나오지 않는다

url_hash 는 phase 와 상관없이 남아 있으므로 같은 기사는 보관 기간 동안 다시 수집되지 않는다.
기존 앱이 만든 DB 에는 열 하나를 더하기만 한다 (파괴적 변경 없음).
"""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from newsclip.store import Article, Store, _row

ACTIVE, DRAFTED, SENT, CLEARED = "active", "drafted", "sent", "cleared"


class Store2(Store):
    def __init__(self, path: Path | None = None) -> None:
        super().__init__(path)
        with closing(self._conn()) as conn, conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)")}
            if "phase" not in cols:
                conn.execute(
                    f"ALTER TABLE articles ADD COLUMN phase TEXT NOT NULL DEFAULT '{ACTIVE}'"
                )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_phase ON articles(phase)")

    def articles_since(self, since: datetime) -> list[Article]:
        """후보 리스트에 보일 기사만 (phase = active)."""
        with closing(self._conn()) as conn:
            rows = conn.execute(
                "SELECT * FROM articles WHERE phase=? "
                "AND COALESCE(published_at, collected_at) >= ? "
                "ORDER BY COALESCE(published_at, collected_at) DESC",
                (ACTIVE, since.astimezone(UTC).isoformat()),
            )
            return [_row(r) for r in rows]

    def set_phase(self, ids: Iterable[int], phase: str) -> None:
        with closing(self._conn()) as conn, conn:
            conn.executemany("UPDATE articles SET phase=? WHERE id=?", [(phase, i) for i in ids])

    def ids_in_phase(self, phase: str) -> list[int]:
        with closing(self._conn()) as conn:
            return [r[0] for r in conn.execute("SELECT id FROM articles WHERE phase=?", (phase,))]

    def purge_all_older_than(self, before: datetime) -> int:
        """수집한 지 오래된 기사를 상태와 상관없이 모두 지운다 (승인·거절·발송 포함)."""
        with closing(self._conn()) as conn, conn:
            cur = conn.execute(
                "DELETE FROM articles WHERE collected_at < ?",
                (before.astimezone(UTC).isoformat(),),
            )
            return cur.rowcount

    def counts(self) -> dict[str, int]:
        with closing(self._conn()) as conn:
            rows = conn.execute("SELECT phase, COUNT(*) FROM articles GROUP BY phase")
            out = {ACTIVE: 0, DRAFTED: 0, SENT: 0, CLEARED: 0}
            out.update({r[0]: r[1] for r in rows})
            return out
