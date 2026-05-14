"""Unit tests for the CLI pipeline module."""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main


class MainTests(unittest.TestCase):
    """Test CLI path handling and pipeline orchestration."""

    def test_build_output_path_avoids_overwrite(self) -> None:
        """기존 회의록 파일이 있으면 번호가 붙은 새 경로를 반환합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")
            (Path(temp_dir) / "meeting_회의록.txt").write_text("old", encoding="utf-8")
            (Path(temp_dir) / "meeting_회의록_1.txt").write_text("old", encoding="utf-8")

            output_path = main.build_output_path(audio_file)

            self.assertEqual(output_path, Path(temp_dir) / "meeting_회의록_2.txt")

    def test_run_pipeline_uses_transcribe_then_summarize_and_saves_file(self) -> None:
        """API 호출 없이 mock 모듈로 전체 CLI 파이프라인 순서를 확인합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            fake_dotenv = types.SimpleNamespace(load_dotenv=Mock())
            fake_utils = types.SimpleNamespace(ensure_audio_file=Mock())
            fake_transcribe = types.SimpleNamespace(transcribe_audio=Mock(return_value="transcript text"))
            fake_summarize = types.SimpleNamespace(summarize_transcript=Mock(return_value="final minutes"))

            fake_modules = {
                "dotenv": fake_dotenv,
                "utils": fake_utils,
                "transcribe": fake_transcribe,
                "summarize": fake_summarize,
            }

            with patch.dict(sys.modules, fake_modules), redirect_stdout(StringIO()) as stdout:
                output_path = main.run_pipeline(audio_file)

            fake_dotenv.load_dotenv.assert_called_once_with()
            fake_utils.ensure_audio_file.assert_called_once_with(audio_file)
            fake_transcribe.transcribe_audio.assert_called_once_with(audio_file)
            fake_summarize.summarize_transcript.assert_called_once_with("transcript text")
            self.assertEqual(output_path.read_text(encoding="utf-8"), "final minutes")
            self.assertIn("final minutes", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
