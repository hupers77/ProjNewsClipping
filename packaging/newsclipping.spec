# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 스펙 (onedir). Windows 용은 Windows 에서 빌드해야 한다 (크로스 빌드 불가).

    uv sync --group build
    uv run python packaging/write_build_info.py
    uv run pyinstaller packaging/newsclipping.spec --noconfirm

산출물: dist/NewsClipping/NewsClipping.exe  (Windows 는 콘솔 없는 창 앱)
Streamlit 은 화면 스크립트(app.py, views/*.py)를 실행 시점에 읽으므로, 그 스크립트가
import 하는 모듈은 분석 단계에서 보이지 않는다 → hiddenimports/collect_all 로 명시한다.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent  # noqa: F821  (SPECPATH 는 PyInstaller 가 주입)

# .streamlit/config.toml 은 번들하지 않는다 (server.port 가 개발 모드 판정과 충돌). 설정은 launcher 가 지정.
datas = [
    (str(ROOT / "app.py"), "."),
    (str(ROOT / "views"), "views"),
    (str(ROOT / "src" / "web_html"), "web_html"),
]
build_info = ROOT / "src" / "newsclip" / "build_info.json"
if build_info.exists():
    datas.append((str(build_info), "newsclip"))
binaries = []
hiddenimports = collect_submodules("newsclip")

for package in (
    "streamlit",  # 정적 파일(프런트엔드) 포함
    "trafilatura", "justext", "courlan", "htmldate", "tld",  # 본문 추출의 설정·데이터
    "feedparser", "selectolax", "pandas", "altair",
):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += ["yaml", "httpx", "platformdirs", "sqlite3", "tomllib"]
for dist in ("streamlit", "projnewsclipping", "trafilatura", "feedparser", "httpx", "platformdirs"):
    try:
        datas += copy_metadata(dist)
    except Exception:
        pass

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

windows = sys.platform == "win32"
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NewsClipping",
    console=not windows,  # Windows: 콘솔 창 없이 실행. 다른 OS 는 점검 편의를 위해 콘솔
    icon=str(ROOT / "packaging" / "app.ico") if windows else None,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name="NewsClipping",
)
