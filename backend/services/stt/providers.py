"""환경 변수 기반 STT provider 선택을 담당합니다."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Literal, Protocol

from summarization.models import NormalizedTranscript

TranscriptionMode = Literal["plain", "diarized"]


class TranscribeProvider(Protocol):
    """STT provider가 제공해야 하는 최소 전사 인터페이스입니다."""

    name: str

    def transcribe(
        self,
        audio_files: Path | list[Path],
        mode: TranscriptionMode = "plain",
    ) -> str | NormalizedTranscript:
        """오디오 파일을 받아 기존 transcript 반환 형태로 전사합니다."""


class OpenAITranscribeProvider:
    """기존 OpenAI STT 구현을 그대로 호출하는 provider입니다."""

    name = "openai"

    def __init__(self, implementation: Callable[[Path | list[Path], TranscriptionMode], str | NormalizedTranscript]) -> None:
        """기존 OpenAI 구현 함수를 provider에 연결합니다."""
        self.implementation = implementation

    def transcribe(
        self,
        audio_files: Path | list[Path],
        mode: TranscriptionMode = "plain",
    ) -> str | NormalizedTranscript:
        """현재 transcribe.py의 OpenAI chunk/retry workflow를 그대로 실행합니다."""
        return self.implementation(audio_files, mode=mode)


class LocalWhisperProvider:
    """향후 Spark GPU local Whisper 경로를 연결할 placeholder provider입니다."""

    name = "local_whisper"

    def transcribe(
        self,
        audio_files: Path | list[Path],
        mode: TranscriptionMode = "plain",
    ) -> str | NormalizedTranscript:
        """아직 구현되지 않은 local Whisper 경로를 명확히 거절합니다."""
        # TODO: Spark 서버 CUDA/faster-whisper 런타임 검증 후 이 provider에 실제 STT를 연결합니다.
        raise NotImplementedError(
            "STT_PROVIDER=local_whisper is not implemented yet. "
            "Use STT_PROVIDER=openai until the local Whisper runtime is added."
        )


def get_stt_provider_name() -> str:
    """환경 변수에서 STT provider 이름을 읽고 기본값 openai를 반환합니다."""
    return os.getenv("STT_PROVIDER", "openai").strip().lower() or "openai"


def get_stt_provider(
    openai_implementation: Callable[[Path | list[Path], TranscriptionMode], str | NormalizedTranscript],
) -> TranscribeProvider:
    """STT_PROVIDER 값에 맞는 provider 객체를 반환합니다."""
    provider_name = get_stt_provider_name()
    if provider_name == "openai":
        return OpenAITranscribeProvider(openai_implementation)
    if provider_name == "local_whisper":
        return LocalWhisperProvider()
    raise ValueError("Unsupported STT_PROVIDER. Use 'openai' or 'local_whisper'.")
