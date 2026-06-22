"""회의록 생성 API 엔드포인트를 정의합니다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import PlainTextResponse

try:
    from backend.db import get_db_connection
    from backend.schemas import JobCreateResponse, JobResultResponse, JobStatusResponse, MeetingType, TranscriptJobRequest, TranscriptResultResponse
    from backend.session import get_or_create_session
    from backend.services.pipeline import run_meeting_pipeline, run_transcript_summary_pipeline, run_transcription_pipeline
    from backend.storage import create_job, get_job, get_job_status_snapshot, mark_job_failed, save_upload_file, set_job_context, set_job_meeting_type
except ModuleNotFoundError:
    # `backend/` 디렉터리 안에서 직접 서버를 띄우는 개발 흐름을 지원합니다.
    from db import get_db_connection
    from schemas import JobCreateResponse, JobResultResponse, JobStatusResponse, MeetingType, TranscriptJobRequest, TranscriptResultResponse
    from session import get_or_create_session
    from services.pipeline import run_meeting_pipeline, run_transcript_summary_pipeline, run_transcription_pipeline
    from storage import create_job, get_job, get_job_status_snapshot, mark_job_failed, save_upload_file, set_job_context, set_job_meeting_type

router = APIRouter()
RETENTION_DAYS = 7


@router.get("/health")
def health_check() -> dict[str, str]:
    """API 서버가 요청을 받을 수 있는 상태인지 확인합니다."""
    return {"status": "ok"}


@router.post("/jobs", response_model=JobCreateResponse)
async def create_process_job(
    background_tasks: BackgroundTasks,
    request: Request,
    response: Response,
    audio_file: UploadFile = File(...),
    context: str = Form(default=""),
    meeting_type: MeetingType = Form(default="execution"),
) -> JobCreateResponse:
    """업로드된 오디오와 선택 컨텍스트를 저장하고 백그라운드 처리 작업을 시작합니다."""
    session_id = get_or_create_session(request, response)
    job = create_job(filename=audio_file.filename or "uploaded_audio")
    create_meeting_record(job.id, session_id, job.filename, "pending")

    try:
        audio_path = await save_upload_file(job.id, audio_file)
        context_text = context.strip()

        # 긴 STT/요약 작업은 요청 응답을 막지 않도록 백그라운드에서 실행합니다.
        set_job_meeting_type(job.id, meeting_type)
        background_tasks.add_task(run_meeting_pipeline, job.id, audio_path, context_text, meeting_type)
    except Exception as exc:
        mark_job_failed(job.id, f"업로드 파일을 처리하지 못했습니다: {exc}")
        mark_meeting_failed(job.id, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JobCreateResponse(job_id=job.id, status=job.status)


@router.post("/transcriptions", response_model=JobCreateResponse)
async def create_transcription_job(
    background_tasks: BackgroundTasks,
    request: Request,
    response: Response,
    audio_file: UploadFile = File(...),
    context: str = Form(default=""),
    meeting_type: MeetingType = Form(default="execution"),
    transcription_mode: str = Form(default="plain"),
    stt_provider: str = Form(default=""),
) -> JobCreateResponse:
    """업로드된 오디오를 STT 처리해 transcript 검토 작업을 시작합니다."""
    if transcription_mode not in {"plain", "diarized"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 transcription mode입니다.")
    if stt_provider and stt_provider not in {"local_gpu_whisper", "openai"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 STT provider입니다.")

    session_id = get_or_create_session(request, response)
    job = create_job(filename=audio_file.filename or "uploaded_audio")
    create_meeting_record(job.id, session_id, job.filename, "pending")

    try:
        audio_path = await save_upload_file(job.id, audio_file)
        context_text = context.strip()

        set_job_context(job.id, context_text)
        set_job_meeting_type(job.id, meeting_type)
        background_tasks.add_task(
            run_transcription_pipeline,
            job.id,
            audio_path,
            transcription_mode,
            meeting_type,
            stt_provider or None,
        )
    except Exception as exc:
        mark_job_failed(job.id, f"업로드 파일을 처리하지 못했습니다: {exc}")
        mark_meeting_failed(job.id, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JobCreateResponse(job_id=job.id, status=job.status)


@router.post("/transcript-jobs", response_model=JobCreateResponse)
def create_transcript_process_job(
    request: Request,
    response: Response,
    payload: TranscriptJobRequest,
    background_tasks: BackgroundTasks,
) -> JobCreateResponse:
    """검토 또는 수정된 transcript를 받아 회의록 생성 작업을 시작합니다."""
    transcript = payload.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="회의록을 생성할 transcript가 비어 있습니다.")

    session_id = get_or_create_session(request, response)
    structured_transcript = dump_structured_transcript(payload.structured_transcript)
    job = create_job(filename=payload.filename or "transcript.txt")
    create_meeting_record(job.id, session_id, job.filename, "pending")
    background_tasks.add_task(
        run_transcript_summary_pipeline,
        job.id,
        transcript,
        payload.context.strip(),
        structured_transcript,
        payload.meeting_type,
    )
    return JobCreateResponse(job_id=job.id, status=job.status)


@router.get("/meetings")
def list_meetings(request: Request, response: Response) -> list[dict[str, Any]]:
    """현재 세션에 속한 저장 회의 목록을 반환합니다."""
    session_id = get_or_create_session(request, response)
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, title, status, created_at, expires_at, transcript_path, summary_path, error
            FROM meetings
            WHERE session_id = ?
            ORDER BY created_at DESC
            """,
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@router.get("/meetings/{meeting_id}")
def get_meeting(meeting_id: str, request: Request, response: Response) -> dict[str, Any]:
    """현재 세션에 속한 저장 회의 artifact 내용을 반환합니다."""
    session_id = get_or_create_session(request, response)
    with get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT id, title, status, created_at, expires_at, transcript_path, summary_path, error
            FROM meetings
            WHERE id = ? AND session_id = ?
            """,
            (meeting_id, session_id),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="회의를 찾을 수 없습니다.")

    meeting = dict(row)
    return {
        **meeting,
        "transcript": read_text_artifact(meeting.get("transcript_path")),
        "summary": read_text_artifact(meeting.get("summary_path")),
    }


@router.get("/jobs/{job_id}/transcript", response_model=TranscriptResultResponse)
def get_transcription_result(job_id: str) -> TranscriptResultResponse:
    """STT 완료 작업의 transcript와 팀 컨텍스트를 반환합니다."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    if job.status != "completed" or job.result is None or not job.result.transcript:
        raise HTTPException(status_code=409, detail="아직 transcript 생성이 완료되지 않았습니다.")

    return TranscriptResultResponse(
        job_id=job.id,
        filename=job.filename,
        meeting_type=job.meeting_type,
        transcript=job.result.transcript,
        context=job.context,
        stt_seconds=job.stt_seconds,
        structured_transcript=job.result.structured_transcript,
    )


def dump_structured_transcript(structured_transcript: object) -> dict | None:
    """Pydantic 버전에 맞춰 structured transcript를 저장 가능한 dict로 변환합니다."""
    if structured_transcript is None:
        return None
    model_dump = getattr(structured_transcript, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    dict_dump = getattr(structured_transcript, "dict", None)
    if callable(dict_dump):
        return dict_dump()
    return None


def create_meeting_record(job_id: str, session_id: str, title: str, status: str) -> None:
    """새 작업을 현재 세션의 영구 meeting row로 등록합니다."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=RETENTION_DAYS)
    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO meetings(id, session_id, title, status, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, session_id, title, status, now.isoformat(), expires_at.isoformat()),
        )


def mark_meeting_failed(job_id: str, error: str) -> None:
    """업로드 단계 실패를 영구 meeting row에 반영합니다."""
    with get_db_connection() as connection:
        connection.execute(
            """
            UPDATE meetings
            SET status = ?, error = ?
            WHERE id = ?
            """,
            ("failed", error, job_id),
        )


def read_text_artifact(raw_path: object) -> str:
    """artifact 경로가 있으면 텍스트 내용을 읽고 없으면 빈 문자열을 반환합니다."""
    if not isinstance(raw_path, str) or not raw_path:
        return ""
    path = Path(raw_path)
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_process_job(job_id: str) -> JobStatusResponse:
    """작업 진행 상태를 조회합니다."""
    job_snapshot = get_job_status_snapshot(job_id)
    if job_snapshot is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    return JobStatusResponse(**job_snapshot)


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
        meeting_type=job.meeting_type,
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
