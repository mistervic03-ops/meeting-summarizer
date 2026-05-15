"""Speech-to-text helpers for meeting audio files."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from utils import cleanup_temp_files, ensure_audio_file, split_audio_if_needed


# 기본 STT 모델입니다. 운영 환경에서는 OPENAI_TRANSCRIPTION_MODEL로 교체할 수 있습니다.
DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-transcribe"


def transcribe_audio(audio_files: Path | list[Path]) -> str:
    """Transcribe one or more audio files and merge the transcript text."""
    # 이 함수가 새로 만든 청크 파일만 추적해서 finally에서 정리합니다.
    temp_files: list[Path] = []

    try:
        # 25MB 초과 파일은 utils.py에서 청크로 나뉘어 API 호출 대상이 됩니다.
        files_to_transcribe = prepare_audio_files(audio_files)
        original_files = normalize_audio_files(audio_files)
        temp_files.extend(file for file in files_to_transcribe if file not in original_files)

        # 청크 순서대로 STT 결과를 이어 붙여 원본 회의 흐름을 유지합니다.
        transcripts = [transcribe_chunk(audio_file) for audio_file in files_to_transcribe]
        return "\n\n".join(transcript.strip() for transcript in transcripts if transcript.strip())
    except Exception as exc:
        raise RuntimeError(f"Audio transcription failed: {exc}") from exc
    finally:
        cleanup_temp_files(temp_files)


def transcribe_chunk(audio_file: Path) -> str:
    """Transcribe a single audio chunk with the configured STT model."""
    try:
        # API 호출 전에 파일 존재 여부와 확장자를 다시 검증해 빠르게 실패시킵니다.
        ensure_audio_file(audio_file)
        client = create_openai_client()

        # OpenAI SDK는 파일 객체를 받으므로 바이너리 모드로 열어 전달합니다.
        with audio_file.open("rb") as file_data:
            transcription = client.audio.transcriptions.create(
                model=get_transcription_model(),
                file=file_data,
            )

        return extract_transcript_text(transcription)
    except Exception as exc:
        raise RuntimeError(f"Audio chunk transcription failed for {audio_file}: {exc}") from exc


def prepare_audio_files(audio_files: Path | list[Path]) -> list[Path]:
    """Validate audio inputs and split files that exceed the API size limit."""
    # 여러 파일을 처리하다 중간 실패해도 이미 생성된 임시 청크를 정리해야 합니다.
    prepared_files: list[Path] = []
    generated_temp_files: list[Path] = []

    try:
        original_files = normalize_audio_files(audio_files)

        for audio_file in original_files:
            # split_audio_if_needed가 원본 또는 청크 목록을 반환합니다.
            ensure_audio_file(audio_file)
            split_files = split_audio_if_needed(audio_file)
            prepared_files.extend(split_files)
            generated_temp_files.extend(file for file in split_files if file not in original_files)
        return prepared_files
    except Exception as exc:
        cleanup_temp_files(generated_temp_files)
        raise RuntimeError(f"Audio preparation failed: {exc}") from exc


def normalize_audio_files(audio_files: Path | list[Path]) -> list[Path]:
    """Normalize a single audio path or list of paths into a list."""
    # 이후 로직은 항상 리스트 기준으로 순회하도록 입력 형태를 통일합니다.
    if isinstance(audio_files, Path):
        return [audio_files]
    return audio_files


def create_openai_client() -> OpenAI:
    """Create an OpenAI API client using the API key from environment variables."""
    try:
        # API 키는 코드에 하드코딩하지 않고 .env 또는 서버 환경 변수에서만 읽습니다.
        load_dotenv()
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is missing. Add it to your .env file.")
        return OpenAI()
    except Exception as exc:
        raise RuntimeError(f"OpenAI client initialization failed: {exc}") from exc


def get_transcription_model() -> str:
    """Return the transcription model configured by environment variables."""
    return os.getenv("OPENAI_TRANSCRIPTION_MODEL", DEFAULT_TRANSCRIPTION_MODEL)


def extract_transcript_text(transcription: object) -> str:
    """Extract transcript text from an OpenAI transcription response."""
    # SDK 버전이나 테스트 mock 형태에 따라 문자열/객체/dict 응답을 모두 허용합니다.
    if isinstance(transcription, str):
        return transcription

    text = getattr(transcription, "text", None)
    if isinstance(text, str):
        return text

    if isinstance(transcription, dict) and isinstance(transcription.get("text"), str):
        return transcription["text"]

    raise ValueError("OpenAI transcription response did not include text.")
