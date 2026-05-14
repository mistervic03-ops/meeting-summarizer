"""Utility helpers for audio splitting and file cleanup."""

from __future__ import annotations

from pathlib import Path


MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}


def ensure_audio_file(audio_file: Path) -> None:
    """Validate that the provided path points to a supported audio file."""
    try:
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file does not exist: {audio_file}")
        if not audio_file.is_file():
            raise ValueError(f"Audio path is not a file: {audio_file}")
        if audio_file.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
            raise ValueError(f"Unsupported audio file extension: {audio_file.suffix}")
    except Exception as exc:
        raise RuntimeError(f"Audio file validation failed: {exc}") from exc


def split_audio_if_needed(audio_file: Path) -> list[Path]:
    """Return audio chunks, splitting the file first when it exceeds the size limit."""
    try:
        if audio_file.stat().st_size <= MAX_AUDIO_SIZE_BYTES:
            return [audio_file]
        return split_audio_file(audio_file)
    except Exception as exc:
        raise RuntimeError(f"Audio splitting check failed: {exc}") from exc


def split_audio_file(audio_file: Path) -> list[Path]:
    """Split a large audio file into chunks below the configured size limit."""
    try:
        raise NotImplementedError("Audio chunk splitting will be added later.")
    except Exception as exc:
        raise RuntimeError(f"Audio file splitting failed for {audio_file}: {exc}") from exc


def cleanup_temp_files(temp_files: list[Path]) -> None:
    """Delete temporary files created during audio processing."""
    for temp_file in temp_files:
        try:
            if temp_file.exists():
                temp_file.unlink()
        except Exception as exc:
            print(f"Failed to delete temporary file {temp_file}: {exc}")
