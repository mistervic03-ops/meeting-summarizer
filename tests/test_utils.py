"""Unit tests for audio utility helpers."""

from __future__ import annotations

import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FakeAudioSegment:
    """Small fake that behaves like a pydub AudioSegment for unit tests."""

    def __init__(self, duration_ms: int = 10_000) -> None:
        self.duration_ms = duration_ms

    def __len__(self) -> int:
        return self.duration_ms

    def __getitem__(self, audio_slice: slice) -> "FakeAudioSegment":
        start = audio_slice.start or 0
        stop = audio_slice.stop or self.duration_ms
        return FakeAudioSegment(stop - start)

    @classmethod
    def from_file(cls, audio_file: Path, format: str) -> "FakeAudioSegment":
        return cls()

    def export(self, output_path: Path, **kwargs: str) -> None:
        Path(output_path).write_bytes(b"x" * max(self.duration_ms, 1))


def import_utils_with_fake_pydub():
    """Import utils.py with a fake pydub module."""
    fake_pydub = types.SimpleNamespace(AudioSegment=FakeAudioSegment)

    with patch.dict(sys.modules, {"pydub": fake_pydub}):
        sys.modules.pop("utils", None)
        return importlib.import_module("utils")


utils = import_utils_with_fake_pydub()


class UtilsTests(unittest.TestCase):
    """Test file validation, splitting decisions, and cleanup behavior."""

    def test_ensure_audio_file_accepts_supported_file(self) -> None:
        """지원되는 확장자의 실제 파일은 검증을 통과합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            utils.ensure_audio_file(audio_file)

    def test_ensure_audio_file_rejects_unsupported_extension(self) -> None:
        """지원하지 않는 확장자는 명확한 에러로 거절합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.txt"
            audio_file.write_text("not audio", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                utils.ensure_audio_file(audio_file)

    def test_split_audio_if_needed_returns_original_under_limit(self) -> None:
        """크기 제한 이하 파일은 분할하지 않고 원본 경로를 반환합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            with patch.object(utils, "MAX_AUDIO_SIZE_BYTES", 10):
                self.assertEqual(utils.split_audio_if_needed(audio_file), [audio_file])

    def test_split_audio_if_needed_delegates_large_file(self) -> None:
        """크기 제한 초과 파일은 split_audio_file에 위임합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"large audio")
            chunk_path = Path(temp_dir) / "chunk.wav"

            with patch.object(utils, "MAX_AUDIO_SIZE_BYTES", 1), patch.object(
                utils, "split_audio_file", return_value=[chunk_path]
            ) as split_mock:
                self.assertEqual(utils.split_audio_if_needed(audio_file), [chunk_path])

            split_mock.assert_called_once_with(audio_file)

    def test_cleanup_temp_files_removes_files_and_temp_directory(self) -> None:
        """임시 청크 파일과 비어 있는 임시 디렉터리를 정리합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            chunk_dir = Path(temp_dir) / f"{utils.TEMP_CHUNK_DIR_PREFIX}abc"
            chunk_dir.mkdir()
            chunk_file = chunk_dir / "chunk.wav"
            chunk_file.write_bytes(b"audio")

            utils.cleanup_temp_files([chunk_file])

            self.assertFalse(chunk_file.exists())
            self.assertFalse(chunk_dir.exists())

    def test_ensure_audio_tooling_available_raises_when_missing(self) -> None:
        """ffmpeg/ffprobe가 없으면 pydub 사용 전에 명확히 실패합니다."""
        with patch.object(utils, "find_executable", return_value=None):
            with self.assertRaises(RuntimeError):
                utils.ensure_audio_tooling_available()

    def test_export_chunk_under_size_shrinks_until_file_is_under_limit(self) -> None:
        """export된 청크가 너무 크면 길이를 줄여 다시 시도합니다."""
        fake_audio = FakeAudioSegment(10)
        export_sizes = [20, 5]

        def fake_export(audio_chunk: FakeAudioSegment, output_path: Path, audio_format: str) -> None:
            Path(output_path).write_bytes(b"x" * export_sizes.pop(0))

        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "meeting.wav"
            source_file.write_bytes(b"audio")

            with patch.object(utils, "MAX_AUDIO_SIZE_BYTES", 10), patch.object(
                utils, "MIN_CHUNK_DURATION_MS", 1
            ), patch.object(utils, "export_audio_chunk", side_effect=fake_export):
                chunk_path, actual_end_ms = utils.export_chunk_under_size(
                    audio=fake_audio,
                    start_ms=0,
                    end_ms=10,
                    output_dir=Path(temp_dir),
                    source_file=source_file,
                    chunk_index=1,
                    audio_format="wav",
                )

            self.assertEqual(chunk_path.stat().st_size, 5)
            self.assertLess(actual_end_ms, 10)

    def test_split_audio_file_uses_audio_segment_and_exports_chunks(self) -> None:
        """실제 오디오 처리 없이 split_audio_file의 orchestration을 확인합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"x" * 100)
            temp_chunk_dir = Path(temp_dir) / f"{utils.TEMP_CHUNK_DIR_PREFIX}test"
            chunk_one = temp_chunk_dir / "meeting_chunk_001.wav"
            chunk_two = temp_chunk_dir / "meeting_chunk_002.wav"

            def fake_mkdtemp(prefix: str, dir: str) -> str:
                temp_chunk_dir.mkdir()
                return str(temp_chunk_dir)

            with patch.object(utils, "ensure_audio_tooling_available"), patch.object(
                utils.AudioSegment, "from_file", return_value=FakeAudioSegment(10_000)
            ), patch.object(utils, "mkdtemp", side_effect=fake_mkdtemp), patch.object(
                utils, "calculate_initial_chunk_duration_ms", return_value=6_000
            ), patch.object(
                utils,
                "export_chunk_under_size",
                side_effect=[(chunk_one, 6_000), (chunk_two, 10_000)],
            ):
                chunks = utils.split_audio_file(audio_file)

        self.assertEqual(chunks, [chunk_one, chunk_two])


if __name__ == "__main__":
    unittest.main()
