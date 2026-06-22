"""Transformers Whisper GPU 전사 품질 평가용 독립 실행 스크립트입니다.

PyTorch CUDA 기반 Whisper 전사가 Spark ARM64 GPU 서버에서 동작하는지 확인하기 위한
평가 도구입니다. 프로덕션 앱 런타임과 연결하지 않습니다.
"""

from __future__ import annotations

import argparse
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "openai/whisper-large-v3"
DEFAULT_DEVICE = "cuda"
DEFAULT_TORCH_DTYPE = "float16"
DEFAULT_LANGUAGE = "ko"
DEFAULT_TASK = "transcribe"


def parse_args() -> argparse.Namespace:
    """CLI 인자와 환경 변수 기본값을 파싱합니다."""
    parser = argparse.ArgumentParser(description="Run a standalone Transformers Whisper STT evaluation.")
    parser.add_argument("audio_file", type=Path, help="Transcribe할 오디오 파일 경로")
    parser.add_argument("--model", default=os.getenv("TRANSFORMERS_WHISPER_MODEL", DEFAULT_MODEL))
    parser.add_argument("--device", default=os.getenv("TRANSFORMERS_WHISPER_DEVICE", DEFAULT_DEVICE))
    parser.add_argument("--torch-dtype", default=os.getenv("TRANSFORMERS_WHISPER_TORCH_DTYPE", DEFAULT_TORCH_DTYPE))
    parser.add_argument("--language", default=os.getenv("TRANSFORMERS_WHISPER_LANGUAGE", DEFAULT_LANGUAGE))
    parser.add_argument("--task", default=os.getenv("TRANSFORMERS_WHISPER_TASK", DEFAULT_TASK))
    parser.add_argument(
        "--return-timestamps",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("TRANSFORMERS_WHISPER_RETURN_TIMESTAMPS", "true").strip().lower() not in {"0", "false", "no"},
        help="긴 오디오 전사를 위해 timestamp chunk 반환을 켭니다.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.getenv("TRANSFORMERS_WHISPER_OUTPUT_DIR", Path(__file__).resolve().parent / "outputs")),
        help="Transcript 저장 디렉터리",
    )
    return parser.parse_args()


def resolve_torch_dtype(torch_module: Any, dtype_name: str) -> Any:
    """문자열 dtype 설정을 torch dtype 객체로 변환합니다."""
    normalized = dtype_name.strip().lower()
    dtype_map = {
        "float16": torch_module.float16,
        "fp16": torch_module.float16,
        "half": torch_module.float16,
        "bfloat16": torch_module.bfloat16,
        "bf16": torch_module.bfloat16,
        "float32": torch_module.float32,
        "fp32": torch_module.float32,
    }
    if normalized not in dtype_map:
        raise ValueError(f"Unsupported torch dtype: {dtype_name}")
    return dtype_map[normalized]


def resolve_pipeline_device(torch_module: Any, device: str) -> str | int:
    """Transformers pipeline에 전달할 device 값을 결정합니다."""
    normalized = device.strip().lower()
    if normalized in {"cuda", "gpu"}:
        if not torch_module.cuda.is_available():
            raise RuntimeError("Requested device=cuda, but torch.cuda.is_available() is false.")
        return 0
    if normalized in {"cpu", "-1"}:
        return -1
    if normalized.startswith("cuda:"):
        if not torch_module.cuda.is_available():
            raise RuntimeError(f"Requested device={device}, but torch.cuda.is_available() is false.")
        return normalized
    return device


def build_output_path(audio_file: Path, output_dir: Path, model: str, device: str) -> Path:
    """Transcript 저장 경로를 만듭니다."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = slugify(model)
    device_slug = slugify(device)
    return output_dir / f"{audio_file.stem}_{model_slug}_{device_slug}_{timestamp}.txt"


def slugify(value: str) -> str:
    """파일명에 쓰기 쉬운 값으로 정리합니다."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "value"


def save_transcript(output_path: Path, transcript: str) -> None:
    """Transcript를 UTF-8 텍스트 파일로 저장합니다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(transcript, encoding="utf-8")


def main() -> int:
    """Transformers Whisper pipeline으로 단일 오디오 파일을 전사합니다."""
    args = parse_args()
    audio_file = args.audio_file.expanduser().resolve()
    if not audio_file.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_file}")

    import torch
    from transformers import pipeline

    torch_dtype = resolve_torch_dtype(torch, args.torch_dtype)
    pipeline_device = resolve_pipeline_device(torch, args.device)
    cuda_available = torch.cuda.is_available()
    cuda_device_count = torch.cuda.device_count()
    gpu_name = torch.cuda.get_device_name(0) if cuda_available and cuda_device_count else "none"

    print("Transformers Whisper GPU evaluation")
    print(f"audio_file={audio_file}")
    print(f"model={args.model}")
    print(f"device={args.device}")
    print(f"pipeline_device={pipeline_device}")
    print(f"torch_dtype={args.torch_dtype}")
    print(f"language={args.language}")
    print(f"task={args.task}")
    print(f"return_timestamps={args.return_timestamps}")
    print(f"torch_version={torch.__version__}")
    print(f"torch_cuda_version={torch.version.cuda}")
    print(f"torch_cuda_available={cuda_available}")
    print(f"torch_cuda_device_count={cuda_device_count}")
    print(f"gpu_name={gpu_name}")

    model_load_started_at = time.perf_counter()
    transcriber = pipeline(
        task="automatic-speech-recognition",
        model=args.model,
        torch_dtype=torch_dtype,
        device=pipeline_device,
    )
    model_load_seconds = time.perf_counter() - model_load_started_at

    transcription_started_at = time.perf_counter()
    result = transcriber(
        str(audio_file),
        return_timestamps=args.return_timestamps,
        generate_kwargs={"language": args.language, "task": args.task},
    )
    transcription_seconds = time.perf_counter() - transcription_started_at
    transcript = str(result.get("text", "")).strip()

    output_path = build_output_path(
        audio_file=audio_file,
        output_dir=args.output_dir.expanduser().resolve(),
        model=args.model,
        device=args.device,
    )
    save_transcript(output_path, transcript)

    print(f"model_load_seconds={model_load_seconds:.3f}")
    print(f"transcription_seconds={transcription_seconds:.3f}")
    print(f"output_path={output_path}")
    print()
    print("Transcript")
    print(transcript)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
