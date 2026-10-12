"""설치본(NewsClipping.exe) 진입점. 실제 동작은 newsclip_v1.desktop 에 있다."""

import sys

from newsclip_v1.desktop import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
