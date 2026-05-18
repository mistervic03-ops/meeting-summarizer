"""회의 오디오 파일을 텍스트로 변환하는 STT 보조 함수입니다."""

from __future__ import annotations

import os
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydub import AudioSegment

from summarization.models import NormalizedTranscript, TranscriptUtterance
from utils import AudioChunkConfig, cleanup_temp_files, ensure_audio_file, get_audio_format, split_audio_if_needed


logger = logging.getLogger(__name__)

# 기본 STT 모델입니다. 운영 환경에서는 OPENAI_TRANSCRIPTION_MODEL로 교체할 수 있습니다.
TRANSCRIBE_RUNTIME_VERSION = "chunk-retry-v2"
TRACE_PREFIX = "[TRANSCRIBE_TRACE]"
DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-transcribe"
DEFAULT_DIARIZED_TRANSCRIPTION_MODEL = "gpt-4o-transcribe-diarize"
DEFAULT_TRANSCRIPTION_LANGUAGE = "ko"
DEFAULT_PLAIN_CHUNK_DURATION_SECONDS = 300
DEFAULT_PLAIN_CHUNK_OVERLAP_SECONDS = 0
DEFAULT_PLAIN_TRANSCRIPTION_CONCURRENCY = 3
MAX_PLAIN_TRANSCRIPTION_CONCURRENCY = 5
DEFAULT_DIARIZED_CHUNK_DURATION_SECONDS = 150
DEFAULT_DIARIZED_CHUNK_OVERLAP_SECONDS = 0
CHUNK_DURATION_TOLERANCE_SECONDS = 3
INPUT_TOO_LARGE_MAX_RETRY_DEPTH = 2
MIN_RETRY_CHUNK_DURATION_SECONDS = 30


@dataclass(frozen=True)
class AudioChunkDiagnostic:
    """전사 직전에 확인한 오디오 파일 진단 정보입니다."""

    path: Path
    duration_seconds: float | None
    size_mb: float


@dataclass
class TranscriptionTimingStats:
    """전사 workflow의 실제 소요 시간을 요약하기 위한 상태입니다."""

    mode: Literal["plain", "diarized"]
    model_name: str
    chunk_config: AudioChunkConfig
    workflow_started_at: float = field(default_factory=time.perf_counter)
    total_chunks: int = 0
    preparation_seconds: float = 0.0
    merge_seconds: float = 0.0
    retry_count: int = 0
    concurrency: int = 1
    chunk_elapsed_seconds: list[float] = field(default_factory=list)

    def record_chunk(self, elapsed_seconds: float) -> None:
        """청크 하나의 OpenAI 요청 소요 시간을 기록합니다."""
        self.chunk_elapsed_seconds.append(elapsed_seconds)

    def record_retry(self) -> None:
        """input_too_large 재시도 횟수를 기록합니다."""
        self.retry_count += 1


def get_trace_timestamp() -> str:
    """trace 로그에 사용할 사람이 읽기 쉬운 현재 시각을 반환합니다."""
    return datetime.now().strftime("%H:%M:%S")


def get_trace_prefix() -> str:
    """모든 전사 trace 로그의 공통 prefix를 반환합니다."""
    return f"[{get_trace_timestamp()}]{TRACE_PREFIX}"


def format_elapsed_seconds(started_at: float) -> str:
    """perf_counter 시작점 기준 경과 시간을 로그 문자열로 반환합니다."""
    return f"{time.perf_counter() - started_at:.3f}"


def log_transcribe_trace(
    function_name: str,
    mode: str | None = None,
    model_name: str | None = None,
    audio_path: Path | None = None,
    chunk_config: AudioChunkConfig | None = None,
    retry_wrapper: bool = False,
    retry_depth: int | None = None,
    diagnostic: AudioChunkDiagnostic | None = None,
) -> None:
    """전사 런타임 경로를 추적하기 위한 명확한 로그를 남깁니다."""
    logger.warning(
        "%s function=%s mode=%s model=%s path=%s retry_wrapper=%s retry_depth=%s "
        "duration_seconds=%s size_mb=%s chunk_duration_seconds=%s chunk_overlap_seconds=%s runtime_version=%s",
        get_trace_prefix(),
        function_name,
        mode or "unknown",
        model_name or "unknown",
        audio_path or "unknown",
        retry_wrapper,
        "none" if retry_depth is None else retry_depth,
        format_optional_seconds(diagnostic.duration_seconds) if diagnostic else "unknown",
        f"{diagnostic.size_mb:.3f}" if diagnostic else "unknown",
        chunk_config.duration_seconds if chunk_config else "unknown",
        chunk_config.overlap_seconds if chunk_config else "unknown",
        TRANSCRIBE_RUNTIME_VERSION,
    )


def log_trace_event(event_name: str, **metadata: object) -> None:
    """짧고 스캔 가능한 전사 trace 이벤트를 남깁니다."""
    metadata_text = " ".join(f"{key}={format_log_value(value)}" for key, value in metadata.items())
    if metadata_text:
        logger.warning("%s %s %s", get_trace_prefix(), event_name, metadata_text)
    else:
        logger.warning("%s %s", get_trace_prefix(), event_name)


def format_log_value(value: object) -> str:
    """trace metadata 값을 한 줄 로그에 안전하게 넣습니다."""
    if isinstance(value, float):
        return f"{value:.3f}"
    if value is None:
        return "none"
    return str(value)


def build_timing_summary(stats: TranscriptionTimingStats) -> dict[str, object]:
    """전사 workflow timing summary metadata를 생성합니다."""
    chunk_times = stats.chunk_elapsed_seconds
    total_elapsed_seconds = time.perf_counter() - stats.workflow_started_at
    avg_chunk_seconds = sum(chunk_times) / len(chunk_times) if chunk_times else 0.0
    slowest_chunk_seconds = max(chunk_times) if chunk_times else 0.0
    return {
        "mode": stats.mode,
        "model": stats.model_name,
        "total_chunks": stats.total_chunks,
        "completed_chunks": len(chunk_times),
        "total_elapsed_seconds": total_elapsed_seconds,
        "preparation_seconds": stats.preparation_seconds,
        "merge_seconds": stats.merge_seconds,
        "avg_chunk_seconds": avg_chunk_seconds,
        "slowest_chunk_seconds": slowest_chunk_seconds,
        "retry_count": stats.retry_count,
        "concurrency": stats.concurrency,
        "chunk_duration_seconds": stats.chunk_config.duration_seconds,
        "chunk_overlap_seconds": stats.chunk_config.overlap_seconds,
    }


def resolve_transcription_model_name(
    mode: Literal["plain", "diarized"],
    timing_stats: TranscriptionTimingStats | None = None,
    model_name: str | None = None,
) -> str:
    """workflow 시작 시 snapshot된 STT 모델명을 우선 사용합니다."""
    if model_name:
        return model_name
    if timing_stats is not None:
        return timing_stats.model_name
    if mode == "plain":
        return get_transcription_model()
    return get_diarized_transcription_model()


logger.warning("%s transcribe_import runtime_version=%s file=%s", get_trace_prefix(), TRANSCRIBE_RUNTIME_VERSION, __file__)


def transcribe_audio(
    audio_files: Path | list[Path],
    mode: Literal["plain", "diarized"] = "plain",
) -> str | NormalizedTranscript:
    """하나 이상의 오디오 파일을 전사하고 전사문을 하나로 합칩니다."""
    workflow_started_at = time.perf_counter()
    resolved_model = get_diarized_transcription_model() if mode == "diarized" else get_transcription_model()
    log_transcribe_trace(
        "transcribe_audio",
        mode=mode,
        model_name=resolved_model,
        audio_path=audio_files if isinstance(audio_files, Path) else None,
    )
    if mode == "diarized":
        return transcribe_audio_diarized(audio_files)
    if mode != "plain":
        raise ValueError(f"Unsupported transcription mode: {mode}")

    # 이 함수가 새로 만든 청크 파일만 추적해서 finally에서 정리합니다.
    temp_files: list[Path] = []
    chunk_config = get_audio_chunk_config("plain")
    concurrency = get_plain_transcription_concurrency()
    timing_stats = TranscriptionTimingStats(
        mode="plain",
        model_name=resolved_model,
        chunk_config=chunk_config,
        workflow_started_at=workflow_started_at,
        concurrency=concurrency,
    )
    log_trace_event(
        "transcription_workflow_start",
        mode="plain",
        resolved_model=timing_stats.model_name,
        path=audio_files if isinstance(audio_files, Path) else "multiple",
        chunk_duration_seconds=chunk_config.duration_seconds,
        chunk_overlap_seconds=chunk_config.overlap_seconds,
        concurrency=concurrency,
    )

    try:
        # 25MB 초과 파일은 utils.py에서 청크로 나뉘어 API 호출 대상이 됩니다.
        preparation_started_at = time.perf_counter()
        files_to_transcribe = prepare_audio_files(audio_files, mode="plain", model_name=resolved_model)
        timing_stats.preparation_seconds = time.perf_counter() - preparation_started_at
        original_files = normalize_audio_files(audio_files)
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
            model_name=resolved_model,
            concurrency=concurrency,
        )

        merge_started_at = time.perf_counter()
        log_trace_event("merge_start", mode="plain", chunk_count=len(transcripts))
        transcript_text = "\n\n".join(transcript.strip() for transcript in transcripts if transcript.strip())
        timing_stats.merge_seconds = time.perf_counter() - merge_started_at
        log_trace_event("merge_complete", mode="plain", elapsed_seconds=timing_stats.merge_seconds)
        log_trace_event(
            "transcription_complete",
            mode="plain",
            total_elapsed_seconds=time.perf_counter() - timing_stats.workflow_started_at,
        )
        log_trace_event("transcription_summary", **build_timing_summary(timing_stats))
        return transcript_text
    except Exception as exc:
        log_trace_event(
            "transcription_workflow_failed",
            mode="plain",
            elapsed_seconds=format_elapsed_seconds(workflow_started_at),
            error=exc,
        )
        raise RuntimeError(f"Audio transcription failed: {exc}") from exc
    finally:
        cleanup_temp_files(temp_files)


def transcribe_audio_diarized(audio_files: Path | list[Path]) -> NormalizedTranscript:
    """diarization provider 경로로 오디오를 전사하고 내부 transcript 구조를 반환합니다."""
    workflow_started_at = time.perf_counter()
    resolved_model = get_diarized_transcription_model()
    log_transcribe_trace(
        "transcribe_audio_diarized",
        mode="diarized",
        model_name=resolved_model,
        audio_path=audio_files if isinstance(audio_files, Path) else None,
    )
    temp_files: list[Path] = []
    chunk_config = get_audio_chunk_config("diarized")
    timing_stats = TranscriptionTimingStats(
        mode="diarized",
        model_name=resolved_model,
        chunk_config=chunk_config,
        workflow_started_at=workflow_started_at,
        concurrency=1,
    )
    log_trace_event(
        "transcription_workflow_start",
        mode="diarized",
        resolved_model=timing_stats.model_name,
        path=audio_files if isinstance(audio_files, Path) else "multiple",
        chunk_duration_seconds=chunk_config.duration_seconds,
        chunk_overlap_seconds=chunk_config.overlap_seconds,
    )

    try:
        preparation_started_at = time.perf_counter()
        files_to_transcribe = prepare_audio_files(audio_files, mode="diarized", model_name=resolved_model)
        timing_stats.preparation_seconds = time.perf_counter() - preparation_started_at
        original_files = normalize_audio_files(audio_files)
        temp_files.extend(file for file in files_to_transcribe if file not in original_files)
        timing_stats.total_chunks = len(files_to_transcribe)
        logger.info(
            "diarized_transcription prepared chunk_count=%s chunk_duration_seconds=%s chunk_overlap_seconds=%s",
            len(files_to_transcribe),
            chunk_config.duration_seconds,
            chunk_config.overlap_seconds,
        )
        log_transcription_run_diagnostics(
            mode="diarized",
            model_name=resolved_model,
            source_files=original_files,
            chunk_files=files_to_transcribe,
            chunk_config=chunk_config,
        )

        segments: list[dict[str, Any]] = []
        for chunk_index, audio_file in enumerate(files_to_transcribe, start=1):
            chunk_started_at = time.perf_counter()
            log_trace_event(
                "chunk_request_start",
                mode="diarized",
                index=chunk_index,
                total=len(files_to_transcribe),
                path=audio_file,
            )
            segments.extend(
                call_diarized_transcription_provider(
                    audio_file,
                    chunk_config=chunk_config,
                    source_files=original_files,
                    timing_stats=timing_stats,
                    model_name=resolved_model,
                )
            )
            chunk_elapsed_seconds = time.perf_counter() - chunk_started_at
            timing_stats.record_chunk(chunk_elapsed_seconds)
            log_trace_event(
                "chunk_completed",
                mode="diarized",
                index=chunk_index,
                total=len(files_to_transcribe),
                elapsed_seconds=chunk_elapsed_seconds,
            )

        merge_started_at = time.perf_counter()
        log_trace_event("merge_start", mode="diarized", segment_count=len(segments))
        normalized_transcript = diarized_segments_to_normalized_transcript(segments)
        timing_stats.merge_seconds = time.perf_counter() - merge_started_at
        log_trace_event("merge_complete", mode="diarized", elapsed_seconds=timing_stats.merge_seconds)
        log_trace_event(
            "transcription_complete",
            mode="diarized",
            total_elapsed_seconds=time.perf_counter() - timing_stats.workflow_started_at,
        )
        log_trace_event("transcription_summary", **build_timing_summary(timing_stats))
        return normalized_transcript
    except Exception as exc:
        log_trace_event(
            "transcription_workflow_failed",
            mode="diarized",
            elapsed_seconds=format_elapsed_seconds(workflow_started_at),
            error=exc,
        )
        raise RuntimeError(f"Diarized audio transcription failed: {exc}") from exc
    finally:
        cleanup_temp_files(temp_files)


def transcribe_plain_chunks_concurrently(
    files_to_transcribe: list[Path],
    chunk_config: AudioChunkConfig,
    source_files: list[Path],
    timing_stats: TranscriptionTimingStats,
    model_name: str,
    concurrency: int,
) -> list[str]:
    """plain STT 청크를 제한된 동시성으로 처리하고 원래 순서대로 반환합니다."""
    total_chunks = len(files_to_transcribe)
    if total_chunks == 0:
        return []

    max_workers = min(concurrency, total_chunks)
    started_at = time.perf_counter()
    results: list[str | None] = [None] * total_chunks
    log_trace_event("plain_concurrency_start", concurrency=max_workers, total_chunks=total_chunks)

    def run_chunk(chunk_index: int, audio_file: Path) -> tuple[int, str, float]:
        """worker thread에서 단일 plain chunk를 전사합니다."""
        chunk_started_at = time.perf_counter()
        log_trace_event(
            "plain_chunk_worker_start",
            index=chunk_index,
            total=total_chunks,
            path=audio_file,
        )
        try:
            transcript = transcribe_chunk(
                audio_file,
                chunk_config=chunk_config,
                source_files=source_files,
                timing_stats=timing_stats,
                model_name=model_name,
            )
        except Exception as exc:
            log_trace_event(
                "plain_chunk_worker_failed",
                index=chunk_index,
                total=total_chunks,
                path=audio_file,
                elapsed_seconds=time.perf_counter() - chunk_started_at,
                error=exc,
            )
            raise

        elapsed_seconds = time.perf_counter() - chunk_started_at
        log_trace_event(
            "plain_chunk_worker_done",
            index=chunk_index,
            total=total_chunks,
            path=audio_file,
            elapsed_seconds=elapsed_seconds,
        )
        return chunk_index, transcript, elapsed_seconds

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_chunk = {
            executor.submit(run_chunk, chunk_index, audio_file): (chunk_index, audio_file)
            for chunk_index, audio_file in enumerate(files_to_transcribe, start=1)
        }
        try:
            for future in as_completed(future_to_chunk):
                chunk_index, audio_file = future_to_chunk[future]
                try:
                    completed_index, transcript, elapsed_seconds = future.result()
                except Exception as exc:
                    for pending_future in future_to_chunk:
                        if pending_future is not future:
                            pending_future.cancel()
                    raise RuntimeError(
                        f"Plain transcription chunk failed index={chunk_index} path={audio_file}: {exc}"
                    ) from exc

                results[completed_index - 1] = transcript
                timing_stats.record_chunk(elapsed_seconds)
                log_trace_event(
                    "chunk_completed",
                    mode="plain",
                    index=completed_index,
                    total=total_chunks,
                    elapsed_seconds=elapsed_seconds,
                )
        finally:
            log_trace_event(
                "plain_concurrency_complete",
                total_elapsed_seconds=time.perf_counter() - started_at,
                total_chunks=total_chunks,
            )

    return [transcript or "" for transcript in results]


def transcribe_chunk(
    audio_file: Path,
    chunk_config: AudioChunkConfig | None = None,
    retry_depth: int = 0,
    source_files: list[Path] | None = None,
    timing_stats: TranscriptionTimingStats | None = None,
    model_name: str | None = None,
) -> str:
    """설정된 STT 모델로 단일 오디오 청크를 전사합니다."""
    chunk_config = chunk_config or get_audio_chunk_config("plain")
    source_files = source_files or [audio_file]
    resolved_model = resolve_transcription_model_name("plain", timing_stats, model_name)
    log_transcribe_trace(
        "transcribe_chunk",
        mode="plain",
        model_name=resolved_model,
        audio_path=audio_file,
        chunk_config=chunk_config,
        retry_wrapper=True,
        retry_depth=retry_depth,
    )

    try:
        transcription = call_openai_transcription(
            audio_file=audio_file,
            mode="plain",
            chunk_config=chunk_config,
            source_files=source_files,
            retry_depth=retry_depth,
            timing_stats=timing_stats,
            model_name=resolved_model,
        )
        return extract_transcript_text(transcription)
    except Exception as exc:
        if is_input_too_large_error(exc):
            return retry_plain_chunk_after_input_too_large(
                audio_file=audio_file,
                chunk_config=chunk_config,
                retry_depth=retry_depth,
                source_files=source_files,
                original_error=exc,
                timing_stats=timing_stats,
                model_name=resolved_model,
            )
        raise RuntimeError(f"Audio chunk transcription failed for {audio_file}: {exc}") from exc


def prepare_audio_files(
    audio_files: Path | list[Path],
    mode: Literal["plain", "diarized"] = "plain",
    model_name: str | None = None,
) -> list[Path]:
    """오디오 입력을 검증하고 API 크기 제한을 넘는 파일을 분할합니다."""
    preparation_started_at = time.perf_counter()
    resolved_model = model_name or resolve_transcription_model_name(mode)
    log_transcribe_trace(
        "prepare_audio_files",
        mode=mode,
        model_name=resolved_model,
        audio_path=audio_files if isinstance(audio_files, Path) else None,
        chunk_config=get_audio_chunk_config(mode),
    )
    log_trace_event(
        "audio_preparation_start",
        mode=mode,
        path=audio_files if isinstance(audio_files, Path) else "multiple",
        chunk_duration_seconds=get_audio_chunk_config(mode).duration_seconds,
        chunk_overlap_seconds=get_audio_chunk_config(mode).overlap_seconds,
    )
    # 여러 파일을 처리하다 중간 실패해도 이미 생성된 임시 청크를 정리해야 합니다.
    prepared_files: list[Path] = []
    generated_temp_files: list[Path] = []

    try:
        original_files = normalize_audio_files(audio_files)

        for audio_file in original_files:
            # split_audio_if_needed가 원본 또는 청크 목록을 반환합니다.
            ensure_audio_file(audio_file)
            splitting_started_at = time.perf_counter()
            log_trace_event("chunk_splitting_start", mode=mode, source=audio_file)
            split_files = split_audio_if_needed(audio_file, chunk_config=get_audio_chunk_config(mode))
            log_trace_event(
                "chunk_splitting_complete",
                mode=mode,
                source=audio_file,
                chunk_count=len(split_files),
                elapsed_seconds=time.perf_counter() - splitting_started_at,
            )
            prepared_files.extend(split_files)
            generated_temp_files.extend(file for file in split_files if file not in original_files)
        log_trace_event(
            "audio_preparation_end",
            mode=mode,
            prepared_count=len(prepared_files),
            elapsed_seconds=time.perf_counter() - preparation_started_at,
        )
        return prepared_files
    except Exception as exc:
        cleanup_temp_files(generated_temp_files)
        raise RuntimeError(f"Audio preparation failed: {exc}") from exc


def normalize_audio_files(audio_files: Path | list[Path]) -> list[Path]:
    """단일 오디오 경로나 경로 목록을 Path 리스트로 정규화합니다."""
    # 이후 로직은 항상 리스트 기준으로 순회하도록 입력 형태를 통일합니다.
    if isinstance(audio_files, Path):
        return [audio_files]
    return audio_files


def normalize_speaker_label(speaker: object) -> str:
    """provider별 speaker 표기를 내부 표시용 라벨로 정규화합니다."""
    speaker_text = "" if speaker is None else str(speaker).strip()
    if not speaker_text:
        return "Unknown"

    speaker_match = re.fullmatch(r"speaker[\s_-]*(?P<number>\d+)", speaker_text, flags=re.IGNORECASE)
    if speaker_match:
        return f"Speaker {int(speaker_match.group('number'))}"
    return speaker_text


def seconds_to_ms(value: object) -> int | None:
    """초 단위 timestamp를 ms 정수로 변환합니다."""
    if value is None:
        return None
    try:
        return int(round(float(value) * 1000))
    except (TypeError, ValueError):
        return None


def diarized_segments_to_utterances(segments: list[dict[str, Any]]) -> list[TranscriptUtterance]:
    """diarized STT segment payload를 내부 TranscriptUtterance 목록으로 변환합니다."""
    utterances: list[TranscriptUtterance] = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue

        speaker = normalize_speaker_label(segment.get("speaker"))
        utterance_id = f"u_{len(utterances) + 1:04d}"
        raw_line = f"{speaker}: {text}"
        utterances.append(
            TranscriptUtterance(
                utterance_id=utterance_id,
                speaker=speaker,
                text=text,
                index=len(utterances),
                raw_line=raw_line,
                start_ms=seconds_to_ms(segment.get("start")),
                end_ms=seconds_to_ms(segment.get("end")),
            )
        )
    return utterances


def diarized_segments_to_normalized_transcript(segments: list[dict[str, Any]]) -> NormalizedTranscript:
    """diarized STT segment payload를 speaker-aware NormalizedTranscript로 변환합니다."""
    utterances = diarized_segments_to_utterances(segments)
    text = "\n".join(utterance.raw_line for utterance in utterances)
    return NormalizedTranscript(utterances=utterances, text=text, meeting_date="")


def call_diarized_transcription_provider(
    audio_file: Path,
    chunk_config: AudioChunkConfig | None = None,
    source_files: list[Path] | None = None,
    timing_stats: TranscriptionTimingStats | None = None,
    model_name: str | None = None,
) -> list[dict[str, Any]]:
    """diarization-capable STT provider를 호출하고 segment payload를 반환합니다."""
    return call_diarized_transcription_provider_with_retry(
        audio_file=audio_file,
        chunk_config=chunk_config or get_audio_chunk_config("diarized"),
        source_files=source_files or [audio_file],
        timing_stats=timing_stats,
        model_name=model_name,
    )


def call_diarized_transcription_provider_with_retry(
    audio_file: Path,
    chunk_config: AudioChunkConfig,
    retry_depth: int = 0,
    source_files: list[Path] | None = None,
    timing_stats: TranscriptionTimingStats | None = None,
    model_name: str | None = None,
) -> list[dict[str, Any]]:
    """input_too_large 오류가 나면 해당 diarized 청크를 더 작게 나눠 재시도합니다."""
    source_files = source_files or [audio_file]
    resolved_model = resolve_transcription_model_name("diarized", timing_stats, model_name)
    log_transcribe_trace(
        "call_diarized_transcription_provider_with_retry",
        mode="diarized",
        model_name=resolved_model,
        audio_path=audio_file,
        chunk_config=chunk_config,
        retry_wrapper=True,
        retry_depth=retry_depth,
    )

    try:
        return call_diarized_transcription_provider_once(
            audio_file,
            chunk_config=chunk_config,
            source_files=source_files,
            retry_depth=retry_depth,
            timing_stats=timing_stats,
            model_name=resolved_model,
        )
    except Exception as exc:
        if is_input_too_large_error(exc):
            return retry_diarized_chunk_after_input_too_large(
                audio_file=audio_file,
                chunk_config=chunk_config,
                retry_depth=retry_depth,
                source_files=source_files,
                original_error=exc,
                timing_stats=timing_stats,
                model_name=resolved_model,
            )
        raise RuntimeError(f"Diarized transcription provider failed for {audio_file}: {exc}") from exc


def call_diarized_transcription_provider_once(
    audio_file: Path,
    chunk_config: AudioChunkConfig | None = None,
    source_files: list[Path] | None = None,
    retry_depth: int = 0,
    timing_stats: TranscriptionTimingStats | None = None,
    model_name: str | None = None,
) -> list[dict[str, Any]]:
    """diarization-capable STT provider를 한 번 호출합니다."""
    chunk_config = chunk_config or get_audio_chunk_config("diarized")
    source_files = source_files or [audio_file]
    resolved_model = resolve_transcription_model_name("diarized", timing_stats, model_name)
    log_transcribe_trace(
        "call_diarized_transcription_provider_once",
        mode="diarized",
        model_name=resolved_model,
        audio_path=audio_file,
        chunk_config=chunk_config,
        retry_wrapper=False,
        retry_depth=retry_depth,
    )
    transcription = call_openai_transcription(
        audio_file=audio_file,
        mode="diarized",
        chunk_config=chunk_config,
        source_files=source_files,
        retry_depth=retry_depth,
        timing_stats=timing_stats,
        model_name=resolved_model,
    )
    return extract_diarized_segments(transcription)


def call_openai_transcription(
    audio_file: Path,
    mode: Literal["plain", "diarized"],
    chunk_config: AudioChunkConfig,
    source_files: list[Path],
    retry_depth: int = 0,
    timing_stats: TranscriptionTimingStats | None = None,
    model_name: str | None = None,
) -> object:
    """모든 OpenAI STT 호출이 통과하는 단일 래퍼입니다."""
    resolved_model = resolve_transcription_model_name(mode, timing_stats, model_name)
    log_transcribe_trace(
        "call_openai_transcription",
        mode=mode,
        model_name=resolved_model,
        audio_path=audio_file,
        chunk_config=chunk_config,
        retry_wrapper=True,
        retry_depth=retry_depth,
    )
    ensure_audio_file(audio_file)
    diagnostic = validate_chunk_before_transcription(
        audio_file,
        mode,
        chunk_config,
        source_files,
        model_name=resolved_model,
    )
    log_trace_event(
        "sending_to_openai",
        path=audio_file,
        duration_seconds=format_optional_seconds(diagnostic.duration_seconds),
        size_mb=diagnostic.size_mb,
        model=resolved_model,
        mode=mode,
        retry_depth=retry_depth,
    )
    client = create_openai_client()
    transcription_kwargs: dict[str, Any] = {
        "model": resolved_model,
        "language": get_transcription_language(),
    }
    if mode == "diarized":
        transcription_kwargs.update(
            {
                "chunking_strategy": "auto",
                "response_format": "diarized_json",
            }
        )

    request_started_at = time.perf_counter()
    log_trace_event(
        "openai_request_start",
        mode=mode,
        model=resolved_model,
        path=audio_file,
        retry_depth=retry_depth,
    )
    try:
        with audio_file.open("rb") as file_data:
            transcription = client.audio.transcriptions.create(file=file_data, **transcription_kwargs)
    except Exception as exc:
        log_trace_event(
            "openai_request_failed",
            mode=mode,
            model=resolved_model,
            path=audio_file,
            retry_depth=retry_depth,
            elapsed_seconds=time.perf_counter() - request_started_at,
            error=exc,
        )
        raise

    log_trace_event(
        "openai_request_complete",
        mode=mode,
        model=resolved_model,
        path=audio_file,
        retry_depth=retry_depth,
        elapsed_seconds=time.perf_counter() - request_started_at,
    )
    return transcription


def extract_diarized_segments(transcription: object) -> list[dict[str, Any]]:
    """provider 응답에서 diarized segment 목록을 추출합니다."""
    if isinstance(transcription, list):
        return normalize_diarized_segments(transcription)

    if isinstance(transcription, dict):
        for key in ("diarized_segments", "segments"):
            value = transcription.get(key)
            if isinstance(value, list):
                return normalize_diarized_segments(value)

    for attr_name in ("diarized_segments", "segments"):
        value = getattr(transcription, attr_name, None)
        if isinstance(value, list):
            return normalize_diarized_segments(value)

    raise ValueError("Diarized transcription response did not include segments.")


def normalize_diarized_segments(segments: list[object]) -> list[dict[str, Any]]:
    """provider별 segment 객체를 speaker/text/start/end dict로 정규화합니다."""
    normalized_segments: list[dict[str, Any]] = []
    for segment in segments:
        normalized_segment = normalize_diarized_segment(segment)
        if normalized_segment is not None:
            normalized_segments.append(normalized_segment)
    return normalized_segments


def normalize_diarized_segment(segment: object) -> dict[str, Any] | None:
    """단일 diarized segment에서 필요한 필드를 추출합니다."""
    text = get_first_segment_value(segment, ("text", "transcript", "content"))
    if text is None:
        return None

    normalized_segment = {
        "speaker": get_first_segment_value(segment, ("speaker", "speaker_label", "speaker_id")),
        "text": text,
    }
    start = get_first_segment_value(segment, ("start", "start_time", "start_seconds"))
    end = get_first_segment_value(segment, ("end", "end_time", "end_seconds"))
    if start is not None:
        normalized_segment["start"] = start
    if end is not None:
        normalized_segment["end"] = end
    return normalized_segment


def get_first_segment_value(segment: object, keys: tuple[str, ...]) -> object:
    """dict 또는 객체 segment에서 첫 번째 사용 가능한 값을 반환합니다."""
    for key in keys:
        if isinstance(segment, dict) and key in segment:
            return segment[key]
        value = getattr(segment, key, None)
        if value is not None:
            return value
    return None


def create_openai_client() -> OpenAI:
    """환경 변수의 API 키를 사용해 OpenAI API client를 만듭니다."""
    try:
        # API 키는 코드에 하드코딩하지 않고 .env 또는 서버 환경 변수에서만 읽습니다.
        load_dotenv()
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is missing. Add it to your .env file.")
        return OpenAI()
    except Exception as exc:
        raise RuntimeError(f"OpenAI client initialization failed: {exc}") from exc


def get_transcription_model() -> str:
    """환경 변수로 설정된 STT 모델명을 반환합니다."""
    return os.getenv("OPENAI_TRANSCRIPTION_MODEL", DEFAULT_TRANSCRIPTION_MODEL)


def get_diarized_transcription_model() -> str:
    """환경 변수로 설정된 diarization STT 모델명을 반환합니다."""
    return os.getenv("OPENAI_DIARIZED_TRANSCRIPTION_MODEL", DEFAULT_DIARIZED_TRANSCRIPTION_MODEL)


def get_transcription_language() -> str:
    """환경 변수로 설정된 STT 언어 힌트를 반환합니다."""
    return os.getenv("OPENAI_TRANSCRIPTION_LANGUAGE", DEFAULT_TRANSCRIPTION_LANGUAGE)


def get_plain_transcription_concurrency() -> int:
    """plain STT worker 동시성 설정을 안전한 범위로 제한해 반환합니다."""
    raw_value = os.getenv("PLAIN_TRANSCRIPTION_CONCURRENCY")
    if raw_value is None:
        return DEFAULT_PLAIN_TRANSCRIPTION_CONCURRENCY
    try:
        parsed_value = int(raw_value)
    except ValueError as exc:
        raise ValueError("PLAIN_TRANSCRIPTION_CONCURRENCY must be an integer.") from exc
    return min(max(parsed_value, 1), MAX_PLAIN_TRANSCRIPTION_CONCURRENCY)


def get_audio_chunk_config(mode: Literal["plain", "diarized"]) -> AudioChunkConfig:
    """전사 모드에 맞는 오디오 청크 설정을 반환합니다."""
    if mode == "plain":
        return AudioChunkConfig(
            duration_seconds=get_plain_chunk_duration_seconds(),
            overlap_seconds=get_plain_chunk_overlap_seconds(),
        )
    if mode == "diarized":
        return AudioChunkConfig(
            duration_seconds=get_diarized_chunk_duration_seconds(),
            overlap_seconds=get_diarized_chunk_overlap_seconds(),
        )
    raise ValueError(f"Unsupported transcription mode: {mode}")


def get_plain_chunk_duration_seconds() -> int:
    """plain STT 전용 청크 길이를 초 단위로 반환합니다."""
    return get_positive_int_env(
        "PLAIN_CHUNK_DURATION_SECONDS",
        DEFAULT_PLAIN_CHUNK_DURATION_SECONDS,
    )


def get_plain_chunk_overlap_seconds() -> int:
    """plain STT 전용 청크 overlap을 초 단위로 반환합니다."""
    return get_non_negative_int_env(
        "PLAIN_CHUNK_OVERLAP_SECONDS",
        DEFAULT_PLAIN_CHUNK_OVERLAP_SECONDS,
    )


def get_diarized_chunk_duration_seconds() -> int:
    """diarized STT 전용 청크 길이를 초 단위로 반환합니다."""
    return get_positive_int_env(
        "DIARIZED_CHUNK_DURATION_SECONDS",
        DEFAULT_DIARIZED_CHUNK_DURATION_SECONDS,
    )


def get_diarized_chunk_overlap_seconds() -> int:
    """diarized STT 전용 청크 overlap을 초 단위로 반환합니다."""
    return get_non_negative_int_env(
        "DIARIZED_CHUNK_OVERLAP_SECONDS",
        DEFAULT_DIARIZED_CHUNK_OVERLAP_SECONDS,
    )


def get_positive_int_env(name: str, default: int) -> int:
    """양수 정수 환경 변수를 읽고 잘못된 값은 명확히 거절합니다."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return parsed


def get_non_negative_int_env(name: str, default: int) -> int:
    """0 이상 정수 환경 변수를 읽고 잘못된 값은 명확히 거절합니다."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be zero or greater.")
    return parsed


def build_audio_chunk_diagnostic(audio_file: Path) -> AudioChunkDiagnostic:
    """전사 전 확인용 오디오 청크 진단 정보를 만듭니다."""
    ensure_audio_file(audio_file)
    return AudioChunkDiagnostic(
        path=audio_file,
        duration_seconds=get_audio_duration_seconds(audio_file),
        size_mb=get_file_size_mb(audio_file),
    )


def get_audio_duration_seconds(audio_file: Path) -> float | None:
    """pydub/ffprobe 경로로 오디오 길이를 초 단위로 읽습니다."""
    try:
        audio_format = get_audio_format(audio_file)
        audio = AudioSegment.from_file(audio_file, format=audio_format)
        return len(audio) / 1000
    except Exception as exc:
        logger.warning("audio_duration unavailable path=%s error=%s", audio_file, exc)
        return None


def get_file_size_mb(audio_file: Path) -> float:
    """파일 크기를 MB 단위로 반환합니다."""
    return audio_file.stat().st_size / (1024 * 1024)


def log_transcription_run_diagnostics(
    mode: Literal["plain", "diarized"],
    model_name: str,
    source_files: list[Path],
    chunk_files: list[Path],
    chunk_config: AudioChunkConfig,
) -> None:
    """전사 실행 전에 source와 chunk의 실제 duration/size를 로그로 남깁니다."""
    logger.warning(
        "%s function=log_transcription_run_diagnostics mode=%s model=%s "
        "chunk_duration_seconds=%s chunk_overlap_seconds=%s chunk_count=%s",
        get_trace_prefix(),
        mode,
        model_name,
        chunk_config.duration_seconds,
        chunk_config.overlap_seconds,
        len(chunk_files),
    )

    for source_file in source_files:
        diagnostic = build_audio_chunk_diagnostic(source_file)
        logger.warning(
            "%s transcription_source path=%s duration_seconds=%s size_mb=%.3f",
            get_trace_prefix(),
            diagnostic.path,
            format_optional_seconds(diagnostic.duration_seconds),
            diagnostic.size_mb,
        )

    for chunk_index, chunk_file in enumerate(chunk_files, start=1):
        diagnostic = build_audio_chunk_diagnostic(chunk_file)
        logger.warning(
            "%s transcription_chunk index=%s path=%s duration_seconds=%s size_mb=%.3f",
            get_trace_prefix(),
            chunk_index,
            diagnostic.path,
            format_optional_seconds(diagnostic.duration_seconds),
            diagnostic.size_mb,
        )


def validate_chunk_before_transcription(
    audio_file: Path,
    mode: Literal["plain", "diarized"],
    chunk_config: AudioChunkConfig,
    source_files: list[Path],
    model_name: str | None = None,
) -> AudioChunkDiagnostic:
    """OpenAI 호출 직전에 chunk duration/size가 의심스러운지 확인합니다."""
    diagnostic = build_audio_chunk_diagnostic(audio_file)
    resolved_model = model_name or resolve_transcription_model_name(mode)
    log_transcribe_trace(
        "validate_chunk_before_transcription",
        mode=mode,
        model_name=resolved_model,
        audio_path=audio_file,
        chunk_config=chunk_config,
        retry_wrapper=False,
        diagnostic=diagnostic,
    )
    logger.warning(
        "%s transcription_chunk_send mode=%s model=%s path=%s duration_seconds=%s size_mb=%.3f "
        "chunk_duration_seconds=%s chunk_overlap_seconds=%s",
        get_trace_prefix(),
        mode,
        resolved_model,
        audio_file,
        format_optional_seconds(diagnostic.duration_seconds),
        diagnostic.size_mb,
        chunk_config.duration_seconds,
        chunk_config.overlap_seconds,
    )

    if chunk_config.duration_seconds is not None and diagnostic.duration_seconds is not None:
        max_duration_seconds = chunk_config.duration_seconds + CHUNK_DURATION_TOLERANCE_SECONDS
        if diagnostic.duration_seconds > max_duration_seconds:
            raise RuntimeError(
                f"Prepared {mode} audio chunk is too long before transcription: "
                f"{audio_file} duration={diagnostic.duration_seconds:.1f}s "
                f"limit={max_duration_seconds:.1f}s"
            )

    warn_if_chunk_size_is_close_to_source(diagnostic, source_files)
    return diagnostic


def warn_if_chunk_size_is_close_to_source(diagnostic: AudioChunkDiagnostic, source_files: list[Path]) -> None:
    """청크 크기가 원본과 거의 같으면 분할 실패 가능성을 경고합니다."""
    for source_file in source_files:
        if diagnostic.path == source_file or not source_file.exists():
            continue

        source_size_mb = get_file_size_mb(source_file)
        if source_size_mb <= 0:
            continue

        if diagnostic.size_mb >= source_size_mb * 0.9:
            logger.warning(
                "transcription_chunk_size_suspicious chunk_path=%s chunk_size_mb=%.3f source_path=%s source_size_mb=%.3f",
                diagnostic.path,
                diagnostic.size_mb,
                source_file,
                source_size_mb,
            )


def is_input_too_large_error(exc: Exception) -> bool:
    """OpenAI input-too-large 계열 오류인지 판별합니다."""
    values = [value.lower() for value in iter_exception_signal_values(exc)]
    has_input_too_large_code = any("input_too_large" in value for value in values)
    has_known_message = any("total number of tokens in instructions + audio is too large" in value for value in values)
    has_status_400 = any(value == "400" for value in values)
    has_audio_too_large_message = any("too large" in value and "audio" in value for value in values)
    return has_input_too_large_code or has_known_message or (has_status_400 and has_audio_too_large_message)


def iter_exception_signal_values(value: object, depth: int = 0, seen: set[int] | None = None):
    """SDK 예외 객체에서 코드/status/message 후보 값을 안전하게 순회합니다."""
    if value is None or depth > 5:
        return

    seen = seen or set()
    value_id = id(value)
    if value_id in seen:
        return
    seen.add(value_id)

    if isinstance(value, (str, int, float, bool)):
        yield str(value)
        return

    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from iter_exception_signal_values(item, depth + 1, seen)
        return

    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from iter_exception_signal_values(item, depth + 1, seen)
        return

    yield str(value)
    for attr_name in ("status_code", "status", "code", "type", "message", "body", "error", "response"):
        try:
            attr_value = getattr(value, attr_name, None)
        except Exception:
            continue
        if attr_value is not None and attr_value is not value:
            yield from iter_exception_signal_values(attr_value, depth + 1, seen)


def retry_plain_chunk_after_input_too_large(
    audio_file: Path,
    chunk_config: AudioChunkConfig,
    retry_depth: int,
    source_files: list[Path],
    original_error: Exception,
    timing_stats: TranscriptionTimingStats | None = None,
    model_name: str | None = None,
) -> str:
    """plain chunk가 너무 크면 더 작은 청크로 나눠 전사합니다."""
    retry_started_at = time.perf_counter()
    if timing_stats is not None:
        timing_stats.record_retry()
    resolved_model = resolve_transcription_model_name("plain", timing_stats, model_name)
    log_transcribe_trace(
        "retry_plain_chunk_after_input_too_large",
        mode="plain",
        model_name=resolved_model,
        audio_path=audio_file,
        chunk_config=chunk_config,
        retry_wrapper=True,
        retry_depth=retry_depth,
    )
    log_trace_event("retry_start", mode="plain", path=audio_file, retry_depth=retry_depth + 1)
    retry_files = split_chunk_for_input_too_large(
        audio_file,
        "plain",
        chunk_config,
        retry_depth,
        original_error,
        model_name=resolved_model,
    )
    generated_files = [retry_file for retry_file in retry_files if retry_file != audio_file]

    try:
        transcripts = [
            transcribe_chunk(
                retry_file,
                chunk_config=build_retry_chunk_config(chunk_config),
                retry_depth=retry_depth + 1,
                source_files=source_files,
                timing_stats=timing_stats,
                model_name=resolved_model,
            )
            for retry_file in retry_files
        ]
        retry_transcript = "\n\n".join(transcript.strip() for transcript in transcripts if transcript.strip())
        log_trace_event(
            "retry_complete",
            mode="plain",
            path=audio_file,
            retry_depth=retry_depth + 1,
            elapsed_seconds=time.perf_counter() - retry_started_at,
            retry_chunk_count=len(retry_files),
        )
        return retry_transcript
    finally:
        cleanup_temp_files(generated_files)


def retry_diarized_chunk_after_input_too_large(
    audio_file: Path,
    chunk_config: AudioChunkConfig,
    retry_depth: int,
    source_files: list[Path],
    original_error: Exception,
    timing_stats: TranscriptionTimingStats | None = None,
    model_name: str | None = None,
) -> list[dict[str, Any]]:
    """diarized chunk가 너무 크면 더 작은 청크로 나눠 재시도합니다."""
    retry_started_at = time.perf_counter()
    if timing_stats is not None:
        timing_stats.record_retry()
    resolved_model = resolve_transcription_model_name("diarized", timing_stats, model_name)
    log_transcribe_trace(
        "retry_diarized_chunk_after_input_too_large",
        mode="diarized",
        model_name=resolved_model,
        audio_path=audio_file,
        chunk_config=chunk_config,
        retry_wrapper=True,
        retry_depth=retry_depth,
    )
    log_trace_event("retry_start", mode="diarized", path=audio_file, retry_depth=retry_depth + 1)
    retry_files = split_chunk_for_input_too_large(
        audio_file,
        "diarized",
        chunk_config,
        retry_depth,
        original_error,
        model_name=resolved_model,
    )
    generated_files = [retry_file for retry_file in retry_files if retry_file != audio_file]

    try:
        segments: list[dict[str, Any]] = []
        for retry_file in retry_files:
            segments.extend(
                call_diarized_transcription_provider_with_retry(
                    retry_file,
                    chunk_config=build_retry_chunk_config(chunk_config),
                    retry_depth=retry_depth + 1,
                    source_files=source_files,
                    timing_stats=timing_stats,
                    model_name=resolved_model,
                )
            )
        log_trace_event(
            "retry_complete",
            mode="diarized",
            path=audio_file,
            retry_depth=retry_depth + 1,
            elapsed_seconds=time.perf_counter() - retry_started_at,
            retry_chunk_count=len(retry_files),
        )
        return segments
    finally:
        cleanup_temp_files(generated_files)


def split_chunk_for_input_too_large(
    audio_file: Path,
    mode: Literal["plain", "diarized"],
    chunk_config: AudioChunkConfig,
    retry_depth: int,
    original_error: Exception,
    model_name: str | None = None,
) -> list[Path]:
    """input_too_large chunk를 더 작은 청크로 분할합니다."""
    resolved_model = model_name or resolve_transcription_model_name(mode)
    log_transcribe_trace(
        "split_chunk_for_input_too_large",
        mode=mode,
        model_name=resolved_model,
        audio_path=audio_file,
        chunk_config=chunk_config,
        retry_wrapper=True,
        retry_depth=retry_depth,
    )
    if retry_depth >= INPUT_TOO_LARGE_MAX_RETRY_DEPTH:
        raise RuntimeError(
            f"{mode} transcription chunk is still too large after {retry_depth} retries: {audio_file}: {original_error}"
        ) from original_error

    retry_config = build_retry_chunk_config(chunk_config)
    logger.warning(
        "%s transcription_input_too_large_retry mode=%s path=%s retry_depth=%s next_chunk_duration_seconds=%s error=%s",
        get_trace_prefix(),
        mode,
        audio_file,
        retry_depth + 1,
        retry_config.duration_seconds,
        original_error,
    )
    retry_files = split_audio_if_needed(audio_file, chunk_config=retry_config)

    if retry_files == [audio_file]:
        raise RuntimeError(
            f"{mode} transcription retry could not split oversized chunk further: {audio_file}: {original_error}"
        ) from original_error

    logger.warning(
        "%s transcription_input_too_large_retry_split mode=%s original_path=%s retry_chunk_count=%s",
        get_trace_prefix(),
        mode,
        audio_file,
        len(retry_files),
    )
    return retry_files


def build_retry_chunk_config(chunk_config: AudioChunkConfig) -> AudioChunkConfig:
    """재시도용으로 더 작은 chunk 설정을 만듭니다."""
    current_duration_seconds = chunk_config.duration_seconds or DEFAULT_DIARIZED_CHUNK_DURATION_SECONDS
    retry_duration_seconds = max(current_duration_seconds // 2, MIN_RETRY_CHUNK_DURATION_SECONDS)
    return AudioChunkConfig(duration_seconds=retry_duration_seconds, overlap_seconds=0)


def format_optional_seconds(value: float | None) -> str:
    """로그용 optional 초 값을 문자열로 변환합니다."""
    if value is None:
        return "unknown"
    return f"{value:.1f}"


def extract_transcript_text(transcription: object) -> str:
    """OpenAI transcription 응답에서 전사문 텍스트를 추출합니다."""
    # SDK 버전이나 테스트 mock 형태에 따라 문자열/객체/dict 응답을 모두 허용합니다.
    if isinstance(transcription, str):
        return transcription

    text = getattr(transcription, "text", None)
    if isinstance(text, str):
        return text

    if isinstance(transcription, dict) and isinstance(transcription.get("text"), str):
        return transcription["text"]

    raise ValueError("OpenAI transcription response did not include text.")
