"""Pytest-wide environment isolation."""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest


ENVIRONMENT_KEYS = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_STRUCTURE_MODEL",
    "CLAUDE_SUMMARY_MODEL",
    "ENABLE_DIARIZED_TRANSCRIPTION",
    "ENABLE_STT_VOCABULARY_HINTS",
    "GATEWAY_AUTH_SECRET",
    "GATEWAY_AUTH_USERNAME",
    "GATEWAY_HTPASSWD_PATH",
    "LOCAL_GPU_DEVICE",
    "LOCAL_GPU_ENABLE_STT_PROMPT",
    "LOCAL_GPU_MAX_CONCURRENCY",
    "LOCAL_GPU_TORCH_DTYPE",
    "LOCAL_GPU_WHISPER_MODEL",
    "LOCAL_WHISPER_COMPUTE_TYPE",
    "LOCAL_WHISPER_DEVICE",
    "LOCAL_WHISPER_LANGUAGE",
    "LOCAL_WHISPER_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_DIARIZED_TRANSCRIPTION_MODEL",
    "OPENAI_STRUCTURE_MODEL",
    "OPENAI_SUMMARY_MODEL",
    "OPENAI_TRANSCRIPTION_LANGUAGE",
    "OPENAI_TRANSCRIPTION_MODEL",
    "PLAIN_CHUNK_DURATION_SECONDS",
    "PLAIN_CHUNK_OVERLAP_SECONDS",
    "PLAIN_TRANSCRIPTION_CONCURRENCY",
    "SESSION_SECRET",
    "STT_PROVIDER",
    "STT_VOCABULARY_PATH",
    "SUMMARIZATION_PROVIDER",
    "TRANSCRIPTION_MODE",
)

DOTENV_MODULES = (
    "backend.main",
    "summarization.llm_provider",
    "summarization.openai_utils",
    "transcribe",
)


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep tests independent from any real deployment .env file."""
    for key in ENVIRONMENT_KEYS:
        monkeypatch.delenv(key, raising=False)

    def load_dotenv_noop(*args: object, **kwargs: object) -> bool:
        return False

    try:
        import dotenv

        monkeypatch.setattr(dotenv, "load_dotenv", load_dotenv_noop, raising=False)
    except ModuleNotFoundError:
        pass

    for module_name in DOTENV_MODULES:
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "load_dotenv"):
            monkeypatch.setattr(module, "load_dotenv", load_dotenv_noop, raising=False)

    yield
