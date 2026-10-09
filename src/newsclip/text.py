"""URL·텍스트 유틸."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from selectolax.lexbor import LexborHTMLParser

_TRACKING_KEYS = {"fbclid", "gclid", "msclkid", "igshid", "mc_cid", "mc_eid"}
_DEFAULT_PORTS = {"http": 80, "https": 443}
_WS = re.compile(r"\s+")
_TAGLIKE = re.compile(r"<[^>]+>|&[#\w]+;")
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def normalize_url(url: str) -> str:
    """스킴/호스트 소문자, 추적 파라미터·프래그먼트 제거, 쿼리 정렬, 끝 슬래시 정리."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host if port is None or _DEFAULT_PORTS.get(scheme) == port else f"{host}:{port}"
    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_KEYS and not k.lower().startswith("utm_")
    )
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))


def url_hash(normalized_url: str) -> str:
    return hashlib.sha1(normalized_url.encode("utf-8"), usedforsecurity=False).hexdigest()


def clean_text(text: str) -> str:
    return _WS.sub(" ", text).strip()


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    if _TAGLIKE.search(text):
        text = LexborHTMLParser(text).text(separator=" ")
    return clean_text(text)


def trigrams(text: str) -> frozenset[str]:
    s = _NON_WORD.sub("", text.lower())
    if len(s) < 3:
        return frozenset({s}) if s else frozenset()
    return frozenset(s[i : i + 3] for i in range(len(s) - 2))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_SENTENCE_END = re.compile(r"(?<=[.!?。])\s+|(?<=다\.)\s*")


def summarize(text: str, max_chars: int) -> str:
    """규칙 기반 요약: 앞쪽 문장부터 max_chars 이내로 채운다 (LLM 없음)."""
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    out = ""
    for sentence in _SENTENCE_END.split(text):
        if not sentence:
            continue
        if out and len(out) + len(sentence) + 1 > max_chars:
            break
        out = f"{out} {sentence}".strip()
        if len(out) >= max_chars:
            break
    if len(out) > max_chars:
        out = out[: max_chars - 1].rstrip() + "…"
    return out
