"""승인한 후보 → 이메일 초안(편집 가능) → HTML / 텍스트 / .eml."""

from __future__ import annotations

import html
import subprocess
import sys
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote

from newsclip import paths
from newsclip.config import EmailSettings
from newsclip.review import Candidate
from newsclip.text import summarize

CATEGORY_LABELS = {"ai": "AI", "it": "IT", "hot": "핫 이슈"}
CATEGORY_ORDER = ("ai", "it", "hot")
MIN_WIDTH = 640  # 메일 본문 최소 너비(px)
MAX_WIDTH = MIN_WIDTH * 2  # 최대 너비는 최소의 2배 — 그 사이에서 창 크기에 맞춰 가변
MAILTO_LIMIT = 1800  # 일부 메일 클라이언트(Windows)의 mailto 길이 한계 대비


@dataclass
class Link:
    title: str
    outlet: str
    url: str


@dataclass
class EmailItem:
    article_id: int
    category: str
    title: str
    summary: str
    links: list[Link] = field(default_factory=list)
    include: bool = True


@dataclass
class Draft:
    subject: str
    recipients: str
    intro: str
    outro: str
    sender: str = ""
    items: list[EmailItem] = field(default_factory=list)


def _item_from(c: Candidate, cfg: EmailSettings) -> EmailItem:
    rep = c.rep
    source_text = rep.content or rep.summary
    links = [Link(rep.title, rep.source_name, rep.url)] + [
        Link(m.title, m.source_name, m.url) for m in c.related[: max(0, cfg.max_links - 1)]
    ]
    return EmailItem(
        rep.id, rep.category, rep.title, summarize(source_text, cfg.summary_chars), links
    )


def build_draft(
    approved: list[Candidate], cfg: EmailSettings, existing: Draft | None, today: date | None = None
) -> Draft:
    """승인 목록과 기존 초안을 합친다. 이미 편집한 항목은 유지하고, 승인 해제된 항목은 뺀다."""
    today = today or date.today()
    old = {i.article_id: i for i in (existing.items if existing else [])}
    items = [old.get(c.rep.id) or _item_from(c, cfg) for c in approved]
    items.sort(
        key=lambda i: CATEGORY_ORDER.index(i.category) if i.category in CATEGORY_ORDER else 99
    )  # 안정 정렬: 같은 분류 안에서는 점수 순 유지
    if existing:
        return Draft(
            existing.subject,
            existing.recipients,
            existing.intro,
            existing.outro,
            existing.sender or cfg.sender,
            items,
        )
    return Draft(
        subject=cfg.subject_template.format(date=f"{today:%Y-%m-%d}"),
        recipients=cfg.recipients,
        intro=cfg.intro,
        outro=cfg.outro,
        sender=cfg.sender,
        items=items,
    )


def draft_to_dict(d: Draft) -> dict:
    return asdict(d)


def draft_from_dict(data: dict) -> Draft:
    items = [
        EmailItem(**{**i, "links": [Link(**link) for link in i.get("links", [])]})
        for i in data.get("items", [])
    ]
    return Draft(
        data["subject"],
        data["recipients"],
        data["intro"],
        data["outro"],
        data.get("sender", ""),
        items,
    )


def _included(d: Draft) -> list[EmailItem]:
    return [i for i in d.items if i.include]


def _paragraphs(text: str) -> str:
    return "".join(
        f'<p style="margin:0 0 8px;">{html.escape(p)}</p>' for p in text.splitlines() if p.strip()
    )


def render_html(d: Draft) -> str:
    e = html.escape
    parts = [
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="background:#f4f5f7;"><tr><td align="center" style="padding:24px 12px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="min-width:{MIN_WIDTH}px;max-width:{MAX_WIDTH}px;width:100%;'
        "background:#ffffff;border-radius:8px;"
        "font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',Arial,sans-serif;"
        'color:#222;">'
        '<tr><td style="padding:28px 28px 8px;"><div style="font-size:22px;font-weight:700;">'
        f"{e(d.subject)}</div></td></tr>"
    ]
    if d.intro.strip():
        parts.append(
            '<tr><td style="padding:8px 28px 0;font-size:14px;line-height:1.65;">'
            f"{_paragraphs(d.intro)}</td></tr>"
        )
    current = None
    for item in _included(d):
        if item.category != current:
            current = item.category
            parts.append(
                '<tr><td style="padding:20px 28px 0;"><div style="font-size:13px;font-weight:700;'
                'color:#2b5fd9;border-bottom:2px solid #2b5fd9;padding-bottom:4px;">'
                f"{e(CATEGORY_LABELS.get(current, current))}</div></td></tr>"
            )
        links = "".join(
            f'<li style="margin:2px 0;"><a href="{e(k.url, quote=True)}" target="_blank" '
            f'rel="noopener noreferrer" style="color:#2b5fd9;text-decoration:none;">{e(k.title)}'
            f'</a> <span style="color:#999;">· {e(k.outlet)}</span></li>'
            for k in item.links
        )
        summary = (
            f'<div style="font-size:14px;line-height:1.65;margin-top:6px;">{e(item.summary)}</div>'
            if item.summary.strip()
            else ""
        )
        link_list = (
            f'<ul style="font-size:13px;line-height:1.6;margin:8px 0 0;padding-left:20px;">'
            f"{links}</ul>"
            if links
            else ""
        )
        parts.append(
            '<tr><td style="padding:16px 28px 0;">'
            f'<div style="font-size:17px;font-weight:700;line-height:1.4;">{e(item.title)}</div>'
            f"{summary}{link_list}</td></tr>"
        )
    if d.outro.strip():
        parts.append(
            '<tr><td style="padding:24px 28px 0;font-size:14px;line-height:1.65;">'
            f"{_paragraphs(d.outro)}</td></tr>"
        )
    parts.append('<tr><td style="padding:16px 28px 28px;"></td></tr></table></td></tr></table>')
    return (
        '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
        f'<title>{e(d.subject)}</title></head><body style="margin:0;">'
        + "".join(parts)
        + "</body></html>\n"
    )


def render_text(d: Draft) -> str:
    lines = []
    if d.intro.strip():
        lines += [d.intro.strip(), ""]
    current = None
    for item in _included(d):
        if item.category != current:
            current = item.category
            lines += [f"[{CATEGORY_LABELS.get(current, current)}]", ""]
        lines.append(f"■ {item.title}")
        if item.summary.strip():
            lines.append(item.summary.strip())
        lines += [f"  · {k.title} ({k.outlet}) {k.url}" for k in item.links]
        lines.append("")
    if d.outro.strip():
        lines.append(d.outro.strip())
    return "\n".join(lines).rstrip() + "\n"


def build_eml(d: Draft, now: datetime) -> bytes:
    """메일 앱에서 새 편지로 열리는 .eml (X-Unsent)."""
    msg = EmailMessage()
    msg["Subject"] = d.subject
    if d.sender.strip():
        msg["From"] = d.sender.strip()
    if d.recipients.strip():
        msg["To"] = d.recipients.strip()
    msg["Date"] = format_datetime(now)
    msg["X-Unsent"] = "1"
    msg.set_content(render_text(d), charset="utf-8")
    msg.add_alternative(render_html(d), subtype="html", charset="utf-8")
    return msg.as_bytes()


def mailto_url(d: Draft) -> str:
    """텍스트 본문만 담은 mailto (너무 길면 잘라 안내문을 붙인다)."""
    body = render_text(d)
    if len(quote(body)) > MAILTO_LIMIT:
        body = body[: MAILTO_LIMIT // 4].rstrip() + "\n…(길어서 일부만 담았습니다)\n"
    to = quote(d.recipients.replace(" ", ""), safe=",@")
    return f"mailto:{to}?subject={quote(d.subject)}&body={quote(body)}"


def save_eml(d: Draft, now: datetime) -> Path:
    path = paths.mail_dir() / f"clipping-{now:%Y%m%d-%H%M%S}.eml"
    path.write_bytes(build_eml(d, now))
    return path


def open_in_mail_client(path: Path) -> None:
    """OS 기본 프로그램으로 .eml 을 연다 (기본 메일 클라이언트가 메일 창을 연다)."""
    if sys.platform == "win32":
        import os

        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=True)
    else:
        subprocess.run(["xdg-open", str(path)], check=True)


def open_mailto(d: Draft) -> None:
    webbrowser.open(mailto_url(d))
