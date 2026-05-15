"""API 요청과 응답에 사용하는 Pydantic 모델을 정의합니다."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

JobStatus = Literal["pending", "processing", "completed", "failed"]
Confidence = Literal["high", "low"]
DecisionStatus = Literal["확정", "미확정"]


class JobCreateResponse(BaseModel):
    """작업 생성 직후 클라이언트에 반환하는 응답 모델입니다."""

    job_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    """작업 상태 polling에 사용하는 응답 모델입니다."""

    job_id: str
    status: JobStatus
    filename: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


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
    transcript: str
    minutes: str
    action_items: list[ActionItemResponse] = []
    summary_facts: list[str] = []
    decisions: list[DecisionResponse] = []
    speaker_highlights: list[str] = []
    warnings: list[str] = []
