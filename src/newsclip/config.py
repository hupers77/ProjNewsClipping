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
    type: str = "rss"  # rss | sitemap | google_news | hackernews | trends_rss
    url: str = ""  # rss·sitemap·trends_rss: 주소 / google_news: 검색어 / hackernews: 불필요
    category: str = "it"
    lang: str = "ko"
    enabled: bool = True
    top_n: int = 30  # hackernews: 상위 몇 건을 볼지
    min_points: int = 150  # hackernews: 최소 추천 수


SOURCE_TYPES = ["rss", "sitemap", "google_news", "hackernews", "trends_rss"]


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
    """기존 BlogCreator 의 소스 구성 (네이버 검색 API 소스는 인증이 필요해 제외)."""

    def rss(id: str, name: str, url: str, category: str, lang: str, enabled: bool = True) -> Source:
        return Source(id, name, "rss", url, category, lang, enabled)

    return [
        # IT
        rss("geeknews", "GeekNews", "https://news.hada.io/rss/news", "it", "ko"),
        rss("etnews", "전자신문", "https://rss.etnews.com/Section901.xml", "it", "ko"),
        rss("zdnet_korea", "ZDNet Korea", "https://feeds.feedburner.com/zdkorea", "it", "ko"),
        rss(
            "industrynews",
            "산업일보",
            "https://www.industrynews.co.kr/rss/allArticle.xml",
            "it",
            "ko",
        ),
        rss("techcrunch", "TechCrunch", "https://techcrunch.com/feed/", "it", "en"),
        rss("the_verge", "The Verge", "https://www.theverge.com/rss/index.xml", "it", "en"),
        Source("hackernews", "Hacker News", "hackernews", "", "it", "en"),
        rss(
            "industryjournal",
            "인더스트리저널",
            "https://industryjournal.co.kr/rss.php",
            "it",
            "ko",
        ),
        # AI
        rss("aitimes", "AI타임스", "https://www.aitimes.com/rss/allArticle.xml", "ai", "ko"),
        rss("aitimes_kr", "AI타임스(kr)", "https://www.aitimes.kr/rss/allArticle.xml", "ai", "ko"),
        Source("hellot", "헬로티", "sitemap", "https://www.hellot.net/sitemap.xml", "ai", "ko"),
        rss("cio_kr", "CIO Korea", "https://www.cio.com/kr/feed/", "ai", "ko"),
        rss("itworld_kr", "ITWorld Korea", "https://www.itworld.co.kr/feed/", "ai", "ko"),
        rss(
            "assembly_magazine",
            "Assembly Magazine",
            "https://www.assemblymag.com/rss/17",
            "ai",
            "en",
            False,
        ),
        Source(
            "assembly_magazine_gn",
            "Assembly Magazine (Google 뉴스)",
            "google_news",
            "site:assemblymag.com",
            "ai",
            "en",
        ),
        rss("openai_news", "OpenAI News", "https://openai.com/news/rss.xml", "ai", "en"),
        rss(
            "google_ai_blog", "Google AI Blog", "https://blog.google/technology/ai/rss/", "ai", "en"
        ),
        rss(
            "huggingface_blog",
            "Hugging Face Blog",
            "https://huggingface.co/blog/feed.xml",
            "ai",
            "en",
        ),
        Source(
            "google_news_ai_ko",
            "Google 뉴스: 제조·스마트팩토리 AI",
            "google_news",
            "제조 공장 스마트팩토리 AI Industry",
            "ai",
            "ko",
        ),
        # 핫 이슈
        Source(
            "google_trends_kr",
            "Google 트렌드(KR)",
            "trends_rss",
            "https://trends.google.com/trending/rss?geo=KR",
            "hot",
            "ko",
        ),
        rss(
            "industrynews_top",
            "산업일보 인기기사",
            "https://www.industrynews.co.kr/rss/clickTop.xml",
            "hot",
            "ko",
        ),
    ]


def default_filters() -> FilterSettings:
    """기존 BlogCreator 의 제외·포함 키워드 (분류별 목록을 합쳐 중복 제거)."""
    include = [
        # 기존 AI 분류
        "제조",
        "AX",
        "AI",
        "피지컬",
        "생산",
        "공장",
        "스마트공장",
        "스마트팩토리",
        "SDF",
        "industry",
        "산업",
        "factory",
        "manufacturing",
        "automation",
        # 기존 IT 분류
        "MES",
        "SmartFactory",
        "다크팩토리",
        "공장자동화",
        "제조AI",
        "디지털전환",
        "무인화",
        "자동화",
    ]
    return FilterSettings(
        exclude_keywords=["광고", "포토", "부고", "인사"],
        include_keywords=[Keyword(w) for w in include],
    )


def _build(cls: type, data: Any) -> Any:
    """dict → dataclass (알 수 없는 키는 무시, 누락된 키는 기본값)."""
    if not isinstance(data, dict):
        return cls()
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in known})


def from_dict(data: dict[str, Any]) -> Settings:
    raw_filters = data.get("filters")
    if raw_filters is None:
        filters = default_filters()
    else:
        filters = _build(FilterSettings, raw_filters)
        filters.include_keywords = [
            _build(Keyword, k) if isinstance(k, dict) else Keyword(str(k))
            for k in raw_filters.get("include_keywords", [])
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
