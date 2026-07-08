"""Gateway auth middleware and login endpoint tests."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from passlib.apache import HtpasswdFile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import gateway_auth


class GatewayAuthTests(unittest.TestCase):
    """Gateway auth protects API routes with the shared htpasswd password."""

    def test_login_success_allows_protected_route(self) -> None:
        with gateway_auth_test_client("correct-password") as client:
            login_response = client.post("/api/auth/login", json={"password": "correct-password"})
            protected_response = client.get("/api/health")

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json(), {"authenticated": True})
        self.assertEqual(protected_response.status_code, 200)
        self.assertEqual(protected_response.json(), {"status": "ok"})

    def test_login_failure_returns_401(self) -> None:
        with gateway_auth_test_client("correct-password") as client:
            response = client.post("/api/auth/login", json={"password": "wrong-password"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "비밀번호가 틀렸습니다.")

    def test_protected_route_without_auth_returns_401(self) -> None:
        with gateway_auth_test_client("correct-password") as client:
            response = client.get("/api/health")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "인증이 필요합니다.")


class gateway_auth_test_client:
    """Context manager that builds a tiny app with a temp htpasswd file."""

    def __init__(self, password: str) -> None:
        self.password = password
        self.temp_dir: tempfile.TemporaryDirectory[str] | None = None
        self.env_patch = None
        self.signer_patch = None

    def __enter__(self) -> TestClient:
        self.temp_dir = tempfile.TemporaryDirectory()
        htpasswd_path = Path(self.temp_dir.name) / ".htpasswd"
        htpasswd = HtpasswdFile(str(htpasswd_path), new=True)
        htpasswd.set_password("bigxdata", self.password)
        htpasswd.save()

        self.env_patch = patch.dict(
            os.environ,
            {
                "GATEWAY_AUTH_SECRET": "test-gateway-secret",
                "GATEWAY_HTPASSWD_PATH": str(htpasswd_path),
            },
        )
        self.env_patch.start()
        self.signer_patch = patch("backend.gateway_auth.get_gateway_signer", return_value=StaticGatewaySigner())
        self.signer_patch.start()

        app = FastAPI()
        app.middleware("http")(gateway_auth.gateway_auth_middleware)
        app.include_router(gateway_auth.router, prefix="/api")

        @app.get("/api/health")
        def health() -> dict[str, str]:
            return {"status": "ok"}

        return TestClient(app)

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if self.signer_patch is not None:
            self.signer_patch.stop()
        if self.env_patch is not None:
            self.env_patch.stop()
        if self.temp_dir is not None:
            self.temp_dir.cleanup()


class StaticGatewaySigner:
    """Small deterministic signer for tests, avoiding global itsdangerous fakes."""

    def sign(self, value: str) -> bytes:
        return f"signed:{value}".encode("utf-8")

    def unsign(self, signed_value: str, max_age: int | None = None) -> str:
        if not signed_value.startswith("signed:"):
            raise gateway_auth.BadSignature("invalid test signature")
        return signed_value.removeprefix("signed:")


if __name__ == "__main__":
    unittest.main()
