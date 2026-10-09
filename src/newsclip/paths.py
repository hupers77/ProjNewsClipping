"""로컬 저장 위치. 환경변수 NEWSCLIP_HOME 으로 바꿀 수 있다."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir


def home() -> Path:
    env = os.environ.get("NEWSCLIP_HOME")
    path = (
        Path(env).expanduser() if env else Path(user_data_dir("ProjNewsClipping", appauthor=False))
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return home() / "config.yaml"


def db_path() -> Path:
    return home() / "newsclip.db"


def mail_dir() -> Path:
    path = home() / "mails"
    path.mkdir(parents=True, exist_ok=True)
    return path
