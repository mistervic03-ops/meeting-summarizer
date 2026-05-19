"""환경 변수 기반 STT provider 선택을 담당합니다."""

from __future__ import annotations

import os
import time
import logging
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Literal, Protocol

from summarization.models import NormalizedTranscript

TranscriptionMode = Literal["plain", "diarized"]
logger = logging.getLogger(__name__)

DEFAULT_LOCAL_WHISPER_MODEL = "small"
DEFAULT_LOCAL_WHISPER_DEVICE = "cpu"
DEFAULT_LOCAL_WHISPER_COMPUTE_TYPE = "int8"
DEFAULT_LOCAL_WHISPER_LANGUAGE = "ko"


class TranscribeProvider(Protocol):
    """STT provider가 제공해야 하는 최소 전사 인터페이스입니다."""

    name: str

    def transcribe(
        self,
        audio_files: Path | list[Path],
        mode: TranscriptionMode = "plain",
    ) -> str | NormalizedTranscript:
        """오디오 파일을 받아 기존 transcript 반환 형태로 전사합니다."""


class OpenAITranscribeProvider:
    """기존 OpenAI STT 구현을 그대로 호출하는 provider입니다."""

    name = "openai"

    def __init__(self, implementation: Callable[[Path | list[Path], TranscriptionMode], str | NormalizedTranscript]) -> None:
        """기존 OpenAI 구현 함수를 provider에 연결합니다."""
        self.implementation = implementation

    def transcribe(
        self,
        audio_files: Path | list[Path],
        mode: TranscriptionMode = "plain",
    ) -> str | NormalizedTranscript:
        """현재 transcribe.py의 OpenAI chunk/retry workflow를 그대로 실행합니다."""
        return self.implementation(audio_files, mode=mode)


class LocalWhisperProvider:
    """faster-whisper CPU 경로로 plain STT를 수행하는 provider입니다."""

    name = "local_whisper"
    _model_cache: dict[tuple[str, str, str], Any] = {}
    _model_lock = Lock()

    def transcribe(
        self,
        audio_files: Path | list[Path],
        mode: TranscriptionMode = "plain",
    ) -> str | NormalizedTranscript:
        """faster-whisper 로컬 모델로 plain transcript를 반환합니다."""
        if mode != "plain":
            raise NotImplementedError("STT_PROVIDER=local_whisper only supports plain transcription for now.")

        model_name = get_local_whisper_model_name()
        device = get_local_whisper_device()
        compute_type = get_local_whisper_compute_type()
        language = get_local_whisper_language()
        model = self.get_model(model_name=model_name, device=device, compute_type=compute_type)
        audio_paths = normalize_audio_files(audio_files)
        started_at = time.perf_counter()
        logger.info(
            "stt_provider_selected provider=%s model=%s device=%s compute_type=%s language=%s file_count=%s",
            self.name,
            model_name,
            device,
            compute_type,
            language,
            len(audio_paths),
        )

        transcripts = [self.transcribe_file(model, audio_path, language) for audio_path in audio_paths]
        elapsed_seconds = time.perf_counter() - started_at
        logger.info(
            "local_whisper_transcription_complete model=%s device=%s compute_type=%s elapsed_seconds=%.3f",
            model_name,
            device,
            compute_type,
            elapsed_seconds,
        )
        return "\n\n".join(transcript.strip() for transcript in transcripts if transcript.strip())

    @classmethod
    def get_model(cls, model_name: str, device: str, compute_type: str) -> Any:
        """faster-whisper 모델을 설정별로 한 번만 로드해 재사용합니다."""
        cache_key = (model_name, device, compute_type)
        if cache_key in cls._model_cache:
            return cls._model_cache[cache_key]

        with cls._model_lock:
            if cache_key in cls._model_cache:
                return cls._model_cache[cache_key]

            WhisperModel = import_whisper_model()
            started_at = time.perf_counter()
            logger.info(
                "local_whisper_model_load_start model=%s device=%s compute_type=%s",
                model_name,
                device,
                compute_type,
            )
            # TODO: CUDA/faster-whisper 패키징이 확정되면 device=cuda 설정을 검증합니다.
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
            elapsed_seconds = time.perf_counter() - started_at
            logger.info(
                "local_whisper_model_load_complete model=%s device=%s compute_type=%s elapsed_seconds=%.3f",
                model_name,
                device,
                compute_type,
                elapsed_seconds,
            )
            cls._model_cache[cache_key] = model
            return model

    def transcribe_file(self, model: Any, audio_path: Path, language: str) -> str:
        """단일 오디오 파일을 faster-whisper로 전사하고 segment text를 합칩니다."""
        started_at = time.perf_counter()
        segments, _info = model.transcribe(str(audio_path), language=language)
        transcript = " ".join(getattr(segment, "text", "").strip() for segment in segments if getattr(segment, "text", "").strip())
        logger.info(
            "local_whisper_file_transcribed path=%s elapsed_seconds=%.3f",
            audio_path,
            time.perf_counter() - started_at,
        )
        return transcript


class LocalGpuWhisperProvider:
    """Transformers Whisper resident GPU 모델로 plain STT를 수행하는 provider입니다."""

    name = "local_gpu_whisper"

    def transcribe(
        self,
        audio_files: Path | list[Path],
        mode: TranscriptionMode = "plain",
    ) -> str | NormalizedTranscript:
        """기존 plain chunk workflow를 유지하며 local GPU Whisper로 전사합니다."""
        if mode != "plain":
            raise NotImplementedError("STT_PROVIDER=local_gpu_whisper only supports plain transcription for now.")

        from backend.services.stt import transformers_whisper
        from transcribe import (
            TranscriptionTimingStats,
            cleanup_temp_files,
            get_audio_chunk_config,
            get_plain_transcription_concurrency,
            log_trace_event,
            log_transcription_run_diagnostics,
            normalize_audio_files as normalize_transcribe_audio_files,
            prepare_audio_files,
            transcribe_plain_chunks_concurrently,
        )

        config = transformers_whisper.get_config()
        workflow_started_at = time.perf_counter()
        chunk_config = get_audio_chunk_config("plain")
        concurrency = get_plain_transcription_concurrency()
        timing_stats = TranscriptionTimingStats(
            mode="plain",
            model_name=config.model_name,
            chunk_config=chunk_config,
            workflow_started_at=workflow_started_at,
            concurrency=concurrency,
        )
        temp_files: list[Path] = []

        logger.info(
            "stt_provider_selected provider=%s model=%s device=%s torch_dtype=%s gpu_max_concurrency=%s",
            self.name,
            config.model_name,
            config.device,
            config.torch_dtype,
            config.max_concurrency,
        )
        log_trace_event(
            "transcription_workflow_start",
            mode="plain",
            resolved_model=timing_stats.model_name,
            path=audio_files if isinstance(audio_files, Path) else "multiple",
            chunk_duration_seconds=chunk_config.duration_seconds,
            chunk_overlap_seconds=chunk_config.overlap_seconds,
            concurrency=concurrency,
            provider=self.name,
        )

        try:
            preparation_started_at = time.perf_counter()
            files_to_transcribe = prepare_audio_files(audio_files, mode="plain", model_name=config.model_name)
            timing_stats.preparation_seconds = time.perf_counter() - preparation_started_at
            original_files = normalize_transcribe_audio_files(audio_files)
            temp_files.extend(file for file in files_to_transcribe if file not in original_files)
            timing_stats.total_chunks = len(files_to_transcribe)
            log_transcription_run_diagnostics(
                mode="plain",
                model_name=timing_stats.model_name,
                source_files=original_files,
                chunk_files=files_to_transcribe,
                chunk_config=chunk_config,
            )

            transcripts = transcribe_plain_chunks_concurrently(
                files_to_transcribe=files_to_transcribe,
                chunk_config=chunk_config,
                source_files=original_files,
                timing_stats=timing_stats,
                model_name=config.model_name,
                concurrency=concurrency,
                chunk_transcriber=lambda audio_path: transformers_whisper.transcribe_file(audio_path, config=config),
            )

            merge_started_at = time.perf_counter()
            log_trace_event("merge_start", mode="plain", chunk_count=len(transcripts), provider=self.name)
            transcript_text = "\n\n".join(transcript.strip() for transcript in transcripts if transcript.strip())
            transcript_text = transformers_whisper.cleanup_repetition_artifacts(transcript_text)
            timing_stats.merge_seconds = time.perf_counter() - merge_started_at
            log_trace_event("merge_complete", mode="plain", elapsed_seconds=timing_stats.merge_seconds, provider=self.name)
            log_trace_event(
                "transcription_complete",
                mode="plain",
                total_elapsed_seconds=time.perf_counter() - timing_stats.workflow_started_at,
                provider=self.name,
            )
            return transcript_text
        except Exception as exc:
            log_trace_event(
                "transcription_workflow_failed",
                mode="plain",
                elapsed_seconds=time.perf_counter() - workflow_started_at,
                provider=self.name,
                error=exc,
            )
            raise RuntimeError(f"Local GPU Whisper transcription failed: {exc}") from exc
        finally:
            cleanup_temp_files(temp_files)


def get_stt_provider_name() -> str:
    """환경 변수에서 STT provider 이름을 읽고 기본값 openai를 반환합니다."""
    return os.getenv("STT_PROVIDER", "openai").strip().lower() or "openai"


def get_local_whisper_model_name() -> str:
    """로컬 Whisper 모델명을 환경 변수 또는 안전한 CPU 기본값으로 반환합니다."""
    return os.getenv("LOCAL_WHISPER_MODEL", DEFAULT_LOCAL_WHISPER_MODEL).strip() or DEFAULT_LOCAL_WHISPER_MODEL


def get_local_whisper_device() -> str:
    """로컬 Whisper 실행 device를 반환합니다."""
    return os.getenv("LOCAL_WHISPER_DEVICE", DEFAULT_LOCAL_WHISPER_DEVICE).strip() or DEFAULT_LOCAL_WHISPER_DEVICE


def get_local_whisper_compute_type() -> str:
    """로컬 Whisper compute type을 반환합니다."""
    return os.getenv("LOCAL_WHISPER_COMPUTE_TYPE", DEFAULT_LOCAL_WHISPER_COMPUTE_TYPE).strip() or DEFAULT_LOCAL_WHISPER_COMPUTE_TYPE


def get_local_whisper_language() -> str:
    """로컬 Whisper 전사 언어 힌트를 반환합니다."""
    return os.getenv("LOCAL_WHISPER_LANGUAGE", DEFAULT_LOCAL_WHISPER_LANGUAGE).strip() or DEFAULT_LOCAL_WHISPER_LANGUAGE


def normalize_audio_files(audio_files: Path | list[Path]) -> list[Path]:
    """단일 Path 또는 Path 목록을 provider 내부 처리용 list로 정규화합니다."""
    if isinstance(audio_files, Path):
        return [audio_files]
    return list(audio_files)


def import_whisper_model() -> Any:
    """faster-whisper WhisperModel을 지연 import하고 설치 안내를 제공합니다."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "STT_PROVIDER=local_whisper requires faster-whisper. "
            "Install it with `python3 -m pip install -r requirements.txt` or `python3 -m pip install faster-whisper`."
        ) from exc
    return WhisperModel


def get_stt_provider(
    openai_implementation: Callable[[Path | list[Path], TranscriptionMode], str | NormalizedTranscript],
) -> TranscribeProvider:
    """STT_PROVIDER 값에 맞는 provider 객체를 반환합니다."""
    provider_name = get_stt_provider_name()
    if provider_name == "openai":
        return OpenAITranscribeProvider(openai_implementation)
    if provider_name == "local_whisper":
        return LocalWhisperProvider()
    if provider_name == "local_gpu_whisper":
        return LocalGpuWhisperProvider()
    raise ValueError("Unsupported STT_PROVIDER. Use 'openai', 'local_whisper', or 'local_gpu_whisper'.")
