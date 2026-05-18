# faster-whisper GPU Evaluation

이 디렉터리는 Meeting Summarizer 앱 런타임과 분리된 GPU STT 평가용 도구입니다.
프로덕션 provider, frontend, summarization, Docker Compose 설정을 변경하지 않고
단일 오디오 파일에 대해 faster-whisper 전사 결과와 timing을 확인합니다.

## 목표

- Korean meeting audio에서 로컬 faster-whisper 품질을 OpenAI STT baseline과 비교합니다.
- `distil-large-v3`가 내부 회의 전사에 충분한지 먼저 확인합니다.
- GPU 실행 시 model load time, transcription time, realtime factor를 확인합니다.
- 결과 transcript를 저장해 사람이 OpenAI 결과와 직접 비교할 수 있게 합니다.

## 사용법

프로젝트 루트에서 실행합니다.

```bash
python3 tools/whisper_eval/evaluate_whisper.py /path/to/meeting_audio.wav
```

기본값은 GPU 평가 대상에 맞춰져 있습니다.

```text
model=distil-large-v3
device=cuda
compute_type=float16
language=ko
```

CLI 인자로 덮어쓸 수 있습니다.

```bash
python3 tools/whisper_eval/evaluate_whisper.py /path/to/meeting_audio.wav \
  --model large-v3 \
  --device cuda \
  --compute-type float16 \
  --language ko
```

환경 변수로도 설정할 수 있습니다.

```bash
WHISPER_EVAL_MODEL=distil-large-v3 \
WHISPER_EVAL_DEVICE=cuda \
WHISPER_EVAL_COMPUTE_TYPE=float16 \
WHISPER_EVAL_LANGUAGE=ko \
python3 tools/whisper_eval/evaluate_whisper.py /path/to/meeting_audio.wav
```

Transcript는 기본적으로 다음 위치에 저장됩니다.

```text
tools/whisper_eval/outputs/<audio>_<model>_<device>_<timestamp>.txt
```

저장 위치를 바꾸려면 `--output-dir` 또는 `--output-file`을 사용합니다.

## GPU Docker 실행

이 Dockerfile은 평가 도구 전용입니다. 프로덕션 `docker-compose.yml`, backend,
frontend runtime과 연결하지 않습니다.

프로젝트 루트에서 이미지를 빌드합니다.

```bash
docker build -f tools/whisper_eval/Dockerfile.gpu -t whisper-eval-gpu .
```

CUDA/CTranslate2 preflight를 먼저 확인합니다.

```bash
docker run --rm --gpus all whisper-eval-gpu --help

docker run --rm --gpus all --entrypoint python3 whisper-eval-gpu \
  -c "import ctranslate2; print(ctranslate2.version); print(ctranslate2.get_cuda_device_count())"
```

오디오 파일을 전사합니다.

```bash
docker run --rm --gpus all \
  -v "$PWD/test-audio.m4a:/audio/test-audio.m4a:ro" \
  -v "$PWD/tools/whisper_eval/outputs:/outputs" \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  whisper-eval-gpu /audio/test-audio.m4a --output-dir /outputs
```

## Transformers Whisper GPU 실행

Spark 서버는 `linux/arm64/v8` 환경입니다. Docker GPU passthrough와 CUDA 컨테이너의
`nvidia-smi`는 정상 동작하지만, ARM64에서 CTranslate2 CUDA wheel 생태계가 아직
불안정해 `ctranslate2.get_cuda_device_count()`가 0으로 남는 상황이 있었습니다.
이 경로는 faster-whisper 평가 harness를 제거하지 않고, PyTorch CUDA 기반
Transformers Whisper로 로컬 GPU STT 품질을 먼저 확인하기 위한 별도 평가 도구입니다.

프로젝트 루트에서 이미지를 빌드합니다.

```bash
docker build -f tools/whisper_eval/Dockerfile.transformers-gpu -t transformers-whisper-gpu .
```

Torch CUDA preflight를 확인합니다.

```bash
docker run --rm --gpus all --entrypoint python3 transformers-whisper-gpu \
  -c "import torch; print(torch.version); print(torch.cuda.is_available()); print(torch.cuda.device_count())"
```

GPU 이름까지 확인하려면 다음 명령을 사용합니다.

```bash
docker run --rm --gpus all --entrypoint python3 transformers-whisper-gpu \
  -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
```

오디오 파일을 전사합니다.

```bash
docker run --rm --gpus all \
  -v "$PWD/test-audio.m4a:/audio/test-audio.m4a:ro" \
  -v "$PWD/tools/whisper_eval/outputs:/outputs" \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  transformers-whisper-gpu /audio/test-audio.m4a --output-dir /outputs
```

기본값은 다음과 같습니다.

```text
model=openai/whisper-large-v3
device=cuda
torch_dtype=float16
language=ko
task=transcribe
```

모델이나 dtype을 바꿔 비교할 수 있습니다.

```bash
docker run --rm --gpus all \
  -v "$PWD/test-audio.m4a:/audio/test-audio.m4a:ro" \
  -v "$PWD/tools/whisper_eval/outputs:/outputs" \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  transformers-whisper-gpu /audio/test-audio.m4a \
    --model openai/whisper-large-v3 \
    --torch-dtype float16 \
    --language ko \
    --output-dir /outputs
```

## 권장 모델

- `distil-large-v3`: 첫 GPU 품질/속도 평가 기본값입니다.
- `large-v3`: 품질 상한선을 확인할 때 사용합니다. 더 느리고 메모리를 더 씁니다.
- `medium`: GPU packaging이 불안정할 때 비교용으로 가볍게 확인합니다.
- `small`: smoke test나 CPU fallback 확인용입니다.

## 출력 지표

- `audio_duration_seconds`: 가능한 경우 pydub/ffmpeg 또는 wav metadata로 계산합니다.
- `model_load_seconds`: faster-whisper model load 시간입니다.
- `transcription_seconds`: segment iterator를 모두 소비해 transcript를 만든 시간입니다.
- `realtime_factor`: `transcription_seconds / audio_duration_seconds`입니다.
- `output_path`: 저장된 transcript 파일입니다.

## GPU 요구 사항

- NVIDIA GPU와 CUDA runtime이 서버에서 동작해야 합니다.
- `faster-whisper`와 그 하위 dependency인 CTranslate2가 CUDA 실행을 지원해야 합니다.
- `device=cuda`, `compute_type=float16` 조합이 실패하면 CUDA/CTranslate2 wheel 호환성을 먼저 확인합니다.

## 문제 해결

이 평가 이미지는 CUDA 12.4 + cuDNN 9 runtime 위에서 CTranslate2 GPU wheel을 쓰도록
`ctranslate2==4.5.0`을 먼저 설치한 뒤 `faster-whisper==1.1.1`을 설치합니다. `pip install
faster-whisper`가 고르는 transitive CTranslate2 버전에 의존하지 않기 위한 pin입니다.

`ctranslate2.get_cuda_device_count()`가 `0`이면 먼저 Docker GPU passthrough를 확인합니다.

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 nvidia-smi
```

위 명령은 GPU를 보는데 preflight만 `0`이면 CUDA runtime과 CTranslate2 wheel 조합 문제일
가능성이 큽니다. 이미지를 다시 빌드하고 pin이 반영됐는지 확인합니다.

```bash
docker build --no-cache -f tools/whisper_eval/Dockerfile.gpu -t whisper-eval-gpu .

docker run --rm --gpus all --entrypoint python3 whisper-eval-gpu \
  -c "import ctranslate2; print(ctranslate2.version); print(ctranslate2.get_cuda_device_count())"
```

CUDA wheel mismatch가 계속되면 `tools/whisper_eval/Dockerfile.gpu`의
`CTRANSLATE2_VERSION`만 바꿔 비교합니다. CUDA 12 + cuDNN 9 계열은 `4.5.x` 이상이
대상이고, CUDA 12 + cuDNN 8 환경은 `4.4.0`으로 낮추는 우회가 알려져 있습니다.

GPU 경로가 막혀도 스크립트 자체와 오디오 decode를 확인하려면 CPU sanity check를 실행합니다.

```bash
docker run --rm \
  -v "$PWD/test-audio.m4a:/audio/test-audio.m4a:ro" \
  -v "$PWD/tools/whisper_eval/outputs:/outputs" \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  whisper-eval-gpu /audio/test-audio.m4a \
    --device cpu \
    --compute-type int8 \
    --model small \
    --output-dir /outputs
```

## Caveats

- 이 도구는 품질 평가 harness일 뿐이며 프로덕션 STT flow에 연결되어 있지 않습니다.
- diarization, batching, streaming, retry, chunk orchestration은 다루지 않습니다.
- 첫 실행은 모델 다운로드 때문에 오래 걸릴 수 있습니다.
- 긴 회의 오디오는 단일 파일 전사로 평가하므로, 실제 앱의 chunked OpenAI path와 성능 특성이 다를 수 있습니다.
- 품질 판단은 저장된 transcript를 OpenAI baseline output과 나란히 비교해 진행합니다.
