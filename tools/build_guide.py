"""views/guide.py 를 실행해 그 내용을 단독 HTML(src/web_html/guide.html)로 만든다.

guide.py 가 원본이다. 여기서는 `streamlit` 대신 호출을 기록만 하는 가짜 모듈을 끼워
넣고 guide.py 를 그대로 실행하므로, f-string 이나 변수도 별도 해석 없이 계산된다.
생성된 HTML 은 Python 없이 브라우저에서 파일로 열 수 있다.

    uv run python tools/build_guide.py            # 생성
    uv run python tools/build_guide.py --check    # 최신인지 검사 (다르면 종료 코드 1)
    uv run python tools/build_guide.py --watch    # guide.py 가 바뀔 때마다 다시 생성
"""

from __future__ import annotations

import argparse
import html
import os
import re
import runpy
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE_PY = ROOT / "views" / "guide.py"
OUT_HTML = ROOT / "src" / "web_html" / "guide.html"

Block = tuple[str, str]  # (종류, 텍스트) — 종류: title | header | subheader | markdown | caption


class _Recorder:
    """streamlit 대신 쓰는 기록기. guide.py 가 쓰는 출력 함수만 허용한다."""

    SUPPORTED = ("title", "header", "subheader", "markdown", "caption")

    def __init__(self) -> None:
        self.blocks: list[Block] = []

    def __getattr__(self, name: str):
        if name not in self.SUPPORTED:
            raise NotImplementedError(
                f"guide.py 가 st.{name}() 을 쓰지만 tools/build_guide.py 가 지원하지 않습니다 "
                f"(지원: {', '.join(self.SUPPORTED)}). 빌드 스크립트에 추가하세요."
            )
        return lambda text: self.blocks.append((name, str(text)))


def collect_blocks(guide_py: Path = GUIDE_PY) -> list[Block]:
    """guide.py 를 (기본 설정으로) 실행해 출력 블록 목록을 얻는다."""
    recorder = _Recorder()
    fake_st = types.ModuleType("streamlit")
    fake_st.__dict__["__getattr__"] = recorder.__getattr__
    saved_st = sys.modules.get("streamlit")
    saved_home = os.environ.get("NEWSCLIP_HOME")
    sys.modules["streamlit"] = fake_st
    sys.path.insert(0, str(ROOT / "src"))
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["NEWSCLIP_HOME"] = tmp  # 사용자 설정이 아니라 기본값으로 만든다
            runpy.run_path(str(guide_py), run_name="__guide__")
    finally:
        sys.path.pop(0)
        if saved_st is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = saved_st
        if saved_home is None:
            os.environ.pop("NEWSCLIP_HOME", None)
        else:
            os.environ["NEWSCLIP_HOME"] = saved_home
    return recorder.blocks


# ── 마크다운 → HTML (guide.py 가 쓰는 부분집합) ─────────────────────────────

_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?![\s*])(.+?)(?<![\s*])\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_TABLE_SEP = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")
_OL = re.compile(r"^\d+\.\s+(.*)")
_UL = re.compile(r"^[-*]\s+(.*)")


def inline(text: str) -> str:
    codes: list[str] = []

    def stash(m: re.Match[str]) -> str:
        codes.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = _CODE.sub(stash, text)
    text = html.escape(text, quote=False)
    text = _LINK.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def markdown_to_html(src: str) -> str:
    """제목은 다루지 않는다(블록 종류로 처리). 표·목록·인용·문단·인라인 서식을 지원."""
    lines = src.strip("\n").splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
        elif (
            line.lstrip().startswith("|")
            and i + 1 < len(lines)
            and _TABLE_SEP.match(lines[i + 1].strip())
        ):
            head = _cells(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            out.append(
                "<table><thead><tr>"
                + "".join(f"<th>{inline(c)}</th>" for c in head)
                + "</tr></thead><tbody>"
                + "".join(
                    "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in rows
                )
                + "</tbody></table>"
            )
        elif line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i][1:].strip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(quote))}</blockquote>")
        elif _UL.match(line) or _OL.match(line):
            ordered = bool(_OL.match(line))
            pattern = _OL if ordered else _UL
            items: list[str] = []
            while i < len(lines):
                m = pattern.match(lines[i].rstrip())
                if m:
                    items.append(m.group(1))
                elif lines[i].startswith("  ") and items and lines[i].strip():
                    items[-1] += " " + lines[i].strip()  # 들여쓴 이어지는 줄
                else:
                    break
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(t)}</li>" for t in items) + f"</{tag}>")
        else:
            para = []
            while (
                i < len(lines)
                and lines[i].strip()
                and not lines[i].startswith(">")
                and not _UL.match(lines[i])
                and not _OL.match(lines[i])
                and not lines[i].lstrip().startswith("|")
            ):
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline('<br>'.join(para)).replace('&lt;br&gt;', '<br>')}</p>")
    return "\n".join(out)


# ── 페이지 ──────────────────────────────────────────────────────────────

CSS = """
:root{--bg:#fff;--fg:#1f2328;--muted:#656d76;--line:#d0d7de;--soft:#f6f8fa;--accent:#2b5fd9;--quote:#fff8c5}
@media(prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--muted:#8d96a0;--line:#30363d;--soft:#161b22;--accent:#6ea8fe;--quote:#2d2a12}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.7 -apple-system,"Apple SD Gothic Neo","Malgun Gothic",Arial,sans-serif}
.top{display:flex;justify-content:space-between;align-items:center;max-width:1100px;margin:0 auto;padding:14px 16px;border-bottom:1px solid var(--line);font-weight:700}
.top a{font-weight:400;font-size:14px;color:var(--accent);text-decoration:none}
.wrap{display:flex;gap:32px;max-width:1100px;margin:0 auto;padding:24px 16px}
nav{position:sticky;top:16px;align-self:flex-start;width:210px;flex:none;font-size:13px;max-height:calc(100vh - 32px);overflow:auto}
nav a{display:block;color:var(--muted);text-decoration:none;padding:3px 0}
nav a:hover{color:var(--accent)}nav a.sub{padding-left:14px}
main{min-width:0;flex:1}
h1{font-size:28px;margin:0 0 8px}h2{font-size:21px;margin:40px 0 8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:17px;margin:28px 0 6px}
code{background:var(--soft);padding:1px 5px;border-radius:4px;font-size:.92em}
table{border-collapse:collapse;margin:12px 0;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
th{background:var(--soft)}
blockquote{margin:12px 0;padding:8px 14px;background:var(--quote);border-left:4px solid #d4a72c;border-radius:4px}
.caption{color:var(--muted);font-size:13px;margin-top:32px}
.note{background:var(--soft);border:1px solid var(--line);border-radius:6px;padding:8px 12px;color:var(--muted);font-size:13px;margin-bottom:16px}
@media(max-width:760px){.wrap{display:block}nav{display:none}}
"""


SITE_TITLE = "뉴스 클리핑 사이트"
GITHUB_URL = "https://github.com/hupers77/ProjNewsClipping"
TOP_BAR = (
    f'<div class="top"><span>📰 {SITE_TITLE}</span>'
    f'<a href="{GITHUB_URL}" target="_blank" rel="noopener">GitHub</a></div>'
)


def render_page(blocks: list[Block]) -> str:
    body: list[str] = []
    toc: list[str] = []
    n = 0
    for kind, text in blocks:
        if kind == "title":
            body.append(f"<h1>{inline(text)}</h1>")
            body.append(
                '<div class="note">이 문서는 <code>views/guide.py</code> 에서 자동 생성되었으며, '
                "본문의 설정 수치는 <strong>기본값</strong> 기준입니다. 실제 값은 앱의 "
                "환경 설정 화면에서 확인·변경하세요.</div>"
            )
        elif kind in ("header", "subheader"):
            n += 1
            tag = "h2" if kind == "header" else "h3"
            cls = "" if kind == "header" else ' class="sub"'
            body.append(f'<{tag} id="s{n}">{inline(text)}</{tag}>')
            toc.append(f'<a{cls} href="#s{n}">{inline(text)}</a>')
        elif kind == "caption":
            body.append(f'<p class="caption">{inline(text)}</p>')
        else:
            body.append(markdown_to_html(text))
    title = next((t for k, t in blocks if k == "title"), "사용법")
    page_title = re.sub(r"[^\w\s·-]", "", title).strip() or "사용법"
    nav = "".join(toc)
    main_html = "\n".join(body)
    return (
        '<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(page_title)}</title>"
        f'<style>{CSS}</style></head><body>{TOP_BAR}<div class="wrap"><nav>{nav}</nav>'
        f"<main>\n{main_html}\n</main></div></body></html>\n"
    )


def build() -> str:
    return render_page(collect_blocks())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--check", action="store_true", help="guide.html 이 최신인지만 검사")
    ap.add_argument("--watch", action="store_true", help="guide.py 변경을 감시해 다시 생성")
    args = ap.parse_args(argv)

    if args.check:
        current = OUT_HTML.read_text(encoding="utf-8") if OUT_HTML.exists() else ""
        if current != build():
            print("guide.html 이 guide.py 와 다릅니다 — `uv run python tools/build_guide.py`")
            return 1
        print("guide.html 은 최신입니다")
        return 0

    def write() -> None:
        OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
        OUT_HTML.write_text(build(), encoding="utf-8")
        print(f"생성: {OUT_HTML.relative_to(ROOT)}")

    write()
    if args.watch:
        last = GUIDE_PY.stat().st_mtime
        print("guide.py 변경을 감시합니다 (Ctrl+C 로 종료)")
        while True:
            time.sleep(1)
            mtime = GUIDE_PY.stat().st_mtime
            if mtime != last:
                last = mtime
                try:
                    write()
                except Exception as exc:  # noqa: BLE001 - 편집 도중의 문법 오류에도 감시를 계속한다
                    print(f"실패: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
