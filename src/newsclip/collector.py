"""기사 수집: RSS / Google 뉴스 검색 RSS → 정규화 → 본문 추출 → 저장."""

from __future__ import annotations

import calendar
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import feedparser
import httpx

from newsclip.config import CollectSettings, Settings, Source
from newsclip.store import Store
from newsclip.text import normalize_url, strip_html, url_hash

logger = logging.getLogger(__name__)

USER_AGENT = "ProjNewsClipping/0.1 (+personal news clipping)"
GNEWS_URL = "https://news.google.com/rss/search"
MAX_SUMMARY_CHARS = 2000


@dataclass
class SourceResult:
    source: str
    fetched: int = 0
    new: int = 0
    error: str = ""


@dataclass
class CollectReport:
    results: list[SourceResult] = field(default_factory=list)
    content_fetched: int = 0

    @property
    def new_total(self) -> int:
        return sum(r.new for r in self.results)


def _entry_time(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC) if parsed else None


def parse_feed(content: bytes, source: Source, since: datetime, max_items: int) -> list[dict]:
    """피드 바이트 → 저장용 dict 목록 (since 이전 제외, 최신순 max_items개)."""
    feed = feedparser.parse(content)
    if not feed.entries and feed.bozo:
        raise ValueError("피드를 해석하지 못했습니다")
    items: list[dict] = []
    for entry in feed.entries:
        title, link = strip_html(entry.get("title")), entry.get("link")
        if not title or not link:
            continue
        published = _entry_time(entry)
        if published is not None and published < since:
            continue
        outlet = (entry.get("source") or {}).get("title") or ""
        if outlet and title.endswith(f" - {outlet}"):  # Google 뉴스 제목 꼬리표 제거
            title = title[: -len(outlet) - 3].rstrip()
        url = normalize_url(link)
        items.append(
            {
                "url_hash": url_hash(url),
                "url": url,
                "title": title,
                "summary": strip_html(entry.get("summary"))[:MAX_SUMMARY_CHARS],
                "source_id": source.id,
                "source_name": outlet or source.name,
                "category": source.category,
                "lang": source.lang,
                "published_at": published.isoformat() if published else None,
            }
        )
    items.sort(key=lambda i: i["published_at"] or "", reverse=True)
    return items[:max_items]


def _fetch_source(
    client: httpx.Client, source: Source, since: datetime, cfg: CollectSettings
) -> tuple[SourceResult, list[dict]]:
    result = SourceResult(source.name)
    try:
        if source.type == "google_news":
            params = {"q": source.url, "hl": source.lang, "gl": "KR", "ceid": f"KR:{source.lang}"}
            resp = client.get(GNEWS_URL, params=params)
        else:
            resp = client.get(source.url)
        resp.raise_for_status()
        items = parse_feed(resp.content, source, since, cfg.max_items_per_source)
    except httpx.HTTPStatusError as exc:
        result.error = f"HTTP {exc.response.status_code}"
        return result, []
    except httpx.HTTPError as exc:
        result.error = f"요청 실패({type(exc).__name__})"
        return result, []
    except ValueError as exc:
        result.error = str(exc)
        return result, []
    result.fetched = len(items)
    return result, items


def trafilatura_extract(html: str) -> str | None:
    import trafilatura

    text: str | None = trafilatura.extract(html, include_comments=False, include_tables=False)
    return text


class ContentFetcher:
    """본문 추출. robots.txt 를 존중한다. 요약·분석 입력 전용이다."""

    def __init__(
        self,
        client: httpx.Client,
        max_chars: int,
        extractor: Callable[[str], str | None] = trafilatura_extract,
    ) -> None:
        self._client = client
        self._max = max_chars
        self._extract = extractor
        self._robots: dict[str, RobotFileParser | None] = {}

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser: RobotFileParser | None = RobotFileParser()
            try:
                resp = self._client.get(f"{origin}/robots.txt")
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())  # type: ignore[union-attr]
                elif 400 <= resp.status_code < 500:
                    parser = None
                else:
                    parser.parse(["User-agent: *", "Disallow: /"])  # type: ignore[union-attr]
            except httpx.HTTPError:
                parser.parse(["User-agent: *", "Disallow: /"])  # type: ignore[union-attr]
            self._robots[origin] = parser
        parser = self._robots[origin]
        return parser is None or parser.can_fetch(USER_AGENT, url)

    def fetch(self, url: str) -> str | None:
        if "news.google.com" in urlsplit(url).netloc or not self._allowed(url):
            return None
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            text = self._extract(resp.text)
        except Exception:  # noqa: BLE001 - 본문 추출 실패는 요약으로 대체하면 되므로 조용히 넘긴다
            logger.info("content fetch failed: %s", urlsplit(url).netloc)
            return None
        return text[: self._max] if text else None


def collect(
    settings: Settings,
    store: Store,
    progress: Callable[[str], None] | None = None,
    client: httpx.Client | None = None,
) -> CollectReport:
    """활성 소스를 모두 수집해 DB 에 넣는다. 이미 있는 URL 은 건너뛴다 (멱등)."""
    cfg = settings.collect
    since = datetime.now(UTC) - timedelta(days=cfg.days)
    report = CollectReport()
    own_client = client is None
    client = client or httpx.Client(
        timeout=cfg.request_timeout,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )
    try:
        sources = [s for s in settings.sources if s.enabled and s.url]
        if progress:
            progress(f"{len(sources)}개 소스 수집 중…")
        with ThreadPoolExecutor(max_workers=6) as pool:
            fetched = list(pool.map(lambda s: _fetch_source(client, s, since, cfg), sources))

        known = store.known_hashes()
        fresh: list[dict] = []
        for result, items in fetched:
            new_items = [i for i in items if i["url_hash"] not in known]
            known.update(i["url_hash"] for i in new_items)
            fresh.extend(new_items)
            result.new = len(new_items)
            report.results.append(result)

        if cfg.fetch_content and cfg.content_max_chars > 0 and fresh:
            if progress:
                progress(f"새 기사 {len(fresh)}건 본문 추출 중…")
            fetcher = ContentFetcher(client, cfg.content_max_chars)
            with ThreadPoolExecutor(max_workers=6) as pool:
                texts = list(pool.map(lambda i: fetcher.fetch(i["url"]), fresh))
            for item, text in zip(fresh, texts, strict=True):
                if text:
                    item["content"] = text
                    report.content_fetched += 1
        store.add_articles(fresh)
    finally:
        if own_client:
            client.close()
    return report
