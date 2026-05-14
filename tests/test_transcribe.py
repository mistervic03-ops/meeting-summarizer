"""Unit tests for the transcription module."""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def import_transcribe_with_fakes():
    """Import transcribe.py with fake external modules when dependencies are absent."""
    fake_dotenv = types.SimpleNamespace(load_dotenv=lambda: None)
    fake_openai = types.SimpleNamespace(OpenAI=object)
    fake_pydub = types.SimpleNamespace(AudioSegment=object)

    with patch.dict(
        sys.modules,
        {"dotenv": fake_dotenv, "openai": fake_openai, "pydub": fake_pydub},
    ):
        sys.modules.pop("utils", None)
        sys.modules.pop("transcribe", None)
        return importlib.import_module("transcribe")


transcribe = import_transcribe_with_fakes()


class TranscribeTests(unittest.TestCase):
    """Test STT orchestration without calling the OpenAI API."""

    def test_normalize_audio_files_accepts_single_path_or_list(self) -> None:
        """단일 Path와 Path 리스트를 모두 리스트 형태로 정규화합니다."""
        audio_file = Path("meeting.wav")

        self.assertEqual(transcribe.normalize_audio_files(audio_file), [audio_file])
        self.assertEqual(transcribe.normalize_audio_files([audio_file]), [audio_file])

    def test_extract_transcript_text_supports_common_response_shapes(self) -> None:
        """문자열, 객체, dict 응답에서 transcript text를 추출합니다."""
        self.assertEqual(transcribe.extract_transcript_text("hello"), "hello")
        self.assertEqual(transcribe.extract_transcript_text(types.SimpleNamespace(text="object text")), "object text")
        self.assertEqual(transcribe.extract_transcript_text({"text": "dict text"}), "dict text")

    def test_get_transcription_model_uses_env_override(self) -> None:
        """환경 변수로 STT 모델명을 덮어쓸 수 있습니다."""
        with patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_MODEL": "custom-stt"}):
            self.assertEqual(transcribe.get_transcription_model(), "custom-stt")

    def test_transcribe_audio_joins_chunks_and_cleans_temp_files(self) -> None:
        """청크 transcript를 합치고 새로 생성된 임시 청크를 정리합니다."""
        original_file = Path("meeting.wav")
        temp_chunk = Path("/private/tmp/meeting_chunk_001.wav")

        with patch.object(transcribe, "prepare_audio_files", return_value=[original_file, temp_chunk]), patch.object(
            transcribe, "transcribe_chunk", side_effect=[" first ", "second"]
        ), patch.object(transcribe, "cleanup_temp_files") as cleanup_mock:
            transcript = transcribe.transcribe_audio(original_file)

        self.assertEqual(transcript, "first\n\nsecond")
        cleanup_mock.assert_called_once_with([temp_chunk])

    def test_prepare_audio_files_cleans_generated_chunks_on_failure(self) -> None:
        """여러 파일 처리 중 실패해도 이미 생성한 청크를 정리합니다."""
        first_file = Path("first.wav")
        second_file = Path("second.wav")
        generated_chunk = Path("/private/tmp/first_chunk_001.wav")

        with patch.object(transcribe, "ensure_audio_file"), patch.object(
            transcribe, "split_audio_if_needed", side_effect=[[generated_chunk], RuntimeError("boom")]
        ), patch.object(transcribe, "cleanup_temp_files") as cleanup_mock:
            with self.assertRaises(RuntimeError):
                transcribe.prepare_audio_files([first_file, second_file])

        cleanup_mock.assert_called_once_with([generated_chunk])

    def test_transcribe_chunk_calls_openai_client_without_real_api(self) -> None:
        """fake OpenAI client로 단일 청크 STT 호출 파라미터를 확인합니다."""
        create_mock = Mock(return_value=types.SimpleNamespace(text="hello"))
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_MODEL": "mock-stt"}):
                result = transcribe.transcribe_chunk(audio_file)

        self.assertEqual(result, "hello")
        self.assertEqual(create_mock.call_args.kwargs["model"], "mock-stt")


if __name__ == "__main__":
    unittest.main()
