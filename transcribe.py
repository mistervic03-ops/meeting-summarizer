"""Speech-to-text helpers for meeting audio files."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from utils import cleanup_temp_files, ensure_audio_file, split_audio_if_needed


# OpenAI 음성 인식에 사용할 기본 모델명입니다. .env에서 덮어쓸 수 있습니다.
DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-transcribe"


def transcribe_audio(audio_files: Path | list[Path]) -> str:
    """Transcribe one or more audio files into a single transcript string."""
    # 이 함수 안에서 새로 만들어진 청크 파일만 정리 대상으로 추적합니다.
    temp_files: list[Path] = []

    try:
        # 입력 파일을 검증하고, 25MB를 넘는 경우 utils.py의 분할 함수로 청크를 만듭니다.
        files_to_transcribe = prepare_audio_files(audio_files)
        original_files = normalize_audio_files(audio_files)
        temp_files.extend(file for file in files_to_transcribe if file not in original_files)

        # 각 파일/청크를 순서대로 STT 처리한 뒤 하나의 transcript로 합칩니다.
        transcripts = [transcribe_chunk(audio_file) for audio_file in files_to_transcribe]
        return "\n\n".join(transcript.strip() for transcript in transcripts if transcript.strip())
    except Exception as exc:
        raise RuntimeError(f"Audio transcription failed: {exc}") from exc
    finally:
        # transcribe_audio가 직접 만든 임시 청크 파일은 처리 후 삭제합니다.
        cleanup_temp_files(temp_files)


def transcribe_chunk(audio_file: Path) -> str:
    """Transcribe a single audio chunk with the configured STT model."""
    try:
        # 청크 하나도 실제 파일인지 다시 확인해서 API 호출 전에 빠르게 실패시킵니다.
        ensure_audio_file(audio_file)
        client = create_openai_client()

        # OpenAI Audio Transcriptions API에 바이너리 파일 핸들을 넘겨 STT를 수행합니다.
        with audio_file.open("rb") as file_data:
            transcription = client.audio.transcriptions.create(
                model=get_transcription_model(),
                file=file_data,
            )

        # SDK 응답 형태가 바뀌어도 text 필드를 안정적으로 꺼내도록 별도 함수로 분리했습니다.
        return extract_transcript_text(transcription)
    except Exception as exc:
        raise RuntimeError(f"Audio chunk transcription failed for {audio_file}: {exc}") from exc


def prepare_audio_files(audio_files: Path | list[Path]) -> list[Path]:
    """Validate audio inputs and split files that exceed the API size limit."""
    # 최종적으로 API에 넘길 파일 목록입니다. 원본 파일 또는 분할된 청크가 들어갑니다.
    prepared_files: list[Path] = []
    generated_temp_files: list[Path] = []

    try:
        original_files = normalize_audio_files(audio_files)

        for audio_file in original_files:
            # 입력 파일마다 형식/존재 여부를 확인한 뒤 크기에 따라 분할합니다.
            ensure_audio_file(audio_file)
            split_files = split_audio_if_needed(audio_file)
            prepared_files.extend(split_files)
            generated_temp_files.extend(file for file in split_files if file not in original_files)
        return prepared_files
    except Exception as exc:
        # 여러 파일 처리 중간에 실패해도 이미 만든 임시 청크는 여기서 정리합니다.
        cleanup_temp_files(generated_temp_files)
        raise RuntimeError(f"Audio preparation failed: {exc}") from exc


def normalize_audio_files(audio_files: Path | list[Path]) -> list[Path]:
    """Normalize a single audio path or list of paths into a list."""
    # 호출자가 파일 하나만 넘겨도 이후 로직은 항상 리스트 기준으로 처리합니다.
    if isinstance(audio_files, Path):
        return [audio_files]
    return audio_files


def create_openai_client() -> OpenAI:
    """Create an OpenAI API client using the API key from environment variables."""
    try:
        # API 키는 코드에 직접 쓰지 않고 .env 또는 환경 변수에서만 읽습니다.
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
    # 응답이 문자열 자체로 오는 경우를 처리합니다.
    if isinstance(transcription, str):
        return transcription

    # OpenAI SDK 객체 응답의 .text 속성을 우선 사용합니다.
    text = getattr(transcription, "text", None)
    if isinstance(text, str):
        return text

    # 혹시 dict 형태로 응답이 들어와도 text 값을 꺼낼 수 있게 보완합니다.
    if isinstance(transcription, dict) and isinstance(transcription.get("text"), str):
        return transcription["text"]

    raise ValueError("OpenAI transcription response did not include text.")
