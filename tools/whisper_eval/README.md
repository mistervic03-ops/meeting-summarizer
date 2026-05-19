# Whisper GPU Evaluation

이 디렉터리는 Meeting Summarizer production flow와 분리된 STT 품질 평가 도구입니다. 단일 오디오 파일의 전사 품질과 실행 시간을 확인하기 위한 harness이며, 앱의 API flow를 직접 실행하지 않습니다.

현재 앱에는 별도의 `local_gpu_whisper` provider와 `docker-compose.local-gpu.yml` overlay가 존재합니다. 이 디렉터리의 스크립트는 그 production-safe provider와 별개로 모델 품질과 runtime 특성을 빠르게 비교하는 용도입니다.

## 평가 목표

- OpenAI STT baseline과 local GPU Whisper transcript의 semantic fidelity를 비교합니다.
- production integration이 아니라 품질 판단을 위한 실험입니다.
- downstream summarization에 유용한 transcript인지 확인합니다.

주요 평가 기준:

- 한국어 비즈니스 용어 fidelity
- 날짜와 숫자 정확도
- action item fidelity
- hallucination rate
- downstream summarization 입력으로서의 유용성

## 현재 결론

검증된 production baseline:

- `STT_PROVIDER=openai`
- OpenAI STT는 현재 안정 운영 경로입니다.

CPU local Whisper:

- 기능적으로 동작합니다.
- production 회의 전사 품질에는 부족했습니다.
- 관찰된 문제는 한국어 비즈니스 용어 왜곡, entity fidelity 부족, downstream semantic extraction 품질 저하 가능성입니다.

faster-whisper/CTranslate2 GPU:

- 기존 harness는 유지합니다.
- Spark 서버가 `linux/arm64/v8`이므로 generic Docker Hub CUDA 이미지와 CTranslate2 wheel 조합이 안정적이지 않았습니다.
- `ctranslate2 4.7.1`, `ctranslate2 4.5.0`에서 모두 CUDA passthrough는 보이지만 `ctranslate2.get_cuda_device_count() == 0`이었습니다.
- 이 경로는 ARM64 CUDA packaging/build compatibility 계획을 세운 뒤 다시 조사합니다.
- 무작위 CTranslate2 wheel pinning은 중단합니다.

현재 검증된 GPU 평가 경로:

- NVIDIA NGC PyTorch container
- `nvcr.io/nvidia/pytorch:25.11-py3`
- Spark/GB10에서 `torch.cuda.is_available() == True`
- `torch.cuda.device_count() == 1`
- GPU 이름: `NVIDIA GB10`
- PyTorch Transformers Whisper `openai/whisper-large-v3` GPU inference 진입 성공
- PyTorch Transformers Whisper `openai/whisper-large-v3-turbo` GPU inference 진입 성공
- 69초 오디오가 long-form timestamp 설정 후 약 15.9초에 전사됨

## 파일 구성

- `evaluate_whisper.py`: faster-whisper/CTranslate2 평가 harness
- `Dockerfile.gpu`: faster-whisper/CTranslate2 평가 이미지
- `evaluate_transformers_whisper.py`: PyTorch Transformers Whisper 평가 harness
- `Dockerfile.transformers-gpu`: generic PyTorch Docker Hub 기반 실험 이미지
- `outputs/`: transcript 출력 디렉터리

현재 Spark/GB10에서는 NGC PyTorch container를 우선 사용합니다.

## NGC PyTorch 평가 환경

프로젝트 루트에서 NGC PyTorch container에 들어갑니다.

```bash
docker run --rm --gpus all -it --ipc=host \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -v "${PWD}:/workspace" \
  -w /workspace \
  nvcr.io/nvidia/pytorch:25.11-py3
```

container 안에서 Torch CUDA preflight를 확인합니다.

```bash
python -c "import torch; print(torch.version); print(torch.cuda.is_available()); print(torch.cuda.device_count()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no cuda')"
```

필요한 최소 dependency를 설치합니다.

```bash
apt-get update && apt-get install -y ffmpeg
pip install transformers accelerate sentencepiece
```

오디오를 전사합니다.

```bash
python tools/whisper_eval/evaluate_transformers_whisper.py test-audio.wav
```

기본값:

```text
model=openai/whisper-large-v3
device=cuda
torch_dtype=float16
language=ko
task=transcribe
return_timestamps=true
```

참고: 앱의 `local_gpu_whisper` provider 기본 모델은 production-safe GPU overlay 기준으로 `openai/whisper-large-v3-turbo`입니다. 평가 스크립트 기본값은 비교 실험을 위해 `openai/whisper-large-v3`로 유지합니다.

모델을 바꿔 비교합니다.

```bash
python tools/whisper_eval/evaluate_transformers_whisper.py test-audio.wav \
  --model openai/whisper-large-v3-turbo \
  --output-dir tools/whisper_eval/outputs
```

```bash
python tools/whisper_eval/evaluate_transformers_whisper.py test-audio.wav \
  --model distil-whisper/distil-large-v3 \
  --output-dir tools/whisper_eval/outputs
```

## Long-Form Audio

Transformers Whisper는 30초를 넘는 long-form audio에서 timestamp chunk 반환이 필요할 수 있습니다.

`evaluate_transformers_whisper.py`는 기본적으로 다음 설정을 사용합니다.

```text
--return-timestamps
```

필요할 때만 짧은 smoke test에서 끕니다.

```bash
python tools/whisper_eval/evaluate_transformers_whisper.py test-audio.wav --no-return-timestamps
```

## Audio Decode Notes

`m4a` decoding에는 container 안의 `ffmpeg`가 필요할 수 있습니다. `m4a` parsing이 실패하면 `wav`로 변환해서 평가합니다.

```bash
ffmpeg -i input.m4a input.wav
python tools/whisper_eval/evaluate_transformers_whisper.py input.wav
```

## Transformers Dockerfile

`Dockerfile.transformers-gpu`는 generic PyTorch Docker Hub 기반 실험 이미지입니다. Spark/GB10에서는 NGC image가 검증된 경로이므로 먼저 NGC container를 사용합니다.

빌드:

```bash
docker build -f tools/whisper_eval/Dockerfile.transformers-gpu -t transformers-whisper-gpu .
```

Torch CUDA preflight:

```bash
docker run --rm --gpus all --entrypoint python3 transformers-whisper-gpu \
  -c "import torch; print(torch.version); print(torch.cuda.is_available()); print(torch.cuda.device_count())"
```

실행:

```bash
docker run --rm --gpus all \
  -v "$PWD/test-audio.wav:/audio/test-audio.wav:ro" \
  -v "$PWD/tools/whisper_eval/outputs:/outputs" \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  transformers-whisper-gpu /audio/test-audio.wav --output-dir /outputs
```

## faster-whisper Harness

기존 faster-whisper harness는 남겨둡니다. 이 경로는 ARM64 CUDA packaging/build compatibility 조사가 끝난 뒤 다시 평가합니다.

로컬 실행:

```bash
python3 tools/whisper_eval/evaluate_whisper.py /path/to/meeting_audio.wav
```

Docker build:

```bash
docker build -f tools/whisper_eval/Dockerfile.gpu -t whisper-eval-gpu .
```

CTranslate2 preflight:

```bash
docker run --rm --gpus all --entrypoint python3 whisper-eval-gpu \
  -c "import ctranslate2; print(ctranslate2.version); print(ctranslate2.get_cuda_device_count())"
```

Spark ARM64에서 이 값이 0이면 Docker GPU passthrough와는 별개로 CTranslate2 CUDA runtime/wheel 문제일 가능성이 큽니다.

## 출력

각 eval script는 다음을 출력합니다.

- model/device/dtype
- CUDA availability
- GPU 이름
- model load time
- transcription duration
- transcript
- 저장된 output path

Transcript는 기본적으로 `tools/whisper_eval/outputs/` 아래에 저장됩니다.

## Next Session Checklist

- 안정 production STT는 계속 OpenAI로 유지합니다.
- local GPU backend는 `docker-compose.local-gpu.yml` overlay에서만 검증합니다.
- GPU 품질 비교는 NGC PyTorch container와 이 eval harness에서 계속합니다.
- 비교 대상:
  - OpenAI baseline
  - Whisper `openai/whisper-large-v3` GPU
  - Whisper `openai/whisper-large-v3-turbo`, 사용 가능하면
  - `distil-whisper/distil-large-v3`, 사용 가능하면
- 평가 기준:
  - 한국어 비즈니스 용어 fidelity
  - 날짜와 숫자 정확도
  - action item fidelity
  - hallucination rate
  - downstream summarization 입력으로서의 유용성

## Caveats

- 이 디렉터리는 evaluation-only입니다.
- production-safe local GPU provider는 별도 코드 경로인 `backend/services/stt/transformers_whisper.py`와 `STT_PROVIDER=local_gpu_whisper`에 있습니다.
- 이 eval harness는 API flow, backend storage, frontend, summarization pipeline을 실행하지 않습니다.
- diarization, batching, streaming, retry, production chunk orchestration은 평가 범위 밖입니다.
- 첫 실행은 HuggingFace model download 때문에 오래 걸릴 수 있습니다.
- HuggingFace cache는 `large-v3` 재평가에 유용하므로 당분간 유지합니다.
