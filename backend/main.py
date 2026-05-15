"""회의록 생성 API 서버의 FastAPI 진입점입니다."""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# `cd backend` 실행 시에도 프로젝트 루트의 기존 모듈을 import할 수 있게 합니다.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from backend.api.routes import router
except ModuleNotFoundError:
    # `cd backend && uvicorn main:app` 실행도 지원하기 위해 로컬 import를 허용합니다.
    from api.routes import router


def create_app() -> FastAPI:
    """FastAPI 앱을 생성하고 공통 미들웨어와 라우터를 연결합니다."""
    app = FastAPI(
        title="Meeting Summarizer API",
        description="오디오 회의 파일을 텍스트로 변환하고 회의록으로 요약하는 API입니다.",
        version="0.1.0",
    )

    # React 개발 서버와 사내 배포 환경에서 API를 호출할 수 있도록 CORS를 허용합니다.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")
    return app


app = create_app()
