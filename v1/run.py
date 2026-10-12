"""개발용 실행: python v1/run.py [포트]  (설치본은 v1/packaging/launcher.py 가 같은 서버를 띄운다)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "v1")]

from newsclip_v1.server import make_server  # noqa: E402

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8520
    server = make_server(port)
    print(f"http://localhost:{port}  (Ctrl+C 로 종료)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
