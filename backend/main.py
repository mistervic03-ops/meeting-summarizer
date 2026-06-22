"""회의록 생성 API 서버의 FastAPI 진입점입니다."""

import os
import threading
import time

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.db import cleanup_expired, init_db

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
CLEANUP_INTERVAL_SECONDS = 60 * 60
_cleanup_thread_started = False


def create_app() -> FastAPI:
    """FastAPI 앱을 생성하고 공통 미들웨어와 라우터를 연결합니다."""
    load_dotenv()
    init_db()
    start_cleanup_scheduler()
    app = FastAPI(
        title="Meeting Summarizer API",
        description="오디오 회의 파일을 텍스트로 변환하고 회의록으로 요약하는 API입니다.",
        version="0.1.0",
    )

    # React 개발 서버와 사내 배포 환경에서 API를 호출할 수 있도록 CORS를 허용합니다.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")
    return app


def start_cleanup_scheduler() -> None:
    """만료된 저장 데이터를 주기적으로 정리하는 daemon thread를 시작합니다."""
    global _cleanup_thread_started
    if _cleanup_thread_started:
        return

    cleanup_expired()
    cleanup_thread = threading.Thread(target=run_cleanup_loop, name="meeting-cleanup", daemon=True)
    cleanup_thread.start()
    _cleanup_thread_started = True


def run_cleanup_loop() -> None:
    """서버 실행 중 1시간 간격으로 만료 데이터 정리를 반복합니다."""
    while True:
        time.sleep(CLEANUP_INTERVAL_SECONDS)
        cleanup_expired()


def get_cors_origins() -> list[str]:
    """환경 변수 또는 기본값 기준으로 CORS 허용 origin 목록을 반환합니다."""
    raw_origins = os.getenv("CORS_ORIGINS", "").strip()
    if not raw_origins:
        return DEFAULT_CORS_ORIGINS

    origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    return origins or DEFAULT_CORS_ORIGINS


app = create_app()
