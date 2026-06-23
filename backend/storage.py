"""DB 없이 사용할 수 있는 로컬 임시 저장소와 인메모리 작업 저장소입니다."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from fastapi import UploadFile

from backend.schemas import JobStatus

UPLOAD_ROOT = Path(tempfile.gettempdir()) / "meeting_summarizer_api"
ARTIFACT_ROOT = Path("data") / "meetings"
JOBS: dict[str, "JobRecord"] = {}
JOBS_LOCK = RLock()


def utc_now() -> datetime:
    """작업 timestamp를 timezone-aware UTC 값으로 저장합니다."""
    return datetime.now(timezone.utc)


@dataclass
class PipelineResult:
    """STT와 회의록 생성 결과를 함께 보관합니다."""

    transcript: str
    minutes: str
    action_items: list[dict[str, Any]] = field(default_factory=list)
    summary_facts: list[str] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    speaker_highlights: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class JobRecord:
    """하나의 회의록 생성 작업 상태를 저장합니다."""

    id: str
    filename: str
    status: JobStatus = "pending"
    created_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None
    error: str | None = None
    result: PipelineResult | None = None
    progress: int = 0
    stage: str = "업로드 대기"
    message: str = "오디오 파일을 기다리고 있습니다."
    stt_seconds: float | None = None
    summary_seconds: float | None = None
    completed_chunks: int | None = None
    total_chunks: int | None = None
    context: str = ""
    meeting_type: str = "general"


def create_job(filename: str) -> JobRecord:
    """새 작업을 만들고 인메모리 저장소에 등록합니다."""
    job = JobRecord(id=uuid4().hex, filename=filename)
    with JOBS_LOCK:
        JOBS[job.id] = job
    get_job_dir(job.id).mkdir(parents=True, exist_ok=True)
    return job


def get_job(job_id: str) -> JobRecord | None:
    """작업 ID로 작업 상태를 조회합니다."""
    with JOBS_LOCK:
        return JOBS.get(job_id)


def get_job_status_snapshot(job_id: str) -> dict[str, Any] | None:
    """polling 응답에 필요한 작업 상태를 lock 안에서 snapshot으로 복사합니다."""
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        return {
            "job_id": job.id,
            "status": job.status,
            "filename": job.filename,
            "created_at": job.created_at,
            "completed_at": job.completed_at,
            "error": job.error,
            "progress": job.progress,
            "stage": job.stage,
            "message": job.message,
            "completed_chunks": job.completed_chunks,
            "total_chunks": job.total_chunks,
            "stt_seconds": job.stt_seconds,
            "summary_seconds": job.summary_seconds,
        }


def get_job_dir(job_id: str) -> Path:
    """작업별 임시 파일 저장 디렉터리 경로를 반환합니다."""
    return UPLOAD_ROOT / job_id


async def save_upload_file(job_id: str, upload_file: UploadFile) -> Path:
    """업로드 파일을 작업 임시 디렉터리에 저장하고 저장 경로를 반환합니다."""
    filename = Path(upload_file.filename or "uploaded_file").name
    target_path = get_job_dir(job_id) / filename

    with target_path.open("wb") as output_file:
        while chunk := await upload_file.read(1024 * 1024):
            output_file.write(chunk)

    await upload_file.close()
    return target_path


def save_text_artifacts(job_id: str, transcript: str, summary: str) -> tuple[Path, Path]:
    """작업별 transcript와 summary 텍스트 artifact를 data 디렉터리에 저장합니다."""
    artifact_dir = ARTIFACT_ROOT / job_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = artifact_dir / "transcript.txt"
    summary_path = artifact_dir / "summary.txt"

    transcript_path.write_text(transcript, encoding="utf-8")
    summary_path.write_text(summary, encoding="utf-8")
    return transcript_path, summary_path


def mark_job_processing(job_id: str) -> None:
    """작업 상태를 처리 중으로 변경합니다."""
    with JOBS_LOCK:
        job = require_job(job_id)
        job.status = "processing"
        job.error = None
        job.progress = 10
        job.stage = "파일 준비"
        job.message = "오디오 파일을 확인하고 있습니다."
        job.completed_chunks = None
        job.total_chunks = None


def set_job_context(job_id: str, context: str) -> None:
    """작업에서 사용할 팀 컨텍스트를 저장합니다."""
    with JOBS_LOCK:
        require_job(job_id).context = context


def set_job_meeting_type(job_id: str, meeting_type: str) -> None:
    """작업에서 사용할 회의 유형을 저장합니다."""
    with JOBS_LOCK:
        require_job(job_id).meeting_type = meeting_type or "general"


def mark_job_progress(
    job_id: str,
    progress: int,
    stage: str,
    message: str,
    stt_seconds: float | None = None,
    summary_seconds: float | None = None,
) -> None:
    """작업의 현재 진행률과 사용자에게 보여줄 상태 메시지를 저장합니다."""
    with JOBS_LOCK:
        job = require_job(job_id)
        job.progress = max(job.progress, max(0, min(100, progress)))
        job.stage = stage
        job.message = message

        if stt_seconds is not None:
            job.stt_seconds = stt_seconds
        if summary_seconds is not None:
            job.summary_seconds = summary_seconds


def mark_job_chunk_progress(job_id: str, completed_chunks: int, total_chunks: int) -> None:
    """STT 청크 완료 수를 작업 상태에 반영합니다."""
    safe_total = max(0, total_chunks)
    safe_completed = max(0, min(completed_chunks, safe_total))
    progress = 10 if safe_total == 0 else 10 + round((safe_completed / safe_total) * 70)

    with JOBS_LOCK:
        job = require_job(job_id)
        job.completed_chunks = safe_completed
        job.total_chunks = safe_total
        job.progress = max(job.progress, min(80, progress))
        job.stage = "음성 변환"
        if safe_total > 1:
            job.message = f"음성을 텍스트로 변환하는 중입니다. {safe_completed}/{safe_total} 구간 완료"
        else:
            job.message = "음성을 텍스트로 변환하는 중입니다."


def mark_job_transcribed(
    job_id: str,
    transcript: str,
) -> None:
    """STT 결과를 저장하고 transcript 검토 가능 상태로 변경합니다."""
    with JOBS_LOCK:
        job = require_job(job_id)
        job.status = "completed"
        job.completed_at = utc_now()
        job.progress = 100
        job.stage = "Transcript 준비 완료"
        job.message = "음성 변환이 완료되었습니다. Transcript를 검토해 주세요."
        job.result = PipelineResult(transcript=transcript, minutes="")


def mark_job_completed(
    job_id: str,
    transcript: str,
    summary: dict[str, Any],
) -> None:
    """작업 결과를 저장하고 완료 상태로 변경합니다."""
    action_items = summary.get("action_items")
    summary_facts = summary.get("summary_facts")
    decisions = summary.get("decisions")
    speaker_highlights = summary.get("speaker_highlights")
    warnings = summary.get("warnings")

    with JOBS_LOCK:
        job = require_job(job_id)
        job.status = "completed"
        job.completed_at = utc_now()
        job.progress = 100
        job.stage = "완료"
        job.message = "회의록 생성이 완료되었습니다."
        job.result = PipelineResult(
            transcript=transcript,
            minutes=summary.get("minutes") if isinstance(summary.get("minutes"), str) else "",
            action_items=[item for item in action_items if isinstance(item, dict)] if isinstance(action_items, list) else [],
            summary_facts=[item for item in summary_facts if isinstance(item, str)] if isinstance(summary_facts, list) else [],
            decisions=[item for item in decisions if isinstance(item, dict)] if isinstance(decisions, list) else [],
            speaker_highlights=[item for item in speaker_highlights if isinstance(item, str)] if isinstance(speaker_highlights, list) else [],
            warnings=[item for item in warnings if isinstance(item, str)] if isinstance(warnings, list) else [],
        )


def mark_job_failed(job_id: str, error: str) -> None:
    """작업 실패 메시지를 저장합니다."""
    with JOBS_LOCK:
        job = require_job(job_id)
        job.status = "failed"
        job.completed_at = utc_now()
        job.error = error
        job.stage = "실패"
        job.message = "회의록 생성 중 문제가 발생했습니다."


def cleanup_job_files(job_id: str) -> None:
    """작업 처리에 사용한 임시 파일 디렉터리를 삭제합니다."""
    shutil.rmtree(get_job_dir(job_id), ignore_errors=True)


def require_job(job_id: str) -> JobRecord:
    """작업이 존재하지 않으면 명확한 예외를 발생시킵니다."""
    job = get_job(job_id)
    if job is None:
        raise KeyError(f"작업을 찾을 수 없습니다: {job_id}")
    return job
