"""회의록 생성 API 엔드포인트를 정의합니다."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

try:
    from backend.schemas import JobCreateResponse, JobResultResponse, JobStatusResponse
    from backend.services.pipeline import run_meeting_pipeline
    from backend.storage import create_job, get_job, mark_job_failed, save_upload_file
except ModuleNotFoundError:
    # `backend/` 디렉터리 안에서 직접 서버를 띄우는 개발 흐름을 지원합니다.
    from schemas import JobCreateResponse, JobResultResponse, JobStatusResponse
    from services.pipeline import run_meeting_pipeline
    from storage import create_job, get_job, mark_job_failed, save_upload_file

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    """API 서버가 요청을 받을 수 있는 상태인지 확인합니다."""
    return {"status": "ok"}


@router.post("/jobs", response_model=JobCreateResponse)
async def create_process_job(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(...),
    context_file: Optional[UploadFile] = File(default=None),
    context: str = Form(default=""),
) -> JobCreateResponse:
    """업로드된 오디오와 선택 컨텍스트를 저장하고 백그라운드 처리 작업을 시작합니다."""
    job = create_job(filename=audio_file.filename or "uploaded_audio")

    try:
        audio_path = await save_upload_file(job.id, audio_file)
        context_text = context.strip()

        if context_file is not None and context_file.filename:
            context_path = await save_upload_file(job.id, context_file)
            context_text = context_path.read_text(encoding="utf-8").strip()

        # 긴 STT/요약 작업은 요청 응답을 막지 않도록 백그라운드에서 실행합니다.
        background_tasks.add_task(run_meeting_pipeline, job.id, audio_path, context_text)
    except Exception as exc:
        mark_job_failed(job.id, f"업로드 파일을 처리하지 못했습니다: {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JobCreateResponse(job_id=job.id, status=job.status)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_process_job(job_id: str) -> JobStatusResponse:
    """작업 진행 상태를 조회합니다."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        filename=job.filename,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error=job.error,
    )


@router.get("/jobs/{job_id}/result", response_model=JobResultResponse)
def get_process_result(job_id: str) -> JobResultResponse:
    """완료된 작업의 회의록 결과를 반환합니다."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    if job.status != "completed" or job.result is None:
        raise HTTPException(status_code=409, detail="아직 회의록 생성이 완료되지 않았습니다.")

    return JobResultResponse(
        job_id=job.id,
        filename=job.filename,
        transcript=job.result.transcript,
        minutes=job.result.minutes,
        action_items=job.result.action_items,
        summary_facts=job.result.summary_facts,
        decisions=job.result.decisions,
        speaker_highlights=job.result.speaker_highlights,
        warnings=job.result.warnings,
    )


@router.get("/jobs/{job_id}/download", response_class=PlainTextResponse)
def download_minutes(job_id: str) -> PlainTextResponse:
    """완료된 회의록을 txt 파일로 내려받을 수 있게 반환합니다."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    if job.status != "completed" or job.result is None:
        raise HTTPException(status_code=409, detail="아직 다운로드할 회의록이 없습니다.")

    safe_filename = job.filename.rsplit(".", 1)[0] or "meeting"
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_filename}_minutes.txt"',
    }
    return PlainTextResponse(job.result.minutes, media_type="text/plain; charset=utf-8", headers=headers)
