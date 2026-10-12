# ProjNewsClipping

뉴스 기사를 취합하고, 규칙 기반으로 후보를 고르고, 승인한 기사를 이메일 양식으로 만들어 기본 메일 클라이언트로 여는 Streamlit 앱입니다. **LLM 없이** 동작합니다.

## 실행 (v1 — Streamlit 없는 경량 웹 앱)

```bash
uv sync
uv run python v1/run.py            # http://localhost:8520  (포트 인자: python v1/run.py 8530)
```

기존 Streamlit 앱(`app.py`, `views/`)은 그대로 보존되어 있습니다: `uv run streamlit run app.py`.
v1 은 같은 `src/newsclip`(수집·점수·이메일 렌더링)을 재사용하고, 같은 설정·DB 파일을 이어서 씁니다.

## v1 에서 달라진 점

| | 내용 |
|---|---|
| 속도 | Streamlit(매 동작마다 전체 스크립트 재실행) 제거. 표준 라이브러리 HTTP 서버 + 가벼운 HTML/JS. 화면 응답 수 ms, 승인/거절은 새로고침 없이 즉시 반영 |
| 이메일 만들기 | 승인 기사를 초안으로 옮기고 **후보 리스트를 초기화**. 승인·거절 기사는 이후 수집에서 제외 (미검토 기사 초기화는 확인 창에서 선택) |
| 발송 처리 | 이메일 화면의 **✅ 발송 처리**를 사용자가 직접 눌러 상태를 바꾸고 초안을 비움. **↩ 초안 폐기**로 후보 리스트에 되돌리기 가능 |
| 기사 보관 기간 | 환경 설정 > 수집 > **기사 보관 기간(기본 30일)**. 지나면 수집·승인/거절·발송 기사를 모두 삭제 |
| 설치본 크기 | Streamlit·pandas 제외로 번들이 훨씬 작고 시작이 빠름 |

폴더: `v1/newsclip_v1/`(서버·화면·업무 로직), `v1/static/`(CSS/JS), `v1/guide.py`(사용법 원본), `v1/packaging/`(Windows 설치 파일).
사용법 화면은 `v1/guide.py` 를 실행해 그대로 그리므로 그 파일만 고치면 반영됩니다.

## 사용법 HTML (Python 없이 열기)

`src/web_html/guide.html` 을 브라우저로 열면 사용법 문서를 볼 수 있습니다. 이 파일은 `views/guide.py`(원본)에서 생성됩니다.

```bash
uv run python tools/build_guide.py            # guide.html 생성
uv run python tools/build_guide.py --watch    # guide.py 를 고칠 때마다 자동 재생성
git config core.hooksPath .githooks           # (1회) guide.py 를 커밋하면 guide.html 도 자동 갱신
```

원본과 다르면 `pytest`(`tests/test_guide_html.py`)가 실패합니다. guide.html 의 설정 수치는 기본값 기준입니다.

## Windows 설치 파일 빌드

Windows 용은 Windows 에서만 빌드할 수 있습니다. 방법은 두 가지입니다.

### A. 다른 Windows PC 에서 직접 빌드 (GitHub Actions 없이)

필요한 것: Windows 10/11 PC, 인터넷, (Git 또는 ZIP 다운로드). Python 은 미리 설치하지 않아도 됩니다.

1. 소스를 받습니다.
   - Git 이 있으면: `git clone https://github.com/hupers77/ProjNewsClipping.git`
   - 없으면: https://github.com/hupers77/ProjNewsClipping/archive/refs/heads/main.zip 을 받아 압축 해제
2. 폴더의 `v1\packaging\build_windows.bat` 을 **더블클릭**합니다.
   - uv(Python 관리자)와 Inno Setup 이 없으면 winget 으로 자동 설치합니다. (설치 중 승인 창이 뜨면 허용)
   - 이어서 앱 빌드 → 화면 점검 → 설치 파일 생성까지 자동 진행합니다. 처음에는 10~20분 걸릴 수 있습니다.
3. 끝나면 `dist\NewsClipping-Setup-<버전>.exe` 가 만들어지고 탐색기가 열립니다.
4. 그 파일을 사용자 PC 로 옮겨 실행하면 설치됩니다 (바탕화면 아이콘 자동 생성).

문제가 생기면: 창에 나온 마지막 오류 줄을 확인하세요. 앱 실행 오류는 `%LOCALAPPDATA%\ProjNewsClipping\app.log`, 화면 점검 결과는 `%TEMP%\newsclip-smoke.log` 에 남습니다. winget 이 없는 PC 는 [uv](https://docs.astral.sh/uv/)와 [Inno Setup 6](https://jrsoftware.org/isdl.php)을 직접 설치한 뒤 다시 실행합니다.

### B. GitHub Actions

`.github/workflows/build.yml` — `v*` 태그 푸시 또는 Actions 탭의 **build → Run workflow** 로 같은 설치 파일을 만들어 아티팩트/릴리스로 올립니다.

### 설치하는 사용자 입장

설치 파일을 실행하고 '다음'만 누르면 됩니다. 관리자 권한 없이 설치되며 바탕화면과 시작 메뉴에 아이콘이 생깁니다. 실행하면 앱 전용 창(Edge/Chrome `--app`)이 열리고 창을 닫으면 서버도 종료됩니다. 설정·기사 데이터는 `%LOCALAPPDATA%\ProjNewsClipping` 에 저장되어 재설치·삭제 후에도 남습니다.

> 코드 서명이 없는 설치 파일이라 처음 실행할 때 Windows SmartScreen 이 "알 수 없는 게시자" 경고를 띄울 수 있습니다. **추가 정보 → 실행** 으로 진행합니다. 백신이 PyInstaller 결과물을 오탐하면 예외로 등록하세요.

### 다른 OS 에서 번들 구성만 점검

```bash
uv sync --no-dev --group build
uv run python packaging/write_build_info.py
uv run pyinstaller v1/packaging/newsclipping.spec --noconfirm
./dist/NewsClipping/NewsClipping --smoke   # 번들 안에서 서버를 띄워 모든 화면 요청
```
