# Meeting Summarizer

## 프로젝트 개요

회의 녹음 파일을 업로드하면 STT 변환 후 AI로 회의록을 자동 생성하는 내부 툴입니다. BigxData 사내 사용을 목적으로 합니다.

## 현재 구조

기존 Streamlit 버전과 신규 FastAPI + React 버전이 병렬로 존재합니다.

### 공유 백엔드 (기존)

- `transcribe.py`: GPT-4o-transcribe로 STT를 수행합니다.
- `summarize.py`: 회의록 생성 파이프라인을 담당합니다.
- `utils.py`: 오디오 청크 분할과 파일 처리 유틸리티를 제공합니다.
- `main.py`: CLI 진입점입니다.

### Streamlit 버전 (기존)

- `app.py`: Streamlit UI입니다.

### FastAPI + React 버전 (신규, 진행 중)

- `backend/main.py`: FastAPI 앱을 생성하고 CORS와 라우터를 설정합니다.
- `backend/api/routes.py`: API 엔드포인트를 정의합니다.
- `backend/services/pipeline.py`: 기존 `transcribe.py`, `summarize.py` 함수를 호출합니다.
- `backend/schemas.py`: 요청과 응답에 사용하는 Pydantic 모델을 정의합니다.
- `backend/storage.py`: DB 없이 인메모리 작업 상태와 임시 파일을 저장합니다.
- `frontend/`: React + TypeScript + Vite 기반 프론트엔드입니다.

## 요약 파이프라인 (`summarize.py`)

0단계: `preprocess_transcript()` - Python 전처리

- 추임새 단독 토큰만 제거합니다.
- 동일 화자 연속 발언을 병합합니다.
- 회의 날짜를 추출합니다.

1단계: `extract_structure()` - GPT-4o-mini, Structured Output

- JSON 필드: `summary_facts`, `decisions`, `action_items`, `speaker_highlights`, `warnings`
- 사실 기반 구조화 정보를 추출합니다.

2단계: `generate_minutes()` - GPT-5.4

- 입력: 전처리된 텍스트 + `extract_structure()` JSON
- 자연스러운 한국어 회의록을 생성합니다.

3단계: `render_output()` - Python

- 구조화 결과와 회의록 본문을 조합합니다.
- 최종 Markdown을 렌더링합니다.

## 기술 스택

- STT: GPT-4o-transcribe
- 구조화 추출: GPT-4o-mini (Structured Output)
- 회의록 생성: GPT-5.4
- Streamlit UI: `app.py`
- FastAPI 백엔드: `backend/`
- React 프론트: `frontend/` (React + TypeScript + Vite)

## 실행 방법

프로젝트 루트에서 Python 가상환경을 활성화합니다.

```bash
source .venv/bin/activate
```

FastAPI 백엔드는 프로젝트 루트에서 실행합니다.

```bash
uvicorn backend.main:app --reload
```

## 코딩 규칙

- API 키는 `.env`에서만 관리합니다.
- 모든 함수에 docstring을 작성합니다.
- 에러는 try/except로 처리하고 명확한 메시지를 제공합니다.
- 각 단계 소요 시간을 로깅합니다.
- 추임새는 단독 토큰일 때만 제거하고, 맥락이 있으면 유지합니다.
- `summarize.py` 또는 요약 엔진 관련 작업 전에는 `docs/SUMMARIZATION_ENGINE.md`를 먼저 읽습니다.
- 코드 주석과 docstring은 모두 한글로 작성합니다.
- Streamlit CSS에서는 `::after`, `::before`를 사용하지 않습니다.
- 주석 정리는 삭제가 아니라 더 명확하게 다듬는 것을 의미합니다.
- 파일 처리 후 임시 파일은 반드시 정리합니다.

## 검증 순서

1. `python3 -m py_compile`로 문법을 확인합니다.
2. `python3 -m unittest discover -s tests -v`로 기능을 확인합니다.
3. UI 변경 시 실제 브라우저에서 화면을 확인합니다.

## 현재 진행 상황

- Streamlit 버전: 기능 구현 완료, UI 개선 중입니다.
- FastAPI + React: 구조 생성 완료, 백엔드 실행 확인 단계입니다.
- 다음 단계: `backend/` 실행 확인 후 React UI를 구현합니다.
