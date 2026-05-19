# Meeting Summarizer

## 프로젝트 개요

회의 녹음 파일을 업로드하면 STT 변환, transcript 검토, 회의 유형별 요약/추출, 렌더링/내보내기를 수행하는 BigxData 내부 회의록 도구입니다.

## 현재 구조

CLI 진입점과 FastAPI + React 운영 앱이 같은 저장소 안에 함께 존재합니다. 저장소를 나누지 않습니다.

### 공유 파이프라인

- `transcribe.py`: STT provider 선택, plain/diarized 전사, 오디오 청크 처리, OpenAI STT baseline 호출을 담당합니다.
- `backend/services/stt/`: STT provider abstraction을 담당합니다.
- `summarization/`: 회의록 생성 엔진 모듈입니다.
- `summarize.py`: 기존 import 호환성을 유지하는 facade입니다.
- `utils.py`: 오디오 청크 분할과 파일 처리 유틸리티를 제공합니다.
- `main.py`: CLI 진입점입니다.

### FastAPI + React 운영 앱

- `backend/main.py`: FastAPI 앱 생성, CORS, 라우터 등록을 담당합니다.
- `backend/api/routes.py`: API 엔드포인트를 정의합니다.
- `backend/services/pipeline.py`: STT, transcript review, summarization pipeline을 연결합니다.
- `backend/schemas.py`: 요청과 응답에 사용하는 Pydantic 모델을 정의합니다.
- `backend/storage.py`: DB 없이 인메모리 작업 상태와 임시 파일을 저장합니다.
- `frontend/`: React + TypeScript + Vite 프론트엔드입니다.

## STT 상태

현재 안정 운영 baseline은 OpenAI STT입니다.

```env
STT_PROVIDER=openai
```

지원되는 STT provider:

- `openai`: 안정 운영 baseline입니다.
- `local_whisper`: faster-whisper CPU 실험 경로입니다. 기능적으로 동작하지만 production 품질 기준에는 부족했습니다.
- `local_gpu_whisper`: Spark/GB10 local GPU Whisper 실험 운영 overlay용 provider입니다. NGC PyTorch runtime, resident model, 전역 GPU semaphore를 전제로 합니다.

plain mode가 기본/주요 경로입니다. diarized mode는 남겨두되 고급/실험 옵션으로 취급합니다.

## 요약 파이프라인

요약 엔진은 `summarization/` 모듈들로 분리되어 있고, `summarize.py`는 기존 호출자를 위한 compatibility facade입니다.

현재 주요 흐름:

1. `preprocess_transcript()`
2. `normalize_transcript()`
3. `analyze_transcript_profile()`
4. `choose_processing_strategy()`
5. `extract_structure()` 또는 `extract_structure_by_chunks()`
6. `apply_extraction_policy()`
7. `validate_structure()`
8. `generate_minutes()`
9. `render_output()`
10. `build_summary_result()`

구조화 추출은 `summary_facts`, `decisions`, `action_items`, `speaker_highlights`, `warnings`를 반환합니다. 내부적으로 action item과 decision은 `source_quote`, `source_utterance_ids` 기반 grounding을 사용하지만 public result에는 노출하지 않습니다.

## 기술 스택

- Backend: FastAPI
- Frontend: React + TypeScript + Vite
- STT baseline: OpenAI `gpt-4o-transcribe`
- Local GPU STT 실험 runtime: NVIDIA NGC PyTorch + Transformers Whisper
- 구조화 추출: OpenAI Structured Output, 기본 `gpt-4o-mini`
- 회의록 생성: OpenAI Responses API, 기본 `gpt-5.4`
- 배포: Docker Compose

## 실행 방법

프로젝트 루트에서 Python 가상환경을 활성화합니다.

```bash
source .venv/bin/activate
```

FastAPI 백엔드는 프로젝트 루트에서 실행합니다.

```bash
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

프론트엔드는 `frontend/`에서 실행합니다.

```bash
cd frontend
npm run dev:server -- --host 0.0.0.0 --port 5173
```

Spark Docker Compose 배포 기준은 `docs/DEPLOYMENT_SPARK.md`를 따릅니다.

## 코딩 규칙

- API 키는 `.env`에서만 관리합니다.
- 모든 함수에 docstring을 작성합니다.
- 에러는 try/except로 처리하고 명확한 메시지를 제공합니다.
- 각 단계 소요 시간을 로깅합니다.
- 추임새는 단독 토큰일 때만 제거하고, 맥락이 있으면 유지합니다.
- `summarize.py` 또는 요약 엔진 관련 작업 전에는 `docs/SUMMARIZATION_ENGINE.md`를 먼저 읽습니다.
- 코드 주석과 docstring은 모두 한글로 작성합니다.
- 주석 정리는 삭제가 아니라 더 명확하게 다듬는 것을 의미합니다.
- 파일 처리 후 임시 파일은 반드시 정리합니다.

## 검증 순서

1. `python3 -m py_compile`로 문법을 확인합니다.
2. `python3 -m unittest discover -s tests -v`로 기능을 확인합니다.
3. UI 변경 시 frontend build와 브라우저 확인을 수행합니다.
