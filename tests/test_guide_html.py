"""views/guide.py ↔ src/web_html/guide.html 동기화 검사와 마크다운 변환 검사."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def build_guide():
    spec = importlib.util.spec_from_file_location("build_guide", ROOT / "tools" / "build_guide.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_guide"] = module
    spec.loader.exec_module(module)
    return module


def test_guide_html_is_up_to_date(build_guide):
    """guide.py 를 고치고 HTML 을 다시 만들지 않았다면 실패한다."""
    current = (ROOT / "src" / "web_html" / "guide.html").read_text(encoding="utf-8")
    assert current == build_guide.build(), (
        "guide.html 이 guide.py 와 다릅니다 — `uv run python tools/build_guide.py`"
    )


def test_every_guide_call_is_captured(build_guide):
    kinds = [k for k, _ in build_guide.collect_blocks()]
    assert kinds[0] == "title" and "header" in kinds and "markdown" in kinds


def test_unsupported_streamlit_call_fails_loudly(build_guide, tmp_path):
    bad = tmp_path / "bad_guide.py"
    bad.write_text("import streamlit as st\nst.dataframe([])\n", encoding="utf-8")
    with pytest.raises(NotImplementedError, match="dataframe"):
        build_guide.collect_blocks(bad)


def test_markdown_rendering(build_guide):
    md = build_guide.markdown_to_html
    assert "<strong>굵게</strong>" in md("**굵게**")
    assert "<em>기울임</em>을" in md("*기울임*을")
    assert "<code>a&lt;b</code>" in md("`a<b`")
    assert "<ol><li>하나</li><li>둘</li></ol>" == md("1. 하나\n2. 둘")
    assert "<ul><li>가</li><li>나</li></ul>" == md("- 가\n- 나")
    table = md("| a | b |\n|---|---|\n| 1 | **2** |")
    assert "<th>a</th>" in table and "<td><strong>2</strong></td>" in table
    assert md("> 💡 인용").startswith("<blockquote>")
    assert "<script>" not in md("<script>alert(1)</script>")
