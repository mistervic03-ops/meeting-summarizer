"""기존 STT와 요약 함수를 FastAPI 작업 흐름에서 호출합니다."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from summarize import summarize_transcript
from summarization.models import NormalizedTranscript
from summarization.normalization import structured_transcript_payload_to_normalized_transcript
from transcribe import TRANSCRIBE_RUNTIME_VERSION, get_trace_prefix, transcribe_audio

logger = logging.getLogger("backend.pipeline")

try:
    from backend.db import get_db_connection
    from backend.storage import (
        cleanup_job_files,
        mark_job_completed,
        mark_job_failed,
        mark_job_chunk_progress,
        mark_job_processing,
        mark_job_progress,
        mark_job_transcribed,
        save_text_artifacts,
        set_job_meeting_type,
    )
except ModuleNotFoundError:
    # `cd backend` 기준 uvicorn 실행에서 로컬 패키지 경로를 사용합니다.
    from db import get_db_connection
    from storage import cleanup_job_files, mark_job_completed, mark_job_failed, mark_job_chunk_progress, mark_job_processing, mark_job_progress, mark_job_transcribed, save_text_artifacts, set_job_meeting_type


def run_transcription_pipeline(
    job_id: str,
    audio_path: Path,
    meeting_type: str = "general",
    stt_provider: str | None = None,
) -> None:
    """오디오 파일을 STT 처리하고 transcript 검토 화면에서 사용할 결과를 저장합니다."""
    set_job_meeting_type(job_id, meeting_type)
    logger.warning(
        "%s function=run_transcription_pipeline mode=plain audio_path=%s runtime_version=%s",
        get_trace_prefix(),
        audio_path,
        TRANSCRIBE_RUNTIME_VERSION,
    )
    mark_job_processing(job_id)

    try:
        mark_job_progress(job_id, 15, "음성 변환", "음성을 텍스트로 변환하는 중입니다.")
        stt_started_at = time.perf_counter()
        transcript = transcribe_audio(
            audio_path,
            progress_callback=build_chunk_progress_callback(job_id),
            stt_provider=stt_provider,
        )
        stt_seconds = time.perf_counter() - stt_started_at
        mark_job_progress(job_id, 95, "Transcript 정리", "검토 화면에 표시할 transcript를 준비하고 있습니다.", stt_seconds=stt_seconds)
        mark_job_transcribed(job_id, transcript)
        transcript_path, summary_path = save_text_artifacts(job_id, transcript, "")
        update_meeting_artifacts(job_id, "transcript_ready", transcript_path, summary_path)
    except Exception as exc:
        mark_job_failed(job_id, f"음성 변환 중 오류가 발생했습니다: {exc}")
        mark_meeting_failed(job_id, str(exc))
    finally:
        # 원본 업로드 파일은 처리 후 남기지 않아 API 서버 임시 저장소를 깨끗하게 유지합니다.
        cleanup_job_files(job_id)


def run_transcript_summary_pipeline(
    job_id: str,
    transcript: str,
    context: str = "",
    structured_transcript: dict[str, Any] | None = None,
    meeting_type: str = "general",
    meeting_record_id: str | None = None,
) -> None:
    """검토된 transcript를 기준으로 회의록을 생성하고 작업 저장소에 기록합니다."""
    target_meeting_id = meeting_record_id or job_id
    mark_job_processing(job_id)
    set_job_meeting_type(job_id, meeting_type)

    try:
        mark_job_progress(job_id, 55, "검토 완료", "수정된 transcript를 회의록 생성 기준으로 사용합니다.")
        mark_job_progress(job_id, 70, "회의록 작성", "회의 내용을 요약하고 액션 아이템을 추출하는 중입니다.")
        summary_started_at = time.perf_counter()
        normalized_transcript = build_normalized_transcript_from_structured_payload(structured_transcript)
        if normalized_transcript is None:
            summary = summarize_transcript(transcript, context=context, meeting_type=meeting_type)
        else:
            summary = summarize_transcript(
                transcript,
                context=context,
                normalized_transcript=normalized_transcript,
                meeting_type=meeting_type,
            )
        summary_seconds = time.perf_counter() - summary_started_at
        mark_job_progress(job_id, 90, "결과 정리", "결과 화면에 표시할 회의록을 정리하고 있습니다.", summary_seconds=summary_seconds)
        mark_job_completed(job_id, transcript=transcript, summary=summary, structured_transcript=structured_transcript)
        transcript_path, summary_path = save_text_artifacts(job_id, transcript, get_summary_text(summary))
        update_meeting_artifacts(target_meeting_id, "completed", transcript_path, summary_path)
    except Exception as exc:
        mark_job_failed(job_id, f"회의록 생성 중 오류가 발생했습니다: {exc}")
        if not mark_meeting_failed(target_meeting_id, str(exc)):
            logger.warning(
                "summary_meeting_failure_update_missed job_id=%s meeting_record_id=%s error=%s",
                job_id,
                target_meeting_id,
                exc,
            )


def get_summary_text(summary: dict[str, Any]) -> str:
    """요약 결과 dict에서 파일 저장용 회의록 텍스트를 꺼냅니다."""
    minutes = summary.get("minutes")
    return minutes if isinstance(minutes, str) else ""


def update_meeting_artifacts(job_id: str, status: str, transcript_path: Path, summary_path: Path) -> None:
    """영구 meeting row에 처리 상태와 artifact 경로를 반영합니다."""
    with get_db_connection() as connection:
        connection.execute(
            """
            UPDATE meetings
            SET status = ?, transcript_path = ?, summary_path = ?, error = NULL
            WHERE id = ?
            """,
            (status, str(transcript_path), str(summary_path), job_id),
        )


def mark_meeting_failed(job_id: str, error: str) -> bool:
    """영구 meeting row에 실패 상태와 에러 메시지를 저장합니다."""
    with get_db_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE meetings
            SET status = ?, error = ?
            WHERE id = ?
            """,
            ("failed", error, job_id),
        )
        return cursor.rowcount > 0


def build_normalized_transcript_from_structured_payload(structured_transcript: dict[str, Any] | None) -> NormalizedTranscript | None:
    """structured transcript payload가 유효하면 내부 NormalizedTranscript로 변환합니다."""
    if not structured_transcript:
        return None

    try:
        return structured_transcript_payload_to_normalized_transcript(structured_transcript)
    except ValueError:
        return None


def build_chunk_progress_callback(job_id: str) -> Callable[[int, int], None]:
    """plain STT 청크 진행률을 사용자용 job 상태로 반영하는 callback을 만듭니다."""

    def update_chunk_progress(completed_chunks: int, total_chunks: int) -> None:
        mark_job_chunk_progress(job_id, completed_chunks, total_chunks)

    return update_chunk_progress
