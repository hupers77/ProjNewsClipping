# -*- mode: python ; coding: utf-8 -*-
"""v1 PyInstaller 스펙 (onedir). Windows 용은 Windows 에서 빌드해야 한다 (크로스 빌드 불가).

    uv sync --no-dev --group build
    uv run python packaging/write_build_info.py
    uv run pyinstaller v1/packaging/newsclipping.spec --noconfirm

산출물: dist/NewsClipping/NewsClipping.exe  (Windows 는 콘솔 없는 창 앱)
Streamlit·pandas 가 없어 번들이 작고 시작이 빠르다.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent.parent  # noqa: F821  (SPECPATH = v1/packaging)
V1 = ROOT / "v1"

datas = [
    (str(V1 / "static"), "static"),
    (str(V1 / "guide.py"), "."),
    (str(ROOT / "tools" / "build_guide.py"), "tools"),  # 사용법 화면이 guide.py 를 읽는 데 쓴다
]
build_info = ROOT / "src" / "newsclip" / "build_info.json"
if build_info.exists():
    datas.append((str(build_info), "newsclip"))
binaries = []
hiddenimports = collect_submodules("newsclip") + collect_submodules("newsclip_v1")

for package in (
    "trafilatura", "justext", "courlan", "htmldate", "tld",  # 본문 추출의 설정·데이터
    "feedparser", "selectolax",
):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += ["yaml", "httpx", "platformdirs", "sqlite3", "tomllib"]
for dist in ("projnewsclipping", "trafilatura", "feedparser", "httpx", "platformdirs"):
    try:
        datas += copy_metadata(dist)
    except Exception:
        pass

a = Analysis(
    [str(V1 / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src"), str(V1)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "ruff", "streamlit", "pandas", "numpy", "altair", "pyarrow"],
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
