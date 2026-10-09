# ProjNewsClipping

뉴스 기사를 취합하고, 규칙 기반으로 후보를 고르고, 승인한 기사를 이메일 양식으로 만들어 기본 메일 클라이언트로 여는 Streamlit 앱입니다. **LLM 없이** 동작합니다.

## 실행

```bash
uv sync
uv run streamlit run app.py   # http://localhost:8520 (포트는 .streamlit/config.toml)
```

## 화면

1. **환경 설정** — 수집 기간, 사이트(RSS / Google 뉴스 검색), 본문 추출 글자 수, 제외 키워드, 포함 키워드(가산점), 후보 선정 기준(최대 수·최소 점수·매체당 상한·유사도·가중치), 메일 기본값. 설정은 로컬 `config.yaml` 에 저장됩니다.
2. **후보 리스트** — `지금 수집` → 기사 묶음(같은 사건) 목록, 본문/관련 기사/점수 확인, 승인·거절. `이메일 만들기` 는 승인한 기사만 사용합니다.
3. **이메일 보기·편집** — 제목·받는 사람·도입/맺음·항목별 제목/요약/링크를 고치고 저장. `메일 창 열기` 는 `.eml` 을 OS 기본 프로그램으로 열어 기본 메일 클라이언트의 새 메일 창을 띄웁니다. `mailto` 버튼은 텍스트 본문만 담습니다(길이 제한, 서식 없음). `.eml`/`.html` 다운로드도 가능합니다.

## 후보 선정 방식 (LLM 없음)

제외 키워드 → 제목 3-gram 유사도로 같은 사건 묶기 → 점수(신선도·키워드 가산점·화제성 가중 평균) → 최소 점수/최대 개수/매체당 상한으로 컷오프. 설정을 바꾸면 다시 수집하지 않고 저장된 기사로 즉시 재계산합니다. 정확도 향상(요약·분류에 LLM 사용)은 후속 기능입니다.

## 저장 위치

기본: OS 사용자 데이터 폴더(`platformdirs`). `NEWSCLIP_HOME` 환경변수로 바꿀 수 있습니다. 설정 화면 상단에 실제 경로가 표시됩니다.

## 메모

- 메일에는 짧은 규칙 기반 요약과 출처 링크만 담으며, 기사 본문 전체를 복사하지 않습니다.
- Google 뉴스 링크는 리다이렉트라 본문 추출을 건너뜁니다(RSS 요약 사용).
- macOS 메일 앱은 `.eml` 을 새 작성 창이 아니라 열람 창으로 여는 경우가 있습니다. 그땐 `mailto` 또는 `.html` 복사를 쓰세요.

## 개발

```bash
uv run ruff check . && uv run ruff format --check . ; uv run pytest
```

## 사용법 HTML (Python 없이 열기)

`src/web_html/guide.html` 을 브라우저로 열면 사용법 문서를 볼 수 있습니다. 이 파일은 `views/guide.py`(원본)에서 생성됩니다.

```bash
uv run python tools/build_guide.py            # guide.html 생성
uv run python tools/build_guide.py --watch    # guide.py 를 고칠 때마다 자동 재생성
git config core.hooksPath .githooks           # (1회) guide.py 를 커밋하면 guide.html 도 자동 갱신
```

원본과 다르면 `pytest`(`tests/test_guide_html.py`)가 실패합니다. guide.html 의 설정 수치는 기본값 기준입니다.
