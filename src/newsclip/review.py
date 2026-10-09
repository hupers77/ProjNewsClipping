"""LLM 없는 규칙 기반 후보 선정: 제외 키워드 → 유사 기사 묶기 → 점수화 → 후보 컷오프.

점수(0~100) = 신선도·키워드 가산점·화제성(묶인 기사 수/매체 수)의 가중 평균.
설정이 바뀌어도 다시 수집하지 않고 저장된 기사로 바로 재계산한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from newsclip.config import Settings
from newsclip.store import APPROVED, PENDING, REJECTED, Article, Store
from newsclip.text import jaccard, trigrams

SUMMARY_CHARS = 200
SUMMARY_KEYWORD_RATIO = 0.5  # 제목 밖(요약·본문)에서 일치한 키워드는 가산점을 절반만


@dataclass
class Candidate:
    rep: Article
    members: list[Article]
    score: float
    freshness: float
    keyword: float
    buzz: float
    matched: list[str]
    is_candidate: bool = False

    @property
    def decision(self) -> str:
        decisions = {m.decision for m in self.members}
        if APPROVED in decisions:
            return APPROVED
        if REJECTED in decisions:
            return REJECTED
        return PENDING

    @property
    def related(self) -> list[Article]:
        return [m for m in self.members if m.id != self.rep.id]

    @property
    def ids(self) -> list[int]:
        return [m.id for m in self.members]


@dataclass
class ReviewResult:
    candidates: list[Candidate] = field(default_factory=list)  # 점수 내림차순
    excluded: list[tuple[Article, str]] = field(default_factory=list)  # (기사, 일치한 제외어)


def excluded_by(article: Article, words: list[str], in_content: bool) -> str | None:
    text = f"{article.title} {article.summary}"
    if in_content:
        text += f" {article.content}"
    low = text.lower()
    return next((w for w in words if w and w.lower() in low), None)


def keyword_score(article: Article, keywords: list[tuple[str, float]]) -> tuple[float, list[str]]:
    title = article.title.lower()
    body = f"{article.summary} {article.content}".lower()
    total, matched = 0.0, []
    for word, bonus in keywords:
        w = word.lower()
        if not w:
            continue
        if w in title:
            total += bonus
            matched.append(word)
        elif w in body:
            total += bonus * SUMMARY_KEYWORD_RATIO
            matched.append(word)
    return total, matched


def cluster(articles: list[Article], threshold: float) -> list[list[Article]]:
    """제목/제목+요약 3-gram Jaccard 로 같은 사건 기사를 묶는다 (최신 기사부터, 결정적)."""
    feats = {
        a.id: (trigrams(a.title), trigrams(f"{a.title} {a.summary[:SUMMARY_CHARS]}"))
        for a in articles
    }
    groups: list[list[Article]] = []
    for art in sorted(articles, key=lambda a: (-a.when.timestamp(), a.id)):
        t, ts = feats[art.id]
        best_i, best = -1, 0.0
        for i, group in enumerate(groups):
            score = max(max(jaccard(t, feats[m.id][0]), jaccard(ts, feats[m.id][1])) for m in group)
            if score >= threshold and score > best:
                best_i, best = i, score
        if best_i < 0:
            groups.append([art])
        else:
            groups[best_i].append(art)
    return groups


def _freshness(latest: datetime, now: datetime, days: int) -> float:
    age_h = max(0.0, (now - latest).total_seconds() / 3600)
    return max(0.0, 100.0 * (1 - age_h / (days * 24)))


def _buzz(count: int, sources: int) -> float:
    return float(min(100, (count - 1) * 20 + (sources - 1) * 15))


def review(settings: Settings, store: Store, now: datetime | None = None) -> ReviewResult:
    now = now or datetime.now(UTC)
    cfg, flt, col = settings.review, settings.filters, settings.collect
    articles = store.articles_since(now - timedelta(days=col.days))

    result = ReviewResult()
    kept: list[Article] = []
    for art in articles:
        word = excluded_by(art, flt.exclude_keywords, flt.exclude_in_content)
        # 이미 승인한 기사는 제외어를 새로 추가해도 사라지지 않게 둔다
        if word and art.decision != APPROVED:
            result.excluded.append((art, word))
        else:
            kept.append(art)

    keywords = [(k.word, k.bonus) for k in flt.include_keywords]
    total_w = (cfg.weight_freshness + cfg.weight_keyword + cfg.weight_buzz) or 1.0
    for group in cluster(kept, cfg.cluster_threshold):
        per = [(m, *keyword_score(m, keywords)) for m in group]
        rep = max(
            per, key=lambda x: (x[0].decision == APPROVED, x[1], len(x[0].content), x[0].when)
        )[0]
        matched = sorted({w for _, _, ms in per for w in ms})
        kw = min(100.0, max(p[1] for p in per))
        fresh = _freshness(max(m.when for m in group), now, col.days)
        buzz = _buzz(len(group), len({m.source_id for m in group}))
        score = (
            cfg.weight_freshness * fresh + cfg.weight_keyword * kw + cfg.weight_buzz * buzz
        ) / total_w
        members = sorted(group, key=lambda m: m.when, reverse=True)
        result.candidates.append(
            Candidate(
                rep,
                members,
                round(score, 1),
                round(fresh, 1),
                round(kw, 1),
                round(buzz, 1),
                matched,
            )
        )
    result.candidates.sort(key=lambda c: (-c.score, -c.rep.when.timestamp()))
    _mark_candidates(result.candidates, cfg.min_score, cfg.max_candidates, cfg.per_source_max)
    return result


def _mark_candidates(cands: list[Candidate], min_score: float, limit: int, per_source: int) -> None:
    """점수 순으로 훑으며 후보 표시. 승인한 것은 항상 후보, 거절한 것은 후보에서 뺀다."""
    taken: dict[str, int] = {}
    count = 0
    for c in cands:
        if c.decision == APPROVED:
            c.is_candidate = True
            continue
        if c.decision == REJECTED or c.score < min_score or count >= limit:
            continue
        sid = c.rep.source_id
        if per_source and taken.get(sid, 0) >= per_source:
            continue
        taken[sid] = taken.get(sid, 0) + 1
        count += 1
        c.is_candidate = True
