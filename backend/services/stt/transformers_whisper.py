"""Transformers Whisper 기반 resident GPU STT 런타임입니다."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LOCAL_GPU_WHISPER_MODEL = "openai/whisper-large-v3-turbo"
DEFAULT_LOCAL_GPU_DEVICE = "cuda:0"
DEFAULT_LOCAL_GPU_TORCH_DTYPE = "float16"
DEFAULT_LOCAL_GPU_MAX_CONCURRENCY = 4
DEFAULT_LOCAL_GPU_LANGUAGE = "ko"
DEFAULT_LOCAL_GPU_TASK = "transcribe"

_pipeline_cache: dict[tuple[str, str, str], Any] = {}
_pipeline_lock = Lock()
_semaphore_lock = Lock()
_inference_semaphore: BoundedSemaphore | None = None
_inference_semaphore_size: int | None = None


@dataclass(frozen=True)
class LocalGpuWhisperConfig:
    """resident local GPU Whisper 모델 설정입니다."""

    model_name: str
    device: str
    torch_dtype: str
    max_concurrency: int
    language: str = DEFAULT_LOCAL_GPU_LANGUAGE
    task: str = DEFAULT_LOCAL_GPU_TASK


def get_config() -> LocalGpuWhisperConfig:
    """환경 변수에서 local GPU Whisper 설정을 읽습니다."""
    return LocalGpuWhisperConfig(
        model_name=os.getenv("LOCAL_GPU_WHISPER_MODEL", DEFAULT_LOCAL_GPU_WHISPER_MODEL).strip()
        or DEFAULT_LOCAL_GPU_WHISPER_MODEL,
        device=os.getenv("LOCAL_GPU_DEVICE", DEFAULT_LOCAL_GPU_DEVICE).strip() or DEFAULT_LOCAL_GPU_DEVICE,
        torch_dtype=os.getenv("LOCAL_GPU_TORCH_DTYPE", DEFAULT_LOCAL_GPU_TORCH_DTYPE).strip()
        or DEFAULT_LOCAL_GPU_TORCH_DTYPE,
        max_concurrency=get_max_concurrency(),
    )


def get_max_concurrency() -> int:
    """GPU inference 전역 동시성 제한값을 반환합니다."""
    raw_value = os.getenv("LOCAL_GPU_MAX_CONCURRENCY", str(DEFAULT_LOCAL_GPU_MAX_CONCURRENCY)).strip()
    try:
        parsed = int(raw_value)
    except ValueError:
        return DEFAULT_LOCAL_GPU_MAX_CONCURRENCY
    return max(1, parsed)


def get_resident_pipeline(config: LocalGpuWhisperConfig | None = None) -> Any:
    """Transformers pipeline을 프로세스 안에서 한 번만 로드해 재사용합니다."""
    resolved_config = config or get_config()
    cache_key = (resolved_config.model_name, resolved_config.device, resolved_config.torch_dtype)
    cached_pipeline = _pipeline_cache.get(cache_key)
    if cached_pipeline is not None:
        return cached_pipeline

    with _pipeline_lock:
        cached_pipeline = _pipeline_cache.get(cache_key)
        if cached_pipeline is not None:
            return cached_pipeline

        torch_module, pipeline_factory = import_transformers_runtime()
        torch_dtype = resolve_torch_dtype(torch_module, resolved_config.torch_dtype)
        pipeline_device = resolve_pipeline_device(torch_module, resolved_config.device)

        logger.info(
            "local_gpu_whisper_model_load_start model=%s device=%s pipeline_device=%s torch_dtype=%s max_concurrency=%s",
            resolved_config.model_name,
            resolved_config.device,
            pipeline_device,
            resolved_config.torch_dtype,
            resolved_config.max_concurrency,
        )
        started_at = time.perf_counter()
        transcriber = pipeline_factory(
            task="automatic-speech-recognition",
            model=resolved_config.model_name,
            torch_dtype=torch_dtype,
            device=pipeline_device,
        )
        elapsed_seconds = time.perf_counter() - started_at
        logger.info(
            "local_gpu_whisper_model_load_complete model=%s device=%s torch_dtype=%s elapsed_seconds=%.3f",
            resolved_config.model_name,
            resolved_config.device,
            resolved_config.torch_dtype,
            elapsed_seconds,
        )
        _pipeline_cache[cache_key] = transcriber
        return transcriber


def transcribe_file(audio_path: Path, config: LocalGpuWhisperConfig | None = None) -> str:
    """resident Transformers Whisper pipeline으로 단일 오디오 파일을 전사합니다."""
    resolved_config = config or get_config()
    transcriber = get_resident_pipeline(resolved_config)
    semaphore = get_inference_semaphore(resolved_config.max_concurrency)

    logger.info(
        "local_gpu_whisper_inference_wait path=%s model=%s max_concurrency=%s",
        audio_path,
        resolved_config.model_name,
        resolved_config.max_concurrency,
    )
    with semaphore:
        started_at = time.perf_counter()
        result = transcriber(
            str(audio_path),
            return_timestamps=True,
            generate_kwargs={
                "language": resolved_config.language,
                "task": resolved_config.task,
            },
        )
        elapsed_seconds = time.perf_counter() - started_at

    transcript = extract_transcript_text(result)
    logger.info(
        "local_gpu_whisper_inference_complete path=%s model=%s device=%s elapsed_seconds=%.3f",
        audio_path,
        resolved_config.model_name,
        resolved_config.device,
        elapsed_seconds,
    )
    return transcript


def get_inference_semaphore(max_concurrency: int) -> BoundedSemaphore:
    """전역 GPU inference 동시성 제한 semaphore를 반환합니다."""
    global _inference_semaphore, _inference_semaphore_size
    with _semaphore_lock:
        if _inference_semaphore is None or _inference_semaphore_size != max_concurrency:
            _inference_semaphore = BoundedSemaphore(max_concurrency)
            _inference_semaphore_size = max_concurrency
        return _inference_semaphore


def import_transformers_runtime() -> tuple[Any, Any]:
    """torch/transformers를 지연 import하고 runtime 준비 안내를 제공합니다."""
    try:
        import torch
        from transformers import pipeline
    except ImportError as exc:
        raise RuntimeError(
            "STT_PROVIDER=local_gpu_whisper requires torch and transformers. "
            "Use the validated NGC PyTorch runtime and install transformers/accelerate/sentencepiece "
            "before enabling this provider."
        ) from exc
    return torch, pipeline


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
        raise ValueError(f"Unsupported LOCAL_GPU_TORCH_DTYPE: {dtype_name}")
    return dtype_map[normalized]


def resolve_pipeline_device(torch_module: Any, device: str) -> str | int:
    """Transformers pipeline에 전달할 device 값을 결정합니다."""
    normalized = device.strip().lower()
    if normalized in {"cuda", "gpu"}:
        ensure_cuda_available(torch_module, device)
        return 0
    if normalized.startswith("cuda:"):
        ensure_cuda_available(torch_module, device)
        return normalized
    if normalized in {"cpu", "-1"}:
        return -1
    return device


def ensure_cuda_available(torch_module: Any, device: str) -> None:
    """CUDA device 요청 시 torch CUDA 사용 가능 여부를 확인합니다."""
    if not torch_module.cuda.is_available():
        raise RuntimeError(f"Requested LOCAL_GPU_DEVICE={device}, but torch.cuda.is_available() is false.")


def extract_transcript_text(result: Any) -> str:
    """Transformers pipeline 응답에서 transcript text를 추출합니다."""
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        return str(result.get("text", "")).strip()
    return str(getattr(result, "text", "")).strip()


def reset_resident_pipeline_for_tests() -> None:
    """단위 테스트에서 resident model cache와 semaphore를 초기화합니다."""
    global _inference_semaphore, _inference_semaphore_size
    with _pipeline_lock:
        _pipeline_cache.clear()
    with _semaphore_lock:
        _inference_semaphore = None
        _inference_semaphore_size = None
