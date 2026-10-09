"""환경 설정 (로컬 YAML 파일에 저장)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

import yaml

from newsclip import paths


@dataclass
class Source:
    id: str
    name: str
    type: str = "rss"  # rss | google_news
    url: str = ""  # rss: 피드 주소 / google_news: 검색어
    category: str = "it"
    lang: str = "ko"
    enabled: bool = True


@dataclass
class Keyword:
    word: str
    bonus: float = 10.0  # 포함 키워드 가산점


@dataclass
class CollectSettings:
    days: int = 3  # 최근 며칠간의 기사를 대상으로 할지
    fetch_content: bool = True  # 기사 본문 추출 여부
    content_max_chars: int = 1500  # 본문 추출 글자 길이 상한
    max_items_per_source: int = 50
    request_timeout: float = 15.0


@dataclass
class FilterSettings:
    exclude_keywords: list[str] = field(default_factory=list)
    exclude_in_content: bool = False  # 제목·요약 외에 본문에서도 제외 키워드를 찾을지
    include_keywords: list[Keyword] = field(default_factory=list)


@dataclass
class ReviewSettings:
    """LLM 없이 규칙으로 후보를 고르는 기준."""

    max_candidates: int = 30
    min_score: float = 20.0
    per_source_max: int = 5  # 한 매체에서 후보로 올릴 최대 건수 (0 = 제한 없음)
    cluster_threshold: float = 0.5  # 같은 사건으로 묶는 제목 유사도(0~1)
    weight_freshness: float = 0.4
    weight_keyword: float = 0.4
    weight_buzz: float = 0.2


@dataclass
class EmailSettings:
    subject_template: str = "뉴스 클리핑 {date}"
    recipients: str = ""  # 쉼표로 구분
    intro: str = "안녕하세요. 이번에 선별한 주요 뉴스를 공유드립니다."
    outro: str = "감사합니다."
    summary_chars: int = 220
    max_links: int = 3  # 항목당 관련 기사 링크 수


@dataclass
class Settings:
    collect: CollectSettings = field(default_factory=CollectSettings)
    filters: FilterSettings = field(default_factory=FilterSettings)
    review: ReviewSettings = field(default_factory=ReviewSettings)
    email: EmailSettings = field(default_factory=EmailSettings)
    sources: list[Source] = field(default_factory=list)


def default_sources() -> list[Source]:
    def rss(id: str, name: str, url: str, category: str, lang: str) -> Source:
        return Source(id, name, "rss", url, category, lang)

    return [
        rss("geeknews", "GeekNews", "https://news.hada.io/rss/news", "it", "ko"),
        rss("etnews", "전자신문", "https://rss.etnews.com/Section901.xml", "it", "ko"),
        rss("zdnet_korea", "ZDNet Korea", "https://feeds.feedburner.com/zdkorea", "it", "ko"),
        rss("techcrunch", "TechCrunch", "https://techcrunch.com/feed/", "it", "en"),
        rss("the_verge", "The Verge", "https://www.theverge.com/rss/index.xml", "it", "en"),
        rss("aitimes", "AI타임스", "https://www.aitimes.com/rss/allArticle.xml", "ai", "ko"),
        rss("openai_news", "OpenAI News", "https://openai.com/news/rss.xml", "ai", "en"),
        rss("google_ai", "Google AI Blog", "https://blog.google/technology/ai/rss/", "ai", "en"),
        Source("gnews_ai", "Google 뉴스: AI", "google_news", "인공지능 OR AI", "ai", "ko", False),
    ]


def _build(cls: type, data: Any) -> Any:
    """dict → dataclass (알 수 없는 키는 무시, 누락된 키는 기본값)."""
    if not isinstance(data, dict):
        return cls()
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in known})


def from_dict(data: dict[str, Any]) -> Settings:
    filters = _build(FilterSettings, data.get("filters"))
    filters.include_keywords = [
        _build(Keyword, k) if isinstance(k, dict) else Keyword(str(k))
        for k in (data.get("filters") or {}).get("include_keywords", [])
    ]
    sources = data.get("sources")
    return Settings(
        collect=_build(CollectSettings, data.get("collect")),
        filters=filters,
        review=_build(ReviewSettings, data.get("review")),
        email=_build(EmailSettings, data.get("email")),
        sources=[_build(Source, s) for s in sources] if sources else default_sources(),
    )


def load() -> Settings:
    path = paths.config_path()
    if not path.exists():
        return from_dict({})
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return from_dict(data)


def save(settings: Settings) -> None:
    text = yaml.safe_dump(asdict(settings), allow_unicode=True, sort_keys=False)
    paths.config_path().write_text(text, encoding="utf-8")
