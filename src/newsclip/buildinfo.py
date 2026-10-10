"""화면에 표시할 버전·최종 개발 일자 (git 의 마지막 커밋 기준, git 이 없으면 버전만)."""

from __future__ import annotations

import json
import subprocess
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def version() -> str:
    try:
        return metadata.version("projnewsclipping")
    except metadata.PackageNotFoundError:
        return "dev"


def _bundled_commit() -> tuple[str, str] | None:
    """빌드 때 기록한 build_info.json (설치본에는 git 이 없다)."""
    path = Path(__file__).with_name("build_info.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    day, short = data.get("date", ""), data.get("commit", "")
    return (day, short) if day and short else None


def last_commit() -> tuple[str, str] | None:
    """(YYYY-MM-DD, 짧은 해시) 또는 None."""
    bundled = _bundled_commit()
    if bundled:
        return bundled
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs %h"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return (out[0], out[1]) if len(out) == 2 else None


def label() -> str:
    commit = last_commit()
    if commit is None:
        return f"v{version()}"
    day, short = commit
    return f"v{version()} · {day} ({short})"
