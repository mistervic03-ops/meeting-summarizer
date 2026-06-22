"""서명된 쿠키 기반 사용자 세션을 관리합니다."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from backend.db import get_db_connection

COOKIE_NAME = "msid"
SESSION_DAYS = 7
SESSION_MAX_AGE_SECONDS = SESSION_DAYS * 24 * 60 * 60
DEFAULT_SESSION_SECRET = "dev-secret-change-me"


def get_or_create_session(request: Request, response: Response) -> str:
    """요청 쿠키의 세션을 확인하고 없거나 만료되었으면 새 세션을 만듭니다."""
    signed_session_id = request.cookies.get(COOKIE_NAME)
    session_id = verify_signed_session_id(signed_session_id)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=SESSION_DAYS)

    if session_id and refresh_existing_session(session_id, now, expires_at):
        set_session_cookie(response, session_id)
        return session_id

    next_session_id = uuid4().hex
    create_session(next_session_id, now, expires_at)
    set_session_cookie(response, next_session_id)
    return next_session_id


def verify_signed_session_id(signed_session_id: str | None) -> str | None:
    """서명된 세션 쿠키 값을 검증하고 원본 session id를 반환합니다."""
    if not signed_session_id:
        return None

    signer = get_session_signer()
    try:
        unsigned = signer.unsign(signed_session_id, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None

    return unsigned.decode("utf-8") if isinstance(unsigned, bytes) else str(unsigned)


def refresh_existing_session(session_id: str, now: datetime, expires_at: datetime) -> bool:
    """DB에 유효한 세션이 있으면 last_seen_at과 expires_at을 갱신합니다."""
    now_iso = now.isoformat()
    expires_at_iso = expires_at.isoformat()

    with get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT id
            FROM sessions
            WHERE id = ? AND expires_at >= ?
            """,
            (session_id, now_iso),
        ).fetchone()
        if row is None:
            return False

        connection.execute(
            """
            UPDATE sessions
            SET last_seen_at = ?, expires_at = ?
            WHERE id = ?
            """,
            (now_iso, expires_at_iso, session_id),
        )
        return True


def create_session(session_id: str, now: datetime, expires_at: datetime) -> None:
    """새 세션 row를 DB에 저장합니다."""
    now_iso = now.isoformat()
    expires_at_iso = expires_at.isoformat()

    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO sessions(id, created_at, last_seen_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, now_iso, now_iso, expires_at_iso),
        )


def set_session_cookie(response: Response, session_id: str) -> None:
    """session id를 서명한 뒤 HttpOnly SameSite=Lax 쿠키로 설정합니다."""
    signed_session_id = get_session_signer().sign(session_id).decode("utf-8")
    response.set_cookie(
        key=COOKIE_NAME,
        value=signed_session_id,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )


def get_session_signer() -> TimestampSigner:
    """환경 변수 SESSION_SECRET을 사용하는 TimestampSigner를 반환합니다."""
    secret = os.getenv("SESSION_SECRET", DEFAULT_SESSION_SECRET)
    return TimestampSigner(secret)
