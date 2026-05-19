# Spark 서버 배포 노트

이 문서는 Meeting Summarizer 저장소를 그대로 Spark GPU 서버에서 운영하기 위한 현재 기준 메모입니다. 저장소를 나누거나 별도 서비스로 분리하지 않습니다.

## 검증된 운영 상태

- 대상 서버: Spark, `linux/arm64/v8`
- GPU: NVIDIA GB10
- CUDA: host와 CUDA container 안에서 visible
- 운영 배포: Docker Compose 검증 완료
- 백엔드: Dockerized FastAPI
- 프론트엔드: nginx production container에서 정적 서빙
- 백엔드 health check:

```bash
curl http://localhost:8000/api/health
# {"status":"ok"}
```

- 프론트엔드 접속:

```text
http://192.168.3.41:5173
```

현재 안정 운영 모드는 OpenAI STT baseline입니다.

```env
STT_PROVIDER=openai
SUMMARIZATION_PROVIDER=openai
```

## 배포 모드

안정 운영 배포는 기존 compose 파일만 사용합니다. 이 경로는 OpenAI STT baseline이며 rollback 기준입니다.

```bash
docker compose up -d
```

local GPU Whisper backend는 별도 overlay로만 실행합니다. 이 overlay는 backend image만 NGC PyTorch runtime으로 바꾸고 `STT_PROVIDER=local_gpu_whisper`를 설정합니다. 프론트엔드, 네트워크, 포트, volume, `.env` 로딩 방식은 기존 compose 설정을 그대로 따릅니다.

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.local-gpu.yml \
  up -d --build
```

local GPU variant의 현재 전제:

- 단일 FastAPI process/worker
- 프로세스 안의 resident shared Whisper model
- `LOCAL_GPU_MAX_CONCURRENCY` 기반 GPU inference semaphore
- plain STT path 우선
- diarized mode와 OpenAI provider는 변경하지 않음

rollback은 overlay 없이 안정 compose를 다시 적용하면 됩니다.

```bash
docker compose down
docker compose up -d
```

## 현재 실행 구조

- 백엔드: FastAPI 앱 `backend.main:app`
- 프론트엔드: React + TypeScript + Vite build, nginx production serving
- STT baseline: OpenAI STT, `transcribe.py`
- 요약 baseline: OpenAI Responses API, `summarization/`
- 작업 상태 저장: `backend/storage.py`의 인메모리 저장소
- 업로드 파일 저장: OS 기본 임시 디렉터리 하위 `meeting_summarizer_api`
- 오디오 청크 저장: OS 기본 임시 디렉터리 하위 `meeting_summarizer_chunks_*`

## 환경 변수 기준

`.env.example`을 복사해서 `.env`를 만들고 서버 값만 채웁니다.

```bash
cp .env.example .env
```

운영 baseline에 필요한 주요 값:

- `STT_PROVIDER=openai`
- `SUMMARIZATION_PROVIDER=openai`
- `OPENAI_API_KEY`
- `OPENAI_TRANSCRIPTION_MODEL`
- `OPENAI_STRUCTURE_MODEL`
- `OPENAI_SUMMARY_MODEL`
- `CORS_ORIGINS`

OpenAI STT와 요약 경로가 현재 production default입니다. GPU STT는 아직 운영 flow에 연결하지 않습니다.

## STT Provider 상태

검증된 사실:

- STT provider seam은 존재합니다.
- `OpenAITranscribeProvider`는 현재 production baseline입니다.
- `LocalWhisperProvider` CPU 경로는 기능적으로 동작합니다.
- CPU local Whisper는 production 회의 전사 품질 기준에는 부족했습니다.

CPU local Whisper에서 관찰한 문제:

- 한국어 비즈니스 용어 hallucination 또는 garbling
- entity fidelity 부족
- downstream semantic extraction 품질 저하 가능성

운영 지침:

- production default는 계속 `STT_PROVIDER=openai`입니다.
- transcription mode default는 계속 `plain`입니다.
- `STT_PROVIDER=local_whisper`는 실험용으로 유지합니다.
- `STT_PROVIDER=local_gpu_whisper`는 `docker-compose.local-gpu.yml` overlay에서만 켭니다.
- diarized mode는 화자별 검토가 필요한 경우를 위한 고급/실험 옵션으로 유지합니다.
- local Whisper GPU 통합은 먼저 plain path에서 평가하고, production integration 여부는 별도 판단합니다.

## GPU STT 평가 상태

검증된 사실:

- Docker GPU passthrough는 동작합니다.
- CUDA container 안에서 `nvidia-smi`가 동작합니다.
- Spark 서버는 ARM64이므로 generic Docker Hub PyTorch/CTranslate2 이미지 중 amd64 중심 이미지는 실패할 수 있습니다.
- ARM64에서 `pip install ctranslate2` 경로는 CPU-only로 동작했습니다.
- 확인된 증상:

```python
ctranslate2.get_cuda_device_count() == 0
```

- `ctranslate2 4.7.1`, `ctranslate2 4.5.0` 모두 같은 문제가 있었습니다.

현재 판단:

- CTranslate2/faster-whisper CUDA 경로는 ARM64 CUDA packaging/build 호환성 확인 전까지 blocked 상태입니다.
- faster-whisper 경로를 버리지는 않습니다.
- 다만 무작위 CTranslate2 wheel pinning은 중단하고, 필요하면 ARM64 CUDA build/runtime 계획을 세운 뒤 진행합니다.

현재 breakthrough:

- NVIDIA NGC PyTorch container는 Spark/GB10에서 동작했습니다.
- 검증 이미지:

```text
nvcr.io/nvidia/pytorch:25.11-py3
```

- container 내부에서 확인된 값:

```text
torch.cuda.is_available() == True
torch.cuda.device_count() == 1
GPU: NVIDIA GB10
```

- PyTorch Transformers Whisper `openai/whisper-large-v3`가 GPU에 로드되었습니다.
- 69초 오디오가 long-form timestamp 설정 후 약 15.9초에 전사되었습니다.
- 이 결과는 NGC PyTorch stack을 통한 local GPU STT 품질 평가가 가능함을 확인합니다.

## 오디오 런타임 주의점

- 30초를 넘는 Transformers Whisper long-form audio는 `return_timestamps=True`가 필요합니다.
- `tools/whisper_eval/evaluate_transformers_whisper.py`는 이 값을 기본으로 켭니다.
- `m4a` decoding에는 container 안의 `ffmpeg`가 필요할 수 있습니다.
- `m4a` parsing이 실패하면 `wav`로 변환해 평가합니다.

```bash
ffmpeg -i input.m4a input.wav
```

## 서버 디스크와 정리 지침

현재 주요 local addition 규모:

- HuggingFace cache: 약 2.9GB
- repository: 약 893MB
- `.venv`: 약 749MB
- meeting backend image: 약 2.33GB
- `whisper-eval-gpu` image: 약 3.87GB
- NGC PyTorch image: 약 19.5GB

이미 제거한 dangling image:

```text
98a6327b25ee
```

실행 금지:

```bash
docker system prune -a
docker volume prune
```

이 서버에는 다른 서비스, 이미지, 볼륨이 있을 수 있으므로 전체 prune은 하지 않습니다.

상대적으로 안전한 정리:

```bash
docker image prune -f
docker builder prune -f
```

HuggingFace cache는 `large-v3` 재평가에 유용하므로 당분간 유지합니다.

## 운영상 주의점

- 작업 상태는 인메모리입니다. 백엔드 프로세스를 재시작하면 진행 중이거나 완료된 job 상태가 사라집니다.
- 업로드 원본 파일은 처리 후 삭제됩니다.
- 현재 production STT 경로는 ffmpeg 기반 오디오 확인과 청크 분할 경로를 사용합니다.
- GPU/CUDA는 아직 production OpenAI STT 경로에서는 사용하지 않습니다.
- Kubernetes, Spark distributed job, 별도 STT microservice는 현재 배포 범위가 아닙니다.

## 검증 순서

백엔드와 공통 로직:

```bash
python3 -m py_compile main.py app.py transcribe.py summarize.py backend/main.py backend/api/routes.py backend/services/pipeline.py backend/storage.py backend/schemas.py
python3 -m unittest discover -s tests -v
```

프론트엔드:

```bash
cd frontend
npm run build
```

운영 health check:

```bash
curl http://localhost:8000/api/health
```
