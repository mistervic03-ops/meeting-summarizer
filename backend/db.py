"""SQLite 기반 영구 저장소 초기화와 정리 기능을 제공합니다."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("data") / "meeting_summarizer.db"


def get_db_connection() -> sqlite3.Connection:
    """SQLite 연결을 열고 WAL mode와 foreign key 제약을 활성화합니다."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db() -> None:
    """세션과 회의 저장에 필요한 SQLite 테이블을 생성합니다."""
    with get_db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions(
                id TEXT PRIMARY KEY,
                created_at TEXT,
                last_seen_at TEXT,
                expires_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS meetings(
                id TEXT PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
                title TEXT,
                status TEXT,
                created_at TEXT,
                expires_at TEXT,
                transcript_path TEXT,
                summary_path TEXT,
                error TEXT
            )
            """
        )


def cleanup_expired() -> None:
    """만료된 회의 row와 고아 세션을 삭제하고 관련 파일을 정리합니다."""
    now_iso = datetime.now(timezone.utc).isoformat()
    expired_paths: list[Path] = []

    with get_db_connection() as connection:
        expired_rows = connection.execute(
            """
            SELECT transcript_path, summary_path
            FROM meetings
            WHERE expires_at < ?
            """,
            (now_iso,),
        ).fetchall()
        for row in expired_rows:
            expired_paths.extend(build_existing_path_candidates(row["transcript_path"], row["summary_path"]))

        connection.execute("DELETE FROM meetings WHERE expires_at < ?", (now_iso,))
        connection.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso,))

    for path in expired_paths:
        try:
            if path.exists() and path.is_file():
                path.unlink()
        except OSError:
            continue


def build_existing_path_candidates(*raw_paths: str | None) -> list[Path]:
    """DB에 저장된 파일 경로 문자열을 정리 대상 Path 목록으로 바꿉니다."""
    paths: list[Path] = []
    for raw_path in raw_paths:
        if not raw_path:
            continue
        paths.append(Path(raw_path))
    return paths
