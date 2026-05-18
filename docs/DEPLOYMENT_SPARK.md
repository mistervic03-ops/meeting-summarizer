# Spark 서버 배포 노트

이 문서는 기존 meeting-summarizer 저장소를 그대로 Spark GPU 서버에서 실행하기 위한 최소 운영 메모입니다. 저장소를 나누거나 별도 서비스로 분리하지 않습니다.

## 현재 실행 구조

- 백엔드: FastAPI 앱 `backend.main:app`
- 프론트엔드: React + TypeScript + Vite, API 기본 경로는 `/api`
- STT baseline: OpenAI STT, `transcribe.py`
- 요약 baseline: OpenAI Responses API, `summarization/`
- 작업 상태 저장: `backend/storage.py`의 인메모리 저장소
- 업로드 파일 저장: OS 기본 임시 디렉터리 하위 `meeting_summarizer_api`
- 오디오 청크 저장: OS 기본 임시 디렉터리 하위 `meeting_summarizer_chunks_*`

## 서버 필수 패키지

Python 패키지 설치 전에 서버에 `ffmpeg`와 `ffprobe`가 있어야 합니다. 현재 STT 준비 단계는 plain 모드에서도 시간 기준 청크 설정을 확인하므로, 일반 업로드 처리에도 pydub/ffmpeg 경로가 필요합니다.

```bash
sudo apt update
sudo apt install -y ffmpeg
```

현재 Spark 서버의 Python 3.12.3은 프로젝트 코드와 호환되는 방향입니다. 의존성은 `requirements.txt` 기준으로 설치합니다.

## 환경 변수

`.env.example`을 복사해서 `.env`를 만들고 서버 값만 채웁니다.

```bash
cp .env.example .env
```

현재 baseline 실행에 필요한 값:

- `STT_PROVIDER=openai`
- `SUMMARIZATION_PROVIDER=openai`
- `OPENAI_API_KEY`
- `OPENAI_TRANSCRIPTION_MODEL`
- `OPENAI_SUMMARY_MODEL`

주요 선택 값:

- `OPENAI_DIARIZED_TRANSCRIPTION_MODEL`
- `OPENAI_TRANSCRIPTION_LANGUAGE`
- `TRANSCRIPTION_MODE`
- `ENABLE_DIARIZED_TRANSCRIPTION`
- `PLAIN_TRANSCRIPTION_CONCURRENCY`
- `PLAIN_CHUNK_DURATION_SECONDS`
- `PLAIN_CHUNK_OVERLAP_SECONDS`
- `DIARIZED_CHUNK_DURATION_SECONDS`
- `DIARIZED_CHUNK_OVERLAP_SECONDS`
- `ENABLE_STT_VOCABULARY_HINTS`
- `STT_VOCABULARY_PATH`
- `OPENAI_STRUCTURE_MODEL`
- `CORS_ORIGINS`
- `VITE_API_BASE_URL` 또는 `frontend/.env`의 동일 값

## Provider 설정 방향

Provider는 같은 저장소 안에서 환경 변수로 선택하는 방향을 유지합니다.

```bash
STT_PROVIDER=openai
SUMMARIZATION_PROVIDER=openai
```

향후 추가 예정 값:

```bash
STT_PROVIDER=local_whisper
SUMMARIZATION_PROVIDER=claude
```

아직 `local_whisper`와 `claude` 실행 경로는 구현되어 있지 않습니다. 지금은 OpenAI 경로를 baseline/debug 경로로 유지하고, 나중에 provider 분기 모듈을 추가할 때 기존 `transcribe.py`와 `summarization/` public 함수 호출부를 깨지 않는 방식으로 확장합니다.

## 백엔드 실행

프로젝트 루트에서 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

상태 확인:

```bash
curl -s http://127.0.0.1:8000/api/health
```

tmux 예시:

```bash
tmux new -s meeting-backend
source .venv/bin/activate
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## 프론트엔드 실행

개발 서버를 Spark 서버 외부 브라우저에서 보려면 `0.0.0.0`으로 bind합니다.

```bash
cd frontend
npm install
npm run dev:server -- --port 5173
```

Vite dev server를 쓰는 경우 `/api` 요청은 `frontend/vite.config.ts`가 `http://localhost:8000`으로 proxy합니다. 이 방식이면 브라우저는 `http://서버IP:5173`만 열면 됩니다.

빌드 검증:

```bash
cd frontend
npm run build
```

## CORS와 API 경로

기본 프론트엔드 API 경로는 `/api`입니다. Vite proxy 또는 같은 origin 정적 서빙에서는 이 기본값이 가장 단순합니다.

프론트엔드가 백엔드를 직접 호출해야 한다면:

```bash
VITE_API_BASE_URL=http://192.168.3.41:8000/api
CORS_ORIGINS=http://192.168.3.41:5173,http://localhost:5173
```

`VITE_API_BASE_URL`은 Vite가 실행되는 `frontend` 프로세스 환경 변수이거나 `frontend/.env`에 있어야 합니다. 루트 `.env`는 백엔드에서 읽습니다.

## 현재 운영상 주의점

- 작업 상태는 인메모리입니다. 백엔드 프로세스를 재시작하면 진행 중이거나 완료된 job 상태가 사라집니다.
- 업로드 원본 파일은 처리 후 삭제됩니다.
- 현재 STT 준비 단계는 plain/diarized 모두 ffmpeg 기반 오디오 확인과 청크 분할 경로를 사용합니다.
- GPU/CUDA는 아직 baseline OpenAI STT 경로에서는 사용하지 않습니다. Spark GPU는 이후 `local_whisper` provider 추가 시 사용합니다.
- Kubernetes, Spark distributed job, 별도 STT microservice는 현재 배포 범위가 아닙니다.

## 검증 순서

프로젝트 루트:

```bash
python3 -m py_compile main.py app.py transcribe.py summarize.py backend/main.py backend/api/routes.py backend/services/pipeline.py backend/storage.py backend/schemas.py
python3 -m unittest discover -s tests -v
```

프론트엔드:

```bash
cd frontend
npm run build
```
