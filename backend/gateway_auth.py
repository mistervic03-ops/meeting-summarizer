"""Gateway password authentication for the API."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Callable, Awaitable

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from passlib.apache import HtpasswdFile
from pydantic import BaseModel
from starlette.responses import Response as StarletteResponse

COOKIE_NAME = "gwauth"
AUTH_DAYS = 7
AUTH_MAX_AGE_SECONDS = int(timedelta(days=AUTH_DAYS).total_seconds())
DEFAULT_AUTH_SECRET = "dev-gateway-secret-change-me"
DEFAULT_AUTH_USERNAME = "bigxdata"
DEFAULT_HTPASSWD_PATH = Path("secrets") / ".htpasswd"
AUTH_EXEMPT_PATHS = {
    "/api/auth/login",
    "/api/auth/me",
    "/api/auth/logout",
}

router = APIRouter()


class LoginRequest(BaseModel):
    """Password-only login request."""

    password: str


@router.post("/auth/login")
def login(payload: LoginRequest, response: Response) -> dict[str, bool]:
    """Validate the shared password and issue the gateway auth cookie."""
    if not verify_gateway_password(payload.password):
        raise HTTPException(status_code=401, detail="비밀번호가 틀렸습니다.")

    set_gateway_cookie(response)
    return {"authenticated": True}


@router.get("/auth/me")
def auth_status(request: Request) -> dict[str, bool]:
    """Return whether the request has a valid gateway auth cookie."""
    return {"authenticated": is_gateway_authenticated(request)}


@router.post("/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    """Clear the gateway auth cookie."""
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"authenticated": False}


async def gateway_auth_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[StarletteResponse]],
) -> StarletteResponse:
    """Protect all API routes except the gateway auth endpoints."""
    path = request.url.path
    if not path.startswith("/api/") or path in AUTH_EXEMPT_PATHS or request.method == "OPTIONS":
        return await call_next(request)

    if is_gateway_authenticated(request):
        return await call_next(request)

    return JSONResponse({"detail": "인증이 필요합니다."}, status_code=401)


def verify_gateway_password(password: str) -> bool:
    """Check the submitted password against the configured htpasswd file."""
    if not password:
        return False

    htpasswd_path = get_htpasswd_path()
    if not htpasswd_path.exists():
        return False

    try:
        htpasswd = HtpasswdFile(str(htpasswd_path))
        return bool(htpasswd.check_password(get_auth_username(), password))
    except Exception:
        return False


def is_gateway_authenticated(request: Request) -> bool:
    """Return True when the request has a valid signed gateway cookie."""
    signed_value = request.cookies.get(COOKIE_NAME)
    if not signed_value:
        return False

    try:
        value = get_gateway_signer().unsign(signed_value, max_age=AUTH_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return False

    authenticated_user = value.decode("utf-8") if isinstance(value, bytes) else str(value)
    return authenticated_user == get_auth_username()


def set_gateway_cookie(response: Response) -> None:
    """Set the signed gateway auth cookie."""
    signed_value = get_gateway_signer().sign(get_auth_username()).decode("utf-8")
    response.set_cookie(
        key=COOKIE_NAME,
        value=signed_value,
        max_age=AUTH_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )


def get_gateway_signer() -> TimestampSigner:
    """Return a signer for the gateway auth cookie."""
    return TimestampSigner(get_auth_secret())


def get_auth_secret() -> str:
    """Return the gateway auth secret, falling back to SESSION_SECRET."""
    return os.getenv("GATEWAY_AUTH_SECRET") or os.getenv("SESSION_SECRET", DEFAULT_AUTH_SECRET)


def get_auth_username() -> str:
    """Return the htpasswd username to validate."""
    return os.getenv("GATEWAY_AUTH_USERNAME", DEFAULT_AUTH_USERNAME)


def get_htpasswd_path() -> Path:
    """Return the htpasswd path used by gateway auth."""
    return Path(os.getenv("GATEWAY_HTPASSWD_PATH", str(DEFAULT_HTPASSWD_PATH)))
