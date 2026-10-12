"""review.cluster: 역색인 구현이 기존 전수 비교 구현과 같은 결과를 내는지, 그리고 충분히 빠른지."""

from __future__ import annotations

import random
import time
from datetime import UTC, datetime, timedelta

from newsclip.review import SUMMARY_CHARS, cluster
from newsclip.store import Article
from newsclip.text import jaccard, trigrams

WORDS = "AI 스마트팩토리 제조 공장 자동화 로봇 반도체 클라우드 보안 데이터 플랫폼 생성형 모델 투자 협력 발표 공개 개발 확대".split()


def reference_cluster(articles, threshold):
    """이전 구현(모든 쌍 비교) — 결과 비교용 기준."""
    feats = {
        a.id: (trigrams(a.title), trigrams(f"{a.title} {a.summary[:SUMMARY_CHARS]}"))
        for a in articles
    }
    groups = []
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


def make_articles(n: int, seed: int = 1) -> list[Article]:
    rnd = random.Random(seed)
    now = datetime(2026, 10, 13, tzinfo=UTC)
    out = []
    for i in range(n):
        title = " ".join(rnd.choices(WORDS, k=rnd.randint(2, 6))) + f" {rnd.randint(0, 40)}"
        summary = " ".join(rnd.choices(WORDS, k=rnd.randint(0, 12)))
        out.append(
            Article(
                id=i + 1,
                url=f"https://e.com/{i}",
                title=title,
                summary=summary,
                content="",
                source_id=f"s{i % 7}",
                source_name="x",
                category="it",
                lang="ko",
                published_at=now - timedelta(minutes=rnd.randint(0, 5000)),
                collected_at=now,
                decision="",
            )
        )
    return out


def ids(groups):
    return [[a.id for a in g] for g in groups]


def test_fast_cluster_matches_reference_on_many_inputs():
    for seed in range(8):
        arts = make_articles(120, seed)
        for threshold in (0.25, 0.5, 0.8):
            assert ids(cluster(arts, threshold)) == ids(reference_cluster(arts, threshold)), (
                seed,
                threshold,
            )


def test_fast_cluster_handles_edge_cases():
    assert cluster([], 0.5) == []
    arts = make_articles(3)
    arts[0].title, arts[0].summary = "", ""  # 조각이 없는 기사
    assert ids(cluster(arts, 0.5)) == ids(reference_cluster(arts, 0.5))


def test_fast_cluster_is_fast_for_hundreds_of_articles():
    arts = make_articles(800, 3)
    t0 = time.perf_counter()
    cluster(arts, 0.5)
    assert time.perf_counter() - t0 < 1.5  # 이전 구현은 같은 규모에서 수 초
