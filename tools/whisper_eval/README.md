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

## Caveats

- 이 도구는 품질 평가 harness일 뿐이며 프로덕션 STT flow에 연결되어 있지 않습니다.
- diarization, batching, streaming, retry, chunk orchestration은 다루지 않습니다.
- 첫 실행은 모델 다운로드 때문에 오래 걸릴 수 있습니다.
- 긴 회의 오디오는 단일 파일 전사로 평가하므로, 실제 앱의 chunked OpenAI path와 성능 특성이 다를 수 있습니다.
- 품질 판단은 저장된 transcript를 OpenAI baseline output과 나란히 비교해 진행합니다.
