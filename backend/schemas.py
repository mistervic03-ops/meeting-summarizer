"""API 요청과 응답에 사용하는 Pydantic 모델을 정의합니다."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

JobStatus = Literal["pending", "processing", "completed", "failed"]
Confidence = Literal["high", "low"]
DecisionStatus = Literal["확정", "미확정"]
MeetingType = Literal["execution", "customer_meeting", "technical_review", "brainstorming", "general"]


class JobCreateResponse(BaseModel):
    """작업 생성 직후 클라이언트에 반환하는 응답 모델입니다."""

    job_id: str
    status: JobStatus


class TranscriptUtterancePayload(BaseModel):
    """speaker-aware transcript의 단일 발화 payload입니다."""

    utterance_id: Optional[str] = None
    speaker: Optional[str] = None
    text: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None


class StructuredTranscriptPayload(BaseModel):
    """speaker-aware transcript payload입니다."""

    utterances: list[TranscriptUtterancePayload]


class TranscriptJobRequest(BaseModel):
    """검토 또는 수정된 transcript로 회의록 생성을 시작하는 요청 모델입니다."""

    filename: str = "transcript.txt"
    transcript: str
    context: str = ""
    meeting_type: MeetingType = "general"
    structured_transcript: Optional[StructuredTranscriptPayload] = None
    transcription_job_id: Optional[str] = None


class TranscriptResultResponse(BaseModel):
    """STT 완료 후 transcript 검토 화면에 반환하는 응답 모델입니다."""

    job_id: str
    filename: str
    meeting_type: MeetingType = "general"
    transcript: str
    context: str = ""
    stt_seconds: Optional[float] = None
    structured_transcript: Optional[StructuredTranscriptPayload] = None


class JobStatusResponse(BaseModel):
    """작업 상태 polling에 사용하는 응답 모델입니다."""

    job_id: str
    status: JobStatus
    filename: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    progress: int = 0
    stage: str = "업로드 대기"
    message: str = "오디오 파일을 기다리고 있습니다."
    completed_chunks: Optional[int] = None
    total_chunks: Optional[int] = None
    stt_seconds: Optional[float] = None
    summary_seconds: Optional[float] = None


class ActionItemResponse(BaseModel):
    """프론트엔드 액션 아이템 탭에 표시할 작업 항목입니다."""

    task: str
    owner: str
    due_date: str
    confidence: Confidence


class DecisionResponse(BaseModel):
    """프론트엔드 요약 탭에 표시할 결정사항입니다."""

    decision: str
    status: DecisionStatus


class JobResultResponse(BaseModel):
    """완료된 회의록 생성 결과 응답 모델입니다."""

    job_id: str
    filename: str
    meeting_type: MeetingType = "general"
    transcript: str
    minutes: str
    action_items: list[ActionItemResponse] = []
    summary_facts: list[str] = []
    decisions: list[DecisionResponse] = []
    speaker_highlights: list[str] = []
    warnings: list[str] = []
