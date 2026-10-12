"""v1 설정: 기존 Settings 에 '기사 보관 기간(retention_days)'만 더한다.

같은 config.yaml 을 쓰므로 기존 앱의 설정이 그대로 이어진다
(기존 앱은 모르는 키를 무시하므로 서로 방해하지 않는다).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import yaml

from newsclip import config as base
from newsclip import paths

DEFAULT_RETENTION_DAYS = 30


@dataclass
class CollectSettings(base.CollectSettings):
    retention_days: int = (
        DEFAULT_RETENTION_DAYS  # 수집·승인/거절·발송 기사를 이 일수 뒤에 모두 삭제
    )


@dataclass
class Settings(base.Settings):
    collect: CollectSettings = field(default_factory=CollectSettings)


def _positive_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 1 else default


def from_dict(data: dict[str, Any] | None) -> Settings:
    data = data if isinstance(data, dict) else {}
    parsed = base.from_dict(data)
    raw_collect = data.get("collect") if isinstance(data.get("collect"), dict) else {}
    collect = CollectSettings(
        **asdict(parsed.collect),
        retention_days=_positive_int(raw_collect.get("retention_days"), DEFAULT_RETENTION_DAYS),
    )
    # 보관 기간이 수집 기간보다 짧으면, 삭제된 기사가 피드에 남아 있어 다시 수집되어 버린다
    collect.retention_days = max(collect.retention_days, collect.days)
    return Settings(
        collect=collect,
        filters=parsed.filters,
        review=parsed.review,
        email=parsed.email,
        sources=parsed.sources,
    )


def load() -> Settings:
    path = paths.config_path()
    if not path.exists():
        return from_dict({})
    return from_dict(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def save(settings: Settings) -> None:
    paths.config_path().write_text(
        yaml.safe_dump(asdict(settings), allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
