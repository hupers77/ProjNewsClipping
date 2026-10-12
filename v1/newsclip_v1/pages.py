"""HTML 화면 조립 (표준 라이브러리만 사용). 모든 사용자·외부 입력은 html.escape 로 이스케이프한다."""

from __future__ import annotations

import html
import json
import threading
from datetime import datetime
from pathlib import Path

from newsclip import buildinfo
from newsclip import config as base_config
from newsclip.emailer import CATEGORY_LABELS, Draft
from newsclip.review import Candidate, ReviewResult
from newsclip.store import APPROVED, PENDING, REJECTED
from newsclip_v1 import VERSION
from newsclip_v1.config import Settings

GITHUB_URL = "https://github.com/hupers77/ProjNewsClipping"
BLOG_URL = "https://blog.naver.com/hupers"
SITE_TITLE = "뉴스 클리핑 사이트"
CATEGORIES = ("ai", "it", "hot")

e = html.escape


def _q(text: str) -> str:
    return e(text, quote=True)


MENU = (
    ("candidates", "/", "📰 후보 리스트"),
    ("email", "/email", "✉️ 이메일 보기·편집"),
    ("settings", "/settings", "⚙️ 환경 설정"),
    ("guide", "/guide", "📖 사용법"),
)


def layout(page: str, title: str, body: str, *, extra_head: str = "") -> str:
    nav = "".join(
        f'<a href="{href}" class="{"active" if key == page else ""}">{label}</a>'
        for key, href, label in MENU
    )
    try:
        ver = buildinfo.label().replace(f"v{buildinfo.version()}", f"v{VERSION}", 1)
    except Exception:  # noqa: BLE001 - 버전 표시 실패가 화면을 막으면 안 된다
        ver = f"v{VERSION}"
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · {e(SITE_TITLE)}</title>
<link rel="stylesheet" href="/static/app.css">{extra_head}
</head>
<body data-page="{e(page)}">
<div class="shell">
<aside>
  <div class="brand">📰 {e(SITE_TITLE)}</div>
  <div class="tag">주요 뉴스를 모아 후보를 고르고 메일로 만듭니다</div>
  <hr>
  <div class="label">메뉴</div>
  <nav>{nav}</nav>
  <hr>
  <div class="label">정보</div>
  <div class="info">소스 보기 : <a href="{GITHUB_URL}" target="_blank" rel="noopener">GitHub</a><br>
  개발자 블로그 : <a href="{BLOG_URL}" target="_blank" rel="noopener">{BLOG_URL}</a></div>
  <hr>
  <div class="ver">최종 개발 버전·일자 : {e(ver)}</div>
</aside>
<main>
<div class="topbar"><button id="side-toggle" class="icon" title="사이드바 접기/펴기">☰</button>
<h1>{e(title)}</h1></div>
{body}
</main>
</div>
<script src="/static/app.js"></script>
</body></html>"""


# ───────── 후보 리스트 ─────────


def _local(dt: datetime) -> str:
    return dt.astimezone().strftime("%m-%d %H:%M")


def _card(c: Candidate) -> str:
    rep = c.rep
    state = c.decision
    badge = {APPROVED: "✅ 승인", REJECTED: "🚫 거절", PENDING: ""}[state]
    meta = [
        CATEGORY_LABELS.get(rep.category, rep.category),
        e(rep.source_name),
        _local(rep.when),
        f"점수 {c.score}",
    ]
    if len(c.members) > 1:
        meta.append(f"관련 {len(c.members) - 1}건")
    if c.matched:
        meta.append("🔑 " + e(", ".join(c.matched)))
    snippet = rep.summary or rep.content[:200]
    snippet_html = (
        f'<div class="snippet">{e(snippet[:240])}{"…" if len(snippet) > 240 else ""}</div>'
        if snippet
        else ""
    )
    related = "".join(
        f'<li><a href="{_q(m.url)}" target="_blank" rel="noopener noreferrer">{e(m.title)}</a>'
        f" · {e(m.source_name)}</li>"
        for m in c.related
    )
    related_html = f"<div><b>관련 기사</b><ul>{related}</ul></div>" if related else ""
    body_text = (
        e(rep.content) if rep.content else "<i>(본문을 추출하지 못했습니다 — 요약만 사용합니다)</i>"
    )
    haystack = " ".join(m.title for m in c.members).lower()
    cls = "card" + (" approved" if state == APPROVED else " rejected" if state == REJECTED else "")
    return f"""<div class="{cls}" data-id="{rep.id}" data-ids="{_q(json.dumps(c.ids))}"
 data-cat="{_q(rep.category)}" data-state="{_q(state)}" data-cand="{1 if c.is_candidate else 0}"
 data-text="{_q(haystack)}">
<div class="row"><div class="body">
<div class="title"><a href="{_q(rep.url)}" target="_blank" rel="noopener noreferrer">{e(rep.title)}</a><span class="badge {state}"{"" if state else " hidden"}>{badge}</span></div>
<div class="meta">{" · ".join(meta)}</div>
{snippet_html}
<details><summary>본문 · 관련 기사 · 점수 상세</summary>
<div class="content">{body_text}</div>{related_html}
<div class="hint">신선도 {c.freshness} · 키워드 {c.keyword} · 화제성 {c.buzz}</div></details>
</div>
<div class="actions">
<button class="primary btn-approve"{" hidden" if state == APPROVED else ""}>✅ 승인</button>
<button class="btn-reject"{" hidden" if state != PENDING else ""}>🚫 거절</button>
<button class="btn-undo"{" hidden" if state == PENDING else ""}>{"승인 취소" if state == APPROVED else "거절 취소"}</button>
</div></div></div>"""


def candidates_page(
    settings: Settings, result: ReviewResult, *, collecting: bool, last_sent: str | None
) -> str:
    approved = sum(1 for c in result.candidates if c.decision == APPROVED)
    cats = sorted({c.rep.category for c in result.candidates}, key=_cat_rank)
    cat_boxes = "".join(
        f'<label><input type="checkbox" class="f-cat" value="{_q(k)}" checked> '
        f"{e(CATEGORY_LABELS.get(k, k))}</label>"
        for k in cats
    )
    cards = "".join(_card(c) for c in result.candidates)
    excluded = ""
    if result.excluded:
        rows = "".join(
            f'<li><a href="{_q(a.url)}" target="_blank" rel="noopener noreferrer">{e(a.title)}</a>'
            f" · {e(a.source_name)} · 제외어 <code>{e(w)}</code></li>"
            for a, w in result.excluded
        )
        excluded = f"<details><summary>제외된 기사 {len(result.excluded)}건 보기</summary><ul>{rows}</ul></details>"
    empty = (
        '<div class="empty">기사가 없습니다. <b>지금 수집</b>을 눌러 시작하세요.<br>'
        "(소스·기간은 환경 설정에서 바꿉니다)</div>"
        if not result.candidates
        else ""
    )
    running_flag = '<span id="collect-running" hidden></span>' if collecting else ""
    notice = (
        f'<div class="notice">마지막 발송 처리: {e(_local(datetime.fromisoformat(last_sent)))}</div>'
        if last_sent
        else ""
    )
    body = f"""{running_flag}{notice}
<div id="report" class="notice" hidden></div>
<div id="progress" class="notice progress"></div>
<div class="filters">
  <button id="collect" class="primary">🔄 지금 수집</button>
  <button id="make-email" disabled>✉️ 이메일 만들기 ({approved})</button>
  <span class="hint">최근 {settings.collect.days}일 · 묶음 <b id="count-shown">0</b>/{len(result.candidates)}건 ·
   제외 {len(result.excluded)}건 · 승인 <b id="count-approved">{approved}</b>건</span>
</div>
<div class="filters">
  <span>분류 {cat_boxes or "<span class='hint'>없음</span>"}</span>
  <label>상태 <select id="f-state" style="width:auto">
    <option value="">전체</option><option value="pending">미검토</option>
    <option value="approved">승인</option><option value="rejected">거절</option></select></label>
  <label><input type="checkbox" id="f-cand" checked> 후보만 보기</label>
  <input type="text" id="f-query" placeholder="제목 검색">
</div>
{empty}
<div id="list">{cards}</div>
<div id="no-match" class="empty" hidden>조건에 맞는 기사가 없습니다. 필터를 바꿔 보세요.</div>
{excluded}
<dialog id="make-dialog">
  <h3 style="margin-top:0">이메일 만들기</h3>
  <p>승인한 <b id="make-count">0</b>건을 이메일 초안으로 옮기고 <b>후보 리스트를 초기화</b>합니다.<br>
  승인·거절한 기사는 목록에서 사라지고 이후 수집에서도 다시 나타나지 않습니다.</p>
  <label><input type="checkbox" id="make-clear" checked> 미검토 기사도 함께 초기화</label>
  <div class="btns"><button id="make-cancel">취소</button>
  <button id="make-go" class="ok">만들기</button></div>
</dialog>"""
    return layout("candidates", "후보 리스트", body)


def _cat_rank(category: str) -> int:
    return CATEGORIES.index(category) if category in CATEGORIES else 99


# ───────── 이메일 ─────────


def _link_row(title: str = "", outlet: str = "", url: str = "") -> str:
    return (
        f'<tr><td><input type="text" class="l-title" value="{_q(title)}"></td>'
        f'<td><input type="text" class="l-outlet" value="{_q(outlet)}"></td>'
        f'<td><input type="text" class="l-url" value="{_q(url)}"></td>'
        '<td><button type="button" class="small l-del" title="삭제">✕</button></td></tr>'
    )


def email_page(draft: Draft | None, last_sent: str | None) -> str:
    if draft is None or not draft.items:
        sent = (
            f"<br><span class='hint'>마지막 발송 처리: {e(_local(datetime.fromisoformat(last_sent)))}</span>"
            if last_sent
            else ""
        )
        body = f"""<div class="empty">작성 중인 이메일 초안이 없습니다.{sent}<br><br>
<a class="btn primary" href="/">후보 리스트에서 기사를 승인하고 <b>이메일 만들기</b>를 누르세요</a></div>"""
        return layout("email", "이메일 보기·편집", body)

    items = []
    for it in draft.items:
        label = CATEGORY_LABELS.get(it.category, it.category)
        rows = "".join(_link_row(k.title, k.outlet, k.url) for k in it.links)
        items.append(
            f"""<details class="item{"" if it.include else " off"}" data-id="{it.article_id}" data-cat="{_q(it.category)}">
<summary>[{e(label)}] {e(it.title)}</summary>
<div class="inner">
<label><input type="checkbox" class="i-include"{" checked" if it.include else ""}> 메일에 포함</label>
<div class="field"><label>제목</label><input type="text" class="i-title" value="{_q(it.title)}"></div>
<div class="field"><label>요약</label><textarea class="i-summary" rows="5">{e(it.summary)}</textarea></div>
<table class="edit links"><thead><tr><th>링크 제목</th><th style="width:22%">매체</th><th>주소</th><th></th></tr></thead>
<tbody>{rows}</tbody></table>
<button type="button" class="small l-add" style="margin-top:6px">+ 링크 추가</button>
</div></details>"""
        )
    body = f"""<form id="email-form" onsubmit="return false">
<div class="emailgrid">
<div class="panel">
  <div class="field"><label for="e-subject">제목</label><input type="text" id="e-subject" value="{_q(draft.subject)}"></div>
  <div class="field"><label for="e-sender">보내는 사람</label><input type="text" id="e-sender" value="{_q(draft.sender)}" placeholder="홍길동 &lt;me@example.com&gt;"></div>
  <div class="field"><label for="e-to">받는 사람</label><input type="text" id="e-to" value="{_q(draft.recipients)}" placeholder="a@example.com, b@example.com"></div>
  <div class="field"><label for="e-intro">도입 문구</label><textarea id="e-intro" rows="3">{e(draft.intro)}</textarea></div>
  {"".join(items)}
  <div class="field"><label for="e-outro">맺음 문구</label><textarea id="e-outro" rows="3">{e(draft.outro)}</textarea></div>
</div>
<div class="panel preview"><iframe id="preview" title="이메일 미리보기"></iframe></div>
</div>
<div class="actionbar">
  <button id="b-save" type="button">💾 저장</button>
  <button id="b-open" type="button" class="primary" title="기본 메일 프로그램에서 새 메일 창(HTML 본문)을 엽니다">📨 메일 창 열기</button>
  <button id="b-mailto" type="button" title="서식 없는 텍스트 본문 (길면 잘림)">✉️ mailto (텍스트)</button>
  <button id="b-eml" type="button">⬇️ .eml</button>
  <button id="b-html" type="button">⬇️ .html</button>
  <span class="spacer"></span>
  <span id="dirty" class="dirty" hidden>● 저장하지 않은 변경</span>
  <button id="b-revert" type="button" class="danger" title="초안을 버리고 기사를 후보 리스트로 되돌립니다">↩ 초안 폐기</button>
  <button id="b-sent" type="button" class="ok">✅ 발송 처리</button>
</div>
</form>
<template id="link-row-template">{_link_row()}</template>"""
    return layout("email", "이메일 보기·편집", body)


# ───────── 환경 설정 ─────────


def _opt(value: str, options: tuple[str, ...], labels: dict[str, str] | None = None) -> str:
    return "".join(
        f'<option value="{_q(o)}"{" selected" if o == value else ""}>'
        f"{e((labels or {}).get(o, o))}</option>"
        for o in options
    )


def _source_row(s: base_config.Source | None = None) -> str:
    s = s or base_config.Source("", "", "rss", "", "it", "ko", True)
    return f"""<tr>
<td><input type="checkbox" class="s-on"{" checked" if s.enabled else ""}></td>
<td><input type="text" class="s-id" value="{_q(s.id)}" style="width:110px"></td>
<td><input type="text" class="s-name" value="{_q(s.name)}"></td>
<td><select class="s-type">{_opt(s.type, tuple(base_config.SOURCE_TYPES))}</select></td>
<td><input type="text" class="s-url" value="{_q(s.url)}"></td>
<td><select class="s-cat">{_opt(s.category, CATEGORIES, CATEGORY_LABELS)}</select></td>
<td><select class="s-lang">{_opt(s.lang, ("ko", "en"))}</select></td>
<td><input type="number" class="s-topn" value="{s.top_n}" style="width:64px"></td>
<td><input type="number" class="s-minp" value="{s.min_points}" style="width:72px"></td>
<td><button type="button" class="small row-del" title="삭제">✕</button></td></tr>"""


def _keyword_row(word: str = "", bonus: float = 10.0) -> str:
    return (
        f'<tr><td><input type="text" class="k-word" value="{_q(word)}"></td>'
        f'<td><input type="number" class="k-bonus" min="0" max="100" step="5" value="{bonus:g}"></td>'
        '<td><button type="button" class="small row-del">✕</button></td></tr>'
    )


def settings_page(settings: Settings, config_path: Path) -> str:
    c, f, r, m = settings.collect, settings.filters, settings.review, settings.email
    sources = "".join(_source_row(s) for s in settings.sources)
    keywords = "".join(_keyword_row(k.word, k.bonus) for k in f.include_keywords)
    body = f"""<p class="hint">저장 위치: <code>{e(str(config_path))}</code> (이 컴퓨터에만 저장됩니다) —
값을 고친 뒤 아래 <b>저장</b> 버튼을 눌러야 반영됩니다.</p>
<div id="settings-form">
<div class="tabs">
  <button class="on" data-tab="t-collect">수집</button><button data-tab="t-sources">사이트</button>
  <button data-tab="t-keywords">키워드</button><button data-tab="t-review">후보 선정</button>
  <button data-tab="t-email">이메일</button>
</div>

<div class="tabpane on" id="t-collect">
  <div class="grid2">
    <div class="field"><label for="c-days">수집 기간(일)</label>
      <input type="number" id="c-days" min="1" max="30" value="{c.days}">
      <div class="hint">최근 며칠간의 기사를 대상으로 할지</div></div>
    <div class="field"><label for="c-max">사이트당 최대 수집 건수</label>
      <input type="number" id="c-max" min="5" max="200" value="{c.max_items_per_source}"></div>
  </div>
  <div class="field"><label><input type="checkbox" id="c-fetch"{" checked" if c.fetch_content else ""}> 기사 본문 추출</label></div>
  <div class="field"><label for="c-chars">본문 추출 글자 수 상한</label>
    <input type="number" id="c-chars" min="100" max="20000" step="100" value="{c.content_max_chars}" style="max-width:240px"></div>
  <div class="field"><label for="c-retention">기사 보관 기간(일)</label>
    <input type="number" id="c-retention" min="1" max="3650" value="{c.retention_days}" style="max-width:240px">
    <div class="hint">수집한 지 이 일수가 지난 기사는 <b>수집·승인/거절·메일 발송 기사 모두</b> 삭제됩니다 (기본 30일).
    수집 기간보다 짧게 둘 수 없습니다.</div></div>
  <p class="hint">본문은 robots.txt 를 따르며, 요약·검토 용도로만 쓰고 메일에는 짧은 요약과 출처 링크만 담습니다.</p>
</div>

<div class="tabpane" id="t-sources">
  <p class="hint">체크를 끄면 수집하지 않습니다. 유형: <code>rss</code>·<code>sitemap</code>·<code>trends_rss</code>(주소),
  <code>google_news</code>(주소 칸에 검색어), <code>hackernews</code>(주소 불필요).
  <code>HN 상위 N</code>: 인기순 상위 몇 건까지 볼지. <code>HN 최소 추천</code>: 추천(점수)이 이 값 이상인 글만 가져옵니다.</p>
  <table class="edit" id="sources-table"><thead><tr><th>사용</th><th>ID</th><th>이름</th><th>유형</th>
  <th>주소 / 검색어</th><th>분류</th><th>언어</th><th>HN 상위 N</th><th>HN 최소 추천</th><th></th></tr></thead>
  <tbody>{sources}</tbody></table>
  <button type="button" id="add-source" class="small" style="margin-top:8px">+ 사이트 추가</button>
</div>

<div class="tabpane" id="t-keywords">
  <div class="grid2">
    <div><div class="field"><label for="f-exclude">제외 키워드</label>
      <textarea id="f-exclude" rows="10">{e(chr(10).join(f.exclude_keywords))}</textarea>
      <div class="hint">한 줄에 하나. 제목·요약에 있으면 후보에서 뺍니다.</div></div>
      <label><input type="checkbox" id="f-in-content"{" checked" if f.exclude_in_content else ""}> 본문에서도 제외 키워드 찾기</label></div>
    <div><label style="font-weight:600">포함 키워드(가산점)</label>
      <div class="hint">제목에 있으면 가산점 전부, 요약·본문에만 있으면 절반.</div>
      <table class="edit" id="keywords-table"><thead><tr><th>키워드</th><th style="width:90px">가산점</th><th></th></tr></thead>
      <tbody>{keywords}</tbody></table>
      <button type="button" id="add-keyword" class="small" style="margin-top:8px">+ 키워드 추가</button></div>
  </div>
</div>

<div class="tabpane" id="t-review">
  <p class="hint">LLM 없이 규칙으로 고릅니다. 점수 = 신선도·키워드·화제성의 가중 평균(0~100).</p>
  <div class="grid3">
    <div class="field"><label for="r-max">최대 후보 수</label><input type="number" id="r-max" min="1" max="200" value="{r.max_candidates}"></div>
    <div class="field"><label for="r-min">최소 점수</label><input type="number" id="r-min" min="0" max="100" step="5" value="{r.min_score:g}"></div>
    <div class="field"><label for="r-per">매체당 최대 후보 수 (0=무제한)</label><input type="number" id="r-per" min="0" max="50" value="{r.per_source_max}"></div>
  </div>
  <div class="field"><label for="r-cluster">같은 사건으로 묶는 제목 유사도 (0.2~0.9)</label>
    <input type="number" id="r-cluster" min="0.2" max="0.9" step="0.05" value="{r.cluster_threshold:g}" style="max-width:240px">
    <div class="hint">낮출수록 더 많이 묶입니다</div></div>
  <div class="grid3">
    <div class="field"><label for="r-wf">가중치: 신선도</label><input type="number" id="r-wf" min="0" max="1" step="0.05" value="{r.weight_freshness:g}"></div>
    <div class="field"><label for="r-wk">가중치: 키워드</label><input type="number" id="r-wk" min="0" max="1" step="0.05" value="{r.weight_keyword:g}"></div>
    <div class="field"><label for="r-wb">가중치: 화제성</label><input type="number" id="r-wb" min="0" max="1" step="0.05" value="{r.weight_buzz:g}"></div>
  </div>
</div>

<div class="tabpane" id="t-email">
  <div class="field"><label for="m-subject">제목 템플릿</label><input type="text" id="m-subject" value="{_q(m.subject_template)}">
    <div class="hint">{{date}} = 오늘 날짜</div></div>
  <div class="grid2">
    <div class="field"><label for="m-sender">보내는 사람</label><input type="text" id="m-sender" value="{_q(m.sender)}" placeholder="홍길동 &lt;me@example.com&gt;"></div>
    <div class="field"><label for="m-to">받는 사람 (쉼표로 구분, 비워도 됨)</label><input type="text" id="m-to" value="{_q(m.recipients)}"></div>
  </div>
  <div class="field"><label for="m-intro">도입 문구</label><textarea id="m-intro" rows="3">{e(m.intro)}</textarea></div>
  <div class="field"><label for="m-outro">맺음 문구</label><textarea id="m-outro" rows="3">{e(m.outro)}</textarea></div>
  <div class="grid2">
    <div class="field"><label for="m-sumchars">항목별 요약 글자 수</label><input type="number" id="m-sumchars" min="50" max="1000" step="10" value="{m.summary_chars}"></div>
    <div class="field"><label for="m-links">항목별 출처 링크 수</label><input type="number" id="m-links" min="1" max="10" value="{m.max_links}"></div>
  </div>
</div>

<div class="savebar"><button id="save" class="primary">💾 저장</button>
<span id="dirty" class="dirty" hidden>● 저장하지 않은 변경</span></div>
</div>
<template id="source-row-template">{_source_row()}</template>
<template id="keyword-row-template">{_keyword_row()}</template>"""
    return layout("settings", "환경 설정", body)


# ───────── 사용법 ─────────

_guide_lock = threading.Lock()


def guide_page(guide_py: Path, extra_paths: tuple[Path, ...]) -> str:
    """guide.py 를 실행해 읽는다 — guide.py 만 고치면 화면에 그대로 반영된다."""
    import importlib.util
    import sys

    root = Path(__file__).resolve().parents[2]
    candidates = [
        root / "tools" / "build_guide.py",
        Path(getattr(sys, "_MEIPASS", root)) / "tools" / "build_guide.py",
    ]
    module = sys.modules.get("_build_guide")
    if module is None:
        for path in candidates:
            if path.exists():
                spec = importlib.util.spec_from_file_location("_build_guide", path)
                assert spec and spec.loader
                module = importlib.util.module_from_spec(spec)
                sys.modules["_build_guide"] = module
                spec.loader.exec_module(module)
                break
        else:
            raise FileNotFoundError("tools/build_guide.py 를 찾을 수 없습니다")
    with _guide_lock:  # sys.modules / sys.path 를 잠시 바꾸므로 한 번에 하나씩
        blocks = module.collect_blocks(guide_py, use_defaults=False, extra_paths=extra_paths)
    parts = []
    for kind, text in blocks:
        if kind == "title":
            continue  # 화면 제목은 레이아웃이 그린다
        if kind == "header":
            parts.append(f"<h2>{module.inline(text)}</h2>")
        elif kind == "subheader":
            parts.append(f"<h3>{module.inline(text)}</h3>")
        elif kind == "caption":
            parts.append(f'<p class="caption">{module.inline(text)}</p>')
        else:
            parts.append(module.markdown_to_html(text))
    return layout("guide", "사용법", f'<div class="doc">{"".join(parts)}</div>')
