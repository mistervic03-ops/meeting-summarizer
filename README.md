# Meeting Summarizer

BigxData 내부 회의록 도구입니다. 회의 녹음 파일을 업로드하면 STT 변환, transcript 검토, 회의 유형별 요약/추출, 렌더링/내보내기를 수행합니다.

CLI 진입점과 FastAPI + React 운영 앱이 같은 저장소 안에 함께 존재합니다. Spark/GB10 운영 배포는 local GPU Whisper STT와 OpenAI 기반 요약 pipeline을 기준으로 합니다.

## 기술 스택

- Backend: FastAPI
- Frontend: React + TypeScript + Vite
- STT baseline: local GPU Whisper on Spark/GB10, OpenAI STT fallback
- Local GPU STT runtime: NVIDIA NGC PyTorch + Transformers Whisper
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
