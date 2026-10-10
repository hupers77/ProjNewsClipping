"""빌드 시점의 버전·커밋 날짜를 번들에 넣을 JSON 으로 기록한다 (번들에는 git 이 없다)."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
out = ROOT / "src" / "newsclip" / "build_info.json"
try:
    day, short = subprocess.run(
        ["git", "log", "-1", "--format=%cs %h"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
except Exception:  # noqa: BLE001
    day, short = "", ""
out.write_text(json.dumps({"date": day, "commit": short}), encoding="utf-8")
print(f"wrote {out.relative_to(ROOT)}: {day} {short}")
if not day:
    print("WARNING: git info unavailable - the app will show the version without a date")
