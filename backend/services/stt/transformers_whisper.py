"""Transformers Whisper 기반 resident GPU STT 런타임입니다."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LOCAL_GPU_WHISPER_MODEL = "openai/whisper-large-v3-turbo"
DEFAULT_LOCAL_GPU_DEVICE = "cuda:0"
DEFAULT_LOCAL_GPU_TORCH_DTYPE = "float16"
DEFAULT_LOCAL_GPU_MAX_CONCURRENCY = 3
DEFAULT_LOCAL_GPU_LANGUAGE = "ko"
DEFAULT_LOCAL_GPU_TASK = "transcribe"
DEFAULT_LOCAL_GPU_STT_PROMPT_ENABLED = "false"
MAX_LOCAL_GPU_WHISPER_PROMPT_CHARS = 500
MIN_REPETITION_COLLAPSE_COUNT = 4

_pipeline_cache: dict[tuple[str, str, str], Any] = {}
_pipeline_lock = Lock()
_semaphore_lock = Lock()
_prompt_lock = Lock()
_inference_semaphore: BoundedSemaphore | None = None
_inference_semaphore_size: int | None = None
_initial_prompt_cache: dict[tuple[str, int, bool], str] = {}


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
    prepared_audio_path, cleanup_path = prepare_audio_for_transformers(audio_path)
    try:
        transcriber = get_resident_pipeline(resolved_config)
        semaphore = get_inference_semaphore(resolved_config.max_concurrency)

        logger.info(
            "local_gpu_whisper_inference_wait path=%s prepared_path=%s model=%s max_concurrency=%s",
            audio_path,
            prepared_audio_path,
            resolved_config.model_name,
            resolved_config.max_concurrency,
        )
        with semaphore:
            started_at = time.perf_counter()
            result = transcriber(
                str(prepared_audio_path),
                return_timestamps=True,
                generate_kwargs=build_generate_kwargs(resolved_config, transcriber),
            )
            elapsed_seconds = time.perf_counter() - started_at

        transcript = extract_transcript_text(result)
        logger.info(
            "local_gpu_whisper_inference_complete path=%s prepared_path=%s model=%s device=%s elapsed_seconds=%.3f",
            audio_path,
            prepared_audio_path,
            resolved_config.model_name,
            resolved_config.device,
            elapsed_seconds,
        )
        return transcript
    finally:
        if cleanup_path is not None:
            cleanup_path.unlink(missing_ok=True)


def prepare_audio_for_transformers(audio_path: Path) -> tuple[Path, Path | None]:
    """Transformers가 안정적으로 읽을 수 있도록 비-WAV 입력을 임시 WAV로 변환합니다."""
    if audio_path.suffix.lower() == ".wav":
        return audio_path, None

    output_file = tempfile.NamedTemporaryFile(prefix="local_gpu_whisper_", suffix=".wav", delete=False)
    output_path = Path(output_file.name)
    output_file.close()

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_path),
    ]
    logger.info("local_gpu_whisper_audio_convert_start path=%s output_path=%s", audio_path, output_path)
    started_at = time.perf_counter()
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg is required for STT_PROVIDER=local_gpu_whisper to decode uploaded audio files.") from exc
    except subprocess.CalledProcessError as exc:
        output_path.unlink(missing_ok=True)
        error_output = (exc.stderr or exc.stdout or "").strip()
        message = f"ffmpeg failed to convert audio for local_gpu_whisper: {audio_path}"
        if error_output:
            message = f"{message}: {error_output[-500:]}"
        raise RuntimeError(message) from exc

    logger.info(
        "local_gpu_whisper_audio_convert_complete path=%s output_path=%s elapsed_seconds=%.3f",
        audio_path,
        output_path,
        time.perf_counter() - started_at,
    )
    return output_path, output_path


def build_generate_kwargs(config: LocalGpuWhisperConfig, transcriber: Any) -> dict[str, Any]:
    """Whisper generate 옵션에 보수적인 glossary prompt를 선택적으로 추가합니다."""
    generate_kwargs: dict[str, Any] = {
        "language": config.language,
        "task": config.task,
    }
    prompt_ids = build_whisper_prompt_ids(transcriber, config)
    if prompt_ids is not None:
        generate_kwargs["prompt_ids"] = prompt_ids
    return generate_kwargs


def build_whisper_prompt_ids(transcriber: Any, config: LocalGpuWhisperConfig) -> Any | None:
    """pipeline tokenizer가 지원할 때만 initial prompt token을 생성합니다."""
    tokenizer = getattr(transcriber, "tokenizer", None)
    if tokenizer is None or not hasattr(tokenizer, "get_prompt_ids"):
        return None

    prompt = get_local_gpu_whisper_initial_prompt()
    if not prompt:
        return None

    try:
        target_device = resolve_prompt_ids_device(transcriber, config)
        prompt_ids = normalize_prompt_ids_for_transformers(tokenizer.get_prompt_ids(prompt), target_device)
    except Exception as exc:
        logger.warning("local_gpu_whisper_prompt_ids_failed error=%s", exc)
        return None

    logger.info("local_gpu_whisper_prompt_enabled prompt_chars=%s", len(prompt))
    return prompt_ids


def resolve_prompt_ids_device(transcriber: Any, config: LocalGpuWhisperConfig) -> Any | None:
    """prompt_ids를 올릴 inference device를 pipeline 상태와 설정에서 보수적으로 결정합니다."""
    for device in (
        getattr(transcriber, "device", None),
        getattr(getattr(transcriber, "model", None), "device", None),
        config.device,
    ):
        normalized_device = normalize_device_value(device)
        if normalized_device is not None:
            return normalized_device
    return None


def normalize_device_value(device: Any) -> Any | None:
    """Transformers/PyTorch device 표현을 Tensor.to에 넘기기 쉬운 값으로 정리합니다."""
    if device is None:
        return None
    if isinstance(device, int):
        return f"cuda:{device}" if device >= 0 else "cpu"
    text = str(device).strip()
    if not text:
        return None
    if text == "-1":
        return "cpu"
    return device


def normalize_prompt_ids_for_transformers(prompt_ids: Any, target_device: Any | None = None) -> Any:
    """tokenizer prompt ids를 Transformers generation이 기대하는 torch long tensor로 정규화합니다."""
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("torch is required to normalize local_gpu_whisper prompt_ids.") from exc

    tensor_type = getattr(torch, "Tensor", None)
    if tensor_type is not None and isinstance(prompt_ids, tensor_type):
        if hasattr(prompt_ids, "to"):
            return prompt_ids.to(device=target_device, dtype=torch.long) if target_device is not None else prompt_ids.to(dtype=torch.long)
        return prompt_ids
    tensor = torch.tensor(prompt_ids, dtype=torch.long)
    if target_device is not None and hasattr(tensor, "to"):
        return tensor.to(device=target_device, dtype=torch.long)
    return tensor


def get_local_gpu_whisper_initial_prompt() -> str:
    """기존 STT vocabulary에서 organization_terms만 읽어 process-local prompt로 cache합니다."""
    try:
        from transcribe import get_stt_vocabulary_path, stt_vocabulary_hints_enabled

        enabled = local_gpu_stt_prompt_enabled() and stt_vocabulary_hints_enabled()
        vocabulary_path = get_stt_vocabulary_path()
    except Exception as exc:
        logger.warning("local_gpu_whisper_prompt_config_failed error=%s", exc)
        return ""

    cache_key = (str(vocabulary_path), MAX_LOCAL_GPU_WHISPER_PROMPT_CHARS, enabled)
    cached_prompt = _initial_prompt_cache.get(cache_key)
    if cached_prompt is not None:
        return cached_prompt

    with _prompt_lock:
        cached_prompt = _initial_prompt_cache.get(cache_key)
        if cached_prompt is not None:
            return cached_prompt
        if not enabled:
            prompt = ""
        else:
            terms = load_organization_terms(vocabulary_path)
            prompt = build_canonical_terms_prompt(terms)
        _initial_prompt_cache[cache_key] = prompt
        return prompt


def local_gpu_stt_prompt_enabled() -> bool:
    """local GPU Whisper initial prompt 사용 여부를 local runtime 전용 env로 판단합니다."""
    return os.getenv("LOCAL_GPU_ENABLE_STT_PROMPT", DEFAULT_LOCAL_GPU_STT_PROMPT_ENABLED).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def load_organization_terms(vocabulary_path: Path) -> list[str]:
    """기존 vocabulary YAML에서 organization_terms 섹션의 canonical term만 읽습니다."""
    try:
        lines = vocabulary_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    except Exception as exc:
        logger.warning("local_gpu_whisper_vocabulary_load_failed path=%s error=%s", vocabulary_path, exc)
        return []

    try:
        from transcribe import parse_stt_vocabulary_line
    except Exception as exc:
        logger.warning("local_gpu_whisper_vocabulary_parser_unavailable error=%s", exc)
        return []

    terms: list[str] = []
    in_organization_terms = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith((" ", "\t")) and stripped.endswith(":"):
            in_organization_terms = stripped == "organization_terms:"
            continue
        if not in_organization_terms:
            continue
        term = parse_stt_vocabulary_line(line)
        if term is not None:
            terms.append(term)
    return terms


def build_canonical_terms_prompt(terms: list[str]) -> str:
    """canonical term 목록을 짧은 comma-separated Whisper prompt로 만듭니다."""
    try:
        from transcribe import deduplicate_stt_vocabulary_terms

        vocabulary_terms = deduplicate_stt_vocabulary_terms(terms)
    except Exception as exc:
        logger.warning("local_gpu_whisper_vocabulary_dedupe_failed error=%s", exc)
        return ""

    selected_terms: list[str] = []
    for term in vocabulary_terms:
        candidate_prompt = ", ".join([*selected_terms, term])
        if len(candidate_prompt) > MAX_LOCAL_GPU_WHISPER_PROMPT_CHARS:
            break
        selected_terms.append(term)
    return ", ".join(selected_terms)


def cleanup_repetition_artifacts(transcript: str) -> str:
    """local GPU Whisper 출력의 명백한 반복 붕괴 artifact만 보수적으로 줄입니다."""
    original = transcript
    cleaned = transcript
    patterns_removed = 0

    cleanup_rules = [
        # 같은 한글 음절/문자가 길게 반복된 경우: 오오오오오 -> 오
        (re.compile(r"([가-힣])\1{3,}"), r"\1"),
        # 같은 문장부호가 붙거나 띄어서 반복된 경우: . . . . . -> .
        (re.compile(r"([.!?。！？,，;；:：~])(?:\s*\1){3,}"), r"\1"),
        # 짧은 대문자/숫자 acronym이 comma로 반복된 경우: KPI, KPI, KPI, KPI -> KPI
        (re.compile(r"\b([A-Z][A-Z0-9]{0,7})(?:\s*,\s*\1){3,}\b"), r"\1"),
        # 짧은 구절이 네 번 이상 그대로 반복된 경우만 접습니다.
        (
            re.compile(
                r"\b([A-Za-z가-힣0-9]{1,12}\s+[A-Za-z가-힣0-9]{1,12}(?:\s+[A-Za-z가-힣0-9]{1,12}){0,3})"
                r"(?:[,\s]+\1){3,}\b"
            ),
            r"\1",
        ),
    ]

    for pattern, replacement in cleanup_rules:
        cleaned, count = pattern.subn(replacement, cleaned)
        patterns_removed += count

    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.!?,;:])", r"\1", cleaned).strip()

    if cleaned != original:
        logger.info(
            "local_gpu_whisper_repetition_cleanup_applied chars_removed=%s patterns_removed=%s",
            max(0, len(original) - len(cleaned)),
            patterns_removed,
        )
    return cleaned


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
    with _prompt_lock:
        _initial_prompt_cache.clear()
