"""Speech-to-text skeleton for meeting audio files."""

from __future__ import annotations

from pathlib import Path


TRANSCRIPTION_MODEL = "gpt-4o-transcribe"


def transcribe_audio(audio_files: list[Path]) -> str:
    """Transcribe one or more audio files into a single transcript string."""
    try:
        raise NotImplementedError("STT implementation will be added later.")
    except Exception as exc:
        raise RuntimeError(f"Audio transcription failed: {exc}") from exc


def transcribe_chunk(audio_file: Path) -> str:
    """Transcribe a single audio chunk with the configured STT model."""
    try:
        raise NotImplementedError("Single-chunk transcription will be added later.")
    except Exception as exc:
        raise RuntimeError(f"Audio chunk transcription failed for {audio_file}: {exc}") from exc
