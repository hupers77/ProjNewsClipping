from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from newsclip.store import Store

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWSCLIP_HOME", str(tmp_path))


def _seed() -> None:
    now = datetime.now(UTC)
    Store().add_articles(
        [
            {
                "url_hash": f"h{i}",
                "url": f"https://e.com/{i}",
                "title": f"서로 다른 기사 제목 {i}번 {'가나다라마바사'[i]}",
                "summary": "요약 문장입니다.",
                "source_id": f"s{i}",
                "source_name": f"매체{i}",
                "category": "it",
                "published_at": (now - timedelta(hours=i)).isoformat(),
            }
            for i in range(3)
        ]
    )


@pytest.mark.parametrize("page", ["views/candidates.py", "views/settings.py", "views/guide.py"])
def test_pages_render(page):
    _seed()
    at = AppTest.from_file(str(ROOT / page), default_timeout=30).run()
    assert not at.exception


def test_approve_then_email_page():
    _seed()
    at = AppTest.from_file(str(ROOT / "views/candidates.py"), default_timeout=30).run()
    approve = next(b for b in at.button if b.label == "✅ 승인")
    approve.click()
    at.run()
    assert not at.exception
    em = AppTest.from_file(str(ROOT / "views/email.py"), default_timeout=30).run()
    assert not em.exception
    assert any("뉴스 클리핑" in t.value for t in em.text_input)
