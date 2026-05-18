"""DB 없이 사용할 수 있는 로컬 임시 저장소와 인메모리 작업 저장소입니다."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile

from backend.schemas import JobStatus

UPLOAD_ROOT = Path(tempfile.gettempdir()) / "meeting_summarizer_api"
JOBS: dict[str, "JobRecord"] = {}


@dataclass
class PipelineResult:
    """STT와 회의록 생성 결과를 함께 보관합니다."""

    transcript: str
    minutes: str
    structured_transcript: dict[str, Any] | None = None
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
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    error: str | None = None
    result: PipelineResult | None = None
    progress: int = 0
    stage: str = "업로드 대기"
    message: str = "오디오 파일을 기다리고 있습니다."
    stt_seconds: float | None = None
    summary_seconds: float | None = None
    context: str = ""
    meeting_type: str = "general"


def create_job(filename: str) -> JobRecord:
    """새 작업을 만들고 인메모리 저장소에 등록합니다."""
    job = JobRecord(id=uuid4().hex, filename=filename)
    JOBS[job.id] = job
    get_job_dir(job.id).mkdir(parents=True, exist_ok=True)
    return job


def get_job(job_id: str) -> JobRecord | None:
    """작업 ID로 작업 상태를 조회합니다."""
    return JOBS.get(job_id)


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


def mark_job_processing(job_id: str) -> None:
    """작업 상태를 처리 중으로 변경합니다."""
    job = require_job(job_id)
    job.status = "processing"
    job.error = None
    job.progress = 10
    job.stage = "파일 준비"
    job.message = "오디오 파일을 확인하고 있습니다."


def set_job_context(job_id: str, context: str) -> None:
    """작업에서 사용할 팀 컨텍스트를 저장합니다."""
    require_job(job_id).context = context


def set_job_meeting_type(job_id: str, meeting_type: str) -> None:
    """작업에서 사용할 회의 유형을 저장합니다."""
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
    job = require_job(job_id)
    job.progress = max(0, min(100, progress))
    job.stage = stage
    job.message = message

    if stt_seconds is not None:
        job.stt_seconds = stt_seconds
    if summary_seconds is not None:
        job.summary_seconds = summary_seconds


def mark_job_transcribed(
    job_id: str,
    transcript: str,
    structured_transcript: dict[str, Any] | None = None,
) -> None:
    """STT 결과를 저장하고 transcript 검토 가능 상태로 변경합니다."""
    job = require_job(job_id)
    job.status = "completed"
    job.completed_at = datetime.now()
    job.progress = 100
    job.stage = "Transcript 준비 완료"
    job.message = "음성 변환이 완료되었습니다. Transcript를 검토해 주세요."
    job.result = PipelineResult(transcript=transcript, minutes="", structured_transcript=structured_transcript)


def mark_job_completed(
    job_id: str,
    transcript: str,
    summary: dict[str, Any],
    structured_transcript: dict[str, Any] | None = None,
) -> None:
    """작업 결과를 저장하고 완료 상태로 변경합니다."""
    job = require_job(job_id)
    job.status = "completed"
    job.completed_at = datetime.now()
    job.progress = 100
    job.stage = "완료"
    job.message = "회의록 생성이 완료되었습니다."
    action_items = summary.get("action_items")
    summary_facts = summary.get("summary_facts")
    decisions = summary.get("decisions")
    speaker_highlights = summary.get("speaker_highlights")
    warnings = summary.get("warnings")

    job.result = PipelineResult(
        transcript=transcript,
        minutes=summary.get("minutes") if isinstance(summary.get("minutes"), str) else "",
        structured_transcript=structured_transcript,
        action_items=[item for item in action_items if isinstance(item, dict)] if isinstance(action_items, list) else [],
        summary_facts=[item for item in summary_facts if isinstance(item, str)] if isinstance(summary_facts, list) else [],
        decisions=[item for item in decisions if isinstance(item, dict)] if isinstance(decisions, list) else [],
        speaker_highlights=[item for item in speaker_highlights if isinstance(item, str)] if isinstance(speaker_highlights, list) else [],
        warnings=[item for item in warnings if isinstance(item, str)] if isinstance(warnings, list) else [],
    )


def mark_job_failed(job_id: str, error: str) -> None:
    """작업 실패 메시지를 저장합니다."""
    job = require_job(job_id)
    job.status = "failed"
    job.completed_at = datetime.now()
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
