"""DB 없이 사용할 수 있는 로컬 임시 저장소와 인메모리 작업 저장소입니다."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import UploadFile

try:
    from backend.schemas import JobStatus
except ModuleNotFoundError:
    # `cd backend` 실행 시에도 동일한 저장소 모듈을 사용할 수 있게 합니다.
    from schemas import JobStatus

UPLOAD_ROOT = Path(tempfile.gettempdir()) / "meeting_summarizer_api"
JOBS: dict[str, "JobRecord"] = {}


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
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[PipelineResult] = None


def create_job(filename: str) -> JobRecord:
    """새 작업을 만들고 인메모리 저장소에 등록합니다."""
    job = JobRecord(id=uuid4().hex, filename=filename)
    JOBS[job.id] = job
    get_job_dir(job.id).mkdir(parents=True, exist_ok=True)
    return job


def get_job(job_id: str) -> Optional[JobRecord]:
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


def mark_job_completed(
    job_id: str,
    transcript: str,
    minutes: str,
    action_items: Optional[list[dict[str, Any]]] = None,
    summary_facts: Optional[list[str]] = None,
    decisions: Optional[list[dict[str, Any]]] = None,
    speaker_highlights: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
) -> None:
    """작업 결과를 저장하고 완료 상태로 변경합니다."""
    job = require_job(job_id)
    job.status = "completed"
    job.completed_at = datetime.now()
    job.result = PipelineResult(
        transcript=transcript,
        minutes=minutes,
        action_items=action_items or [],
        summary_facts=summary_facts or [],
        decisions=decisions or [],
        speaker_highlights=speaker_highlights or [],
        warnings=warnings or [],
    )


def mark_job_failed(job_id: str, error: str) -> None:
    """작업 실패 메시지를 저장합니다."""
    job = require_job(job_id)
    job.status = "failed"
    job.completed_at = datetime.now()
    job.error = error


def cleanup_job_files(job_id: str) -> None:
    """작업 처리에 사용한 임시 파일 디렉터리를 삭제합니다."""
    shutil.rmtree(get_job_dir(job_id), ignore_errors=True)


def require_job(job_id: str) -> JobRecord:
    """작업이 존재하지 않으면 명확한 예외를 발생시킵니다."""
    job = get_job(job_id)
    if job is None:
        raise KeyError(f"작업을 찾을 수 없습니다: {job_id}")
    return job
