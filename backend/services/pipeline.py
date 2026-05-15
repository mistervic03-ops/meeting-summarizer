"""기존 STT와 요약 함수를 FastAPI 작업 흐름에서 호출합니다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from summarize import summarize_transcript
from transcribe import transcribe_audio

try:
    from backend.storage import cleanup_job_files, mark_job_completed, mark_job_failed, mark_job_processing
except ModuleNotFoundError:
    # `cd backend` 기준 uvicorn 실행에서 로컬 패키지 경로를 사용합니다.
    from storage import cleanup_job_files, mark_job_completed, mark_job_failed, mark_job_processing


def run_meeting_pipeline(job_id: str, audio_path: Path, context: str = "") -> None:
    """오디오 파일을 STT 처리한 뒤 회의록을 생성하고 작업 저장소에 기록합니다."""
    mark_job_processing(job_id)

    try:
        transcript = transcribe_audio(audio_path)
        summary = summarize_transcript(transcript, context=context)
        mark_job_completed(
            job_id,
            transcript=transcript,
            minutes=as_text(summary.get("minutes")),
            action_items=as_dict_list(summary.get("action_items")),
            summary_facts=as_text_list(summary.get("summary_facts")),
            decisions=as_dict_list(summary.get("decisions")),
            speaker_highlights=as_text_list(summary.get("speaker_highlights")),
            warnings=as_text_list(summary.get("warnings")),
        )
    except Exception as exc:
        mark_job_failed(job_id, f"회의록 생성 중 오류가 발생했습니다: {exc}")
    finally:
        # 원본 업로드 파일은 처리 후 남기지 않아 API 서버 임시 저장소를 깨끗하게 유지합니다.
        cleanup_job_files(job_id)


def as_text(value: Any) -> str:
    """Return a display-safe string from an arbitrary summary value."""
    return value if isinstance(value, str) else ""


def as_text_list(value: Any) -> list[str]:
    """Return only string items from an arbitrary summary list."""
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def as_dict_list(value: Any) -> list[dict[str, Any]]:
    """Return only dictionary items from an arbitrary summary list."""
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
