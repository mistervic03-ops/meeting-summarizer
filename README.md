# Meeting Summarizer

BigxData 내부 회의록 도구입니다. 회의 녹음 파일은 STT 변환과 transcript 검토를 거치고, 텍스트 transcript는 바로 회의 유형별 요약/추출, 렌더링/내보내기를 수행합니다.

CLI 진입점과 FastAPI + React 운영 앱이 같은 저장소 안에 함께 존재합니다. Spark/GB10 운영 배포는 local GPU Whisper STT와 OpenAI 기반 요약 pipeline을 기준으로 하며, 요약 provider는 환경 변수로 Claude도 선택할 수 있습니다.

## 기술 스택

- Backend: FastAPI
- Frontend: React + TypeScript + Vite
- STT baseline: local GPU Whisper on Spark/GB10, OpenAI STT fallback
- Local GPU STT runtime: NVIDIA NGC PyTorch + Transformers Whisper
- 구조화 추출: OpenAI Structured Output 기본 `gpt-4o-mini`, 또는 Claude JSON extraction
- 회의록 생성: OpenAI Responses API 기본 `gpt-5.4`, 또는 Claude messages API
- 저장소: SQLite meeting history plus transcript/summary text artifacts under `data/`
- 배포: Docker Compose

## 현재 흐름

1. 음성 업로드: `POST /api/transcriptions`가 plain STT를 실행하고 transcript 검토 화면으로 이동합니다.
2. Transcript 검토: 사용자가 plain text transcript를 확인/수정합니다. 구조화 transcript나 speaker field는 사용하지 않습니다.
3. 사전 요약: 오디오 업로드 흐름에서는 transcript 검토 중 배경 summary job을 시작하고, transcript/context/meeting type이 그대로면 즉시 결과를 표시합니다.
4. 회의록 생성: `POST /api/transcript-jobs`가 plain transcript를 요약 pipeline으로 보냅니다.
5. 결과/히스토리: 결과 화면과 7일 meeting history에서 transcript와 summary artifact를 확인하거나 삭제할 수 있습니다.

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

## Docker 배포 인증

Docker production은 앱 Gateway 로그인 페이지로 비밀번호 인증을 수행합니다. nginx는 정적 SPA 서빙과 `/api/` 프록시만 담당하고, backend가 `secrets/.htpasswd`를 읽어 `/api/*` 요청을 보호합니다. 현재 운영 계정은 개인별 계정이 아니라 공유 계정 `bigxdata` 1개입니다.

Spark 서버에는 `htpasswd` 명령을 제공하는 `apache2-utils`가 먼저 설치되어 있어야 합니다.

```bash
sudo apt install apache2-utils
```

```bash
mkdir -p secrets
htpasswd -B -c secrets/.htpasswd bigxdata
```

비밀번호를 재발급할 때는 기존 파일을 새로 만들지 않도록 `-c` 없이 실행합니다.

```bash
htpasswd -B secrets/.htpasswd bigxdata
```

Backend API는 host port로 직접 공개하지 않고 frontend nginx의 `/api/` 프록시를 통해 접근합니다. `secrets/.htpasswd`는 이미지에 포함하지 않고 배포 호스트에서 backend 컨테이너에 읽기 전용으로 mount합니다.

## 테스트 실행

테스트는 Docker production container 안에서 `docker exec`로 실행하지 말고 host Python virtualenv에서 실행합니다.

```bash
source .venv/bin/activate
python3 -m pytest tests/ -v
```

Production backend container에는 운영 `.env`와 overlay 환경이 주입됩니다. 예를 들어 `STT_PROVIDER=local_gpu_whisper`, `SUMMARIZATION_PROVIDER=claude` 같은 값 때문에 provider 기본값을 가정하는 일부 테스트(`test_transcribe.py`, `test_summarize_provider.py`, `test_summarize_minutes.py`)가 컨테이너 안에서는 실패할 수 있습니다. 이는 Gateway 인증이나 코드 회귀가 아니라 테스트 격리 가정과 실행 환경의 불일치입니다.
