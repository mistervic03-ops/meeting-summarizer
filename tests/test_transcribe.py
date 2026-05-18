"""STT 모듈 단위 테스트입니다."""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def import_transcribe_with_fakes():
    """외부 의존성이 없을 때 fake 모듈로 transcribe.py를 import합니다."""
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
    """OpenAI API를 호출하지 않고 STT 흐름을 테스트합니다."""

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

    def test_normalize_speaker_label_handles_common_provider_shapes(self) -> None:
        """provider별 speaker 표기를 내부 라벨로 정규화합니다."""
        self.assertEqual(transcribe.normalize_speaker_label("speaker_1"), "Speaker 1")
        self.assertEqual(transcribe.normalize_speaker_label("SPEAKER 2"), "Speaker 2")
        self.assertEqual(transcribe.normalize_speaker_label(" Speaker 3 "), "Speaker 3")
        self.assertEqual(transcribe.normalize_speaker_label("영업담당자"), "영업담당자")
        self.assertEqual(transcribe.normalize_speaker_label(""), "Unknown")
        self.assertEqual(transcribe.normalize_speaker_label(None), "Unknown")

    def test_diarized_segments_to_utterances_preserves_speaker_text_and_timestamps(self) -> None:
        """diarized segment payload를 내부 TranscriptUtterance 목록으로 변환합니다."""
        segments = [
            {
                "speaker": "speaker_1",
                "text": "오늘 회의는 네 가지 안건입니다.",
                "start": 1.2,
                "end": 4.5,
            },
            {
                "speaker": "SPEAKER 2",
                "text": "4월 매출이 증가했습니다.",
                "start": 4.8,
                "end": 8.0,
            },
            {"speaker": "Speaker 3", "text": "   "},
        ]

        utterances = transcribe.diarized_segments_to_utterances(segments)

        self.assertEqual(len(utterances), 2)
        self.assertEqual(utterances[0].utterance_id, "u_0001")
        self.assertEqual(utterances[0].speaker, "Speaker 1")
        self.assertEqual(utterances[0].text, "오늘 회의는 네 가지 안건입니다.")
        self.assertEqual(utterances[0].start_ms, 1200)
        self.assertEqual(utterances[0].end_ms, 4500)
        self.assertEqual(utterances[1].utterance_id, "u_0002")
        self.assertEqual(utterances[1].speaker, "Speaker 2")
        self.assertEqual(utterances[1].start_ms, 4800)
        self.assertEqual(utterances[1].end_ms, 8000)

    def test_diarized_segments_to_utterances_uses_unknown_speaker_and_optional_timestamps(self) -> None:
        """speaker나 timestamp가 비어 있어도 내부 발화로 변환할 수 있습니다."""
        utterances = transcribe.diarized_segments_to_utterances(
            [
                {
                    "speaker": "",
                    "text": "화자 정보가 없습니다.",
                    "start": None,
                    "end": "not-a-number",
                }
            ]
        )

        self.assertEqual(utterances[0].speaker, "Unknown")
        self.assertIsNone(utterances[0].start_ms)
        self.assertIsNone(utterances[0].end_ms)
        self.assertEqual(utterances[0].render_for_llm(), "[u_0001] Unknown: 화자 정보가 없습니다.")

    def test_diarized_segments_to_normalized_transcript_renders_for_llm(self) -> None:
        """diarized segment payload를 NormalizedTranscript로 연결합니다."""
        normalized = transcribe.diarized_segments_to_normalized_transcript(
            [
                {"speaker": "Speaker 1", "text": "오늘 회의는 네 가지 안건입니다."},
                {"speaker": "Speaker 2", "text": "4월 매출이 증가했습니다."},
            ]
        )

        self.assertEqual(
            normalized.text,
            "Speaker 1: 오늘 회의는 네 가지 안건입니다.\nSpeaker 2: 4월 매출이 증가했습니다.",
        )
        self.assertEqual(
            normalized.render_for_llm(),
            "[u_0001] Speaker 1: 오늘 회의는 네 가지 안건입니다.\n[u_0002] Speaker 2: 4월 매출이 증가했습니다.",
        )

    def test_get_transcription_model_uses_env_override(self) -> None:
        """환경 변수로 STT 모델명을 덮어쓸 수 있습니다."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(transcribe.get_transcription_model(), "gpt-4o-transcribe")
        with patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_MODEL": "custom-stt"}):
            self.assertEqual(transcribe.get_transcription_model(), "custom-stt")

    def test_get_diarized_transcription_model_uses_env_override(self) -> None:
        """환경 변수로 diarized STT 모델명을 덮어쓸 수 있습니다."""
        with patch.dict(os.environ, {"OPENAI_DIARIZED_TRANSCRIPTION_MODEL": "custom-diarized-stt"}):
            self.assertEqual(transcribe.get_diarized_transcription_model(), "custom-diarized-stt")

    def test_get_transcription_language_defaults_to_korean_and_allows_env_override(self) -> None:
        """STT 언어 힌트는 기본 한국어이고 환경 변수로 덮어쓸 수 있습니다."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(transcribe.get_transcription_language(), "ko")
        with patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_LANGUAGE": "en"}):
            self.assertEqual(transcribe.get_transcription_language(), "en")

    def test_get_plain_transcription_concurrency_defaults_and_clamps_env(self) -> None:
        """plain STT 동시성은 기본값과 안전한 상한/하한을 적용합니다."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(transcribe.get_plain_transcription_concurrency(), 3)
        with patch.dict(os.environ, {"PLAIN_TRANSCRIPTION_CONCURRENCY": "4"}):
            self.assertEqual(transcribe.get_plain_transcription_concurrency(), 4)
        with patch.dict(os.environ, {"PLAIN_TRANSCRIPTION_CONCURRENCY": "0"}):
            self.assertEqual(transcribe.get_plain_transcription_concurrency(), 1)
        with patch.dict(os.environ, {"PLAIN_TRANSCRIPTION_CONCURRENCY": "20"}):
            self.assertEqual(transcribe.get_plain_transcription_concurrency(), 5)

    def test_get_trace_prefix_includes_human_readable_timestamp(self) -> None:
        """trace prefix는 사람이 읽기 쉬운 시각과 고정 marker를 포함합니다."""
        with patch.object(transcribe, "get_trace_timestamp", return_value="12:34:56"):
            self.assertEqual(transcribe.get_trace_prefix(), "[12:34:56][TRANSCRIBE_TRACE]")

    def test_build_timing_summary_computes_chunk_latency_metadata(self) -> None:
        """timing summary helper는 chunk 평균/최대/총 elapsed metadata를 만듭니다."""
        stats = transcribe.TranscriptionTimingStats(
            mode="diarized",
            model_name="mock-diarized-stt",
            chunk_config=transcribe.AudioChunkConfig(duration_seconds=150, overlap_seconds=0),
        )
        stats.total_chunks = 3
        stats.preparation_seconds = 2.0
        stats.merge_seconds = 0.5
        stats.retry_count = 1
        stats.chunk_elapsed_seconds = [10.0, 20.0, 30.0]

        summary = transcribe.build_timing_summary(stats)

        self.assertEqual(summary["mode"], "diarized")
        self.assertEqual(summary["model"], "mock-diarized-stt")
        self.assertEqual(summary["total_chunks"], 3)
        self.assertEqual(summary["completed_chunks"], 3)
        self.assertEqual(summary["avg_chunk_seconds"], 20.0)
        self.assertEqual(summary["slowest_chunk_seconds"], 30.0)
        self.assertEqual(summary["retry_count"], 1)
        self.assertEqual(summary["chunk_duration_seconds"], 150)

    def test_get_audio_chunk_config_uses_plain_safe_duration_default(self) -> None:
        """plain mode도 실제 긴 녹음에서는 시간 기준 청크 검증을 사용합니다."""
        with patch.dict(os.environ, {}, clear=True):
            chunk_config = transcribe.get_audio_chunk_config("plain")

        self.assertEqual(chunk_config.duration_seconds, 300)
        self.assertEqual(chunk_config.overlap_seconds, 0)

    def test_get_audio_chunk_config_uses_diarized_env_overrides(self) -> None:
        """diarized mode는 전용 청크 길이와 overlap 환경 변수를 사용합니다."""
        with patch.dict(
            os.environ,
            {
                "DIARIZED_CHUNK_DURATION_SECONDS": "180",
                "DIARIZED_CHUNK_OVERLAP_SECONDS": "7",
            },
        ):
            chunk_config = transcribe.get_audio_chunk_config("diarized")

        self.assertEqual(chunk_config.duration_seconds, 180)
        self.assertEqual(chunk_config.overlap_seconds, 7)

    def test_get_audio_chunk_config_defaults_diarized_to_short_chunks(self) -> None:
        """diarized mode 기본값은 긴 회의를 작은 시간 청크로 나누도록 설정됩니다."""
        with patch.dict(os.environ, {}, clear=True):
            chunk_config = transcribe.get_audio_chunk_config("diarized")

        self.assertEqual(chunk_config.duration_seconds, 150)
        self.assertEqual(chunk_config.overlap_seconds, 0)

    def test_extract_diarized_segments_supports_common_response_shapes(self) -> None:
        """dict, 객체, list provider 응답에서 diarized segments를 추출합니다."""
        segments = [{"speaker": "Speaker 1", "text": "회의를 시작합니다."}]

        self.assertEqual(transcribe.extract_diarized_segments(segments), segments)
        self.assertEqual(transcribe.extract_diarized_segments({"segments": segments}), segments)
        self.assertEqual(transcribe.extract_diarized_segments({"diarized_segments": segments}), segments)
        self.assertEqual(transcribe.extract_diarized_segments(types.SimpleNamespace(segments=segments)), segments)

    def test_extract_diarized_segments_normalizes_provider_field_aliases(self) -> None:
        """provider segment의 speaker/text/timestamp alias를 공통 shape로 정리합니다."""
        response = types.SimpleNamespace(
            segments=[
                types.SimpleNamespace(
                    speaker_label="speaker_1",
                    transcript="회의를 시작합니다.",
                    start_time=1.2,
                    end_time=4.5,
                )
            ]
        )

        segments = transcribe.extract_diarized_segments(response)

        self.assertEqual(
            segments,
            [
                {
                    "speaker": "speaker_1",
                    "text": "회의를 시작합니다.",
                    "start": 1.2,
                    "end": 4.5,
                }
            ],
        )

    def test_transcribe_audio_joins_chunks_and_cleans_temp_files(self) -> None:
        """청크 transcript를 합치고 새로 생성된 임시 청크를 정리합니다."""
        original_file = Path("meeting.wav")
        temp_chunk = Path("/private/tmp/meeting_chunk_001.wav")

        with patch.dict(os.environ, {"PLAIN_TRANSCRIPTION_CONCURRENCY": "1"}), patch.object(
            transcribe, "prepare_audio_files", return_value=[original_file, temp_chunk]
        ), patch.object(
            transcribe, "transcribe_chunk", side_effect=[" first ", "second"]
        ), patch.object(transcribe, "log_transcription_run_diagnostics"), patch.object(
            transcribe, "cleanup_temp_files"
        ) as cleanup_mock:
            transcript = transcribe.transcribe_audio(original_file)

        self.assertEqual(transcript, "first\n\nsecond")
        cleanup_mock.assert_called_once_with([temp_chunk])

    def test_transcribe_audio_plain_mode_keeps_string_return(self) -> None:
        """기본 plain mode와 명시적 plain mode는 기존 string 반환을 유지합니다."""
        audio_file = Path("meeting.wav")

        with patch.dict(os.environ, {"PLAIN_TRANSCRIPTION_CONCURRENCY": "1"}), patch.object(
            transcribe, "prepare_audio_files", return_value=[audio_file]
        ), patch.object(
            transcribe, "normalize_audio_files", return_value=[audio_file]
        ), patch.object(transcribe, "log_transcription_run_diagnostics"), patch.object(
            transcribe, "transcribe_chunk", return_value="plain text"
        ), patch.object(transcribe, "cleanup_temp_files"):
            self.assertEqual(transcribe.transcribe_audio(audio_file), "plain text")
            self.assertEqual(transcribe.transcribe_audio(audio_file, mode="plain"), "plain text")

    def test_transcribe_audio_plain_passes_configured_concurrency(self) -> None:
        """plain workflow는 환경 변수로 설정한 동시성을 chunk helper에 전달합니다."""
        audio_file = Path("meeting.wav")
        captured: dict[str, int] = {}

        def transcribe_chunks_side_effect(**kwargs):
            captured["concurrency"] = kwargs["concurrency"]
            return ["plain text"]

        with patch.dict(os.environ, {"PLAIN_TRANSCRIPTION_CONCURRENCY": "4"}), patch.object(
            transcribe, "prepare_audio_files", return_value=[audio_file]
        ), patch.object(transcribe, "normalize_audio_files", return_value=[audio_file]), patch.object(
            transcribe, "log_transcription_run_diagnostics"
        ), patch.object(
            transcribe, "transcribe_plain_chunks_concurrently", side_effect=transcribe_chunks_side_effect
        ), patch.object(
            transcribe, "cleanup_temp_files"
        ):
            transcript = transcribe.transcribe_audio(audio_file)

        self.assertEqual(transcript, "plain text")
        self.assertEqual(captured["concurrency"], 4)

    def test_plain_concurrency_one_preserves_sequential_like_call_order(self) -> None:
        """동시성 1에서는 plain chunk 호출 순서가 기존 순차 흐름과 같습니다."""
        call_order: list[str] = []
        chunks = [Path("chunk_001.wav"), Path("chunk_002.wav"), Path("chunk_003.wav")]
        stats = transcribe.TranscriptionTimingStats(
            mode="plain",
            model_name="mock-stt",
            chunk_config=transcribe.AudioChunkConfig(duration_seconds=300, overlap_seconds=0),
            concurrency=1,
        )

        def transcribe_chunk_side_effect(audio_file, **kwargs):
            call_order.append(audio_file.name)
            return audio_file.stem

        with patch.object(transcribe, "transcribe_chunk", side_effect=transcribe_chunk_side_effect):
            transcripts = transcribe.transcribe_plain_chunks_concurrently(
                files_to_transcribe=chunks,
                chunk_config=stats.chunk_config,
                source_files=[Path("meeting.wav")],
                timing_stats=stats,
                model_name="mock-stt",
                concurrency=1,
            )

        self.assertEqual(call_order, ["chunk_001.wav", "chunk_002.wav", "chunk_003.wav"])
        self.assertEqual(transcripts, ["chunk_001", "chunk_002", "chunk_003"])

    def test_plain_concurrency_preserves_original_chunk_order(self) -> None:
        """늦게 끝난 chunk가 있어도 최종 transcript 순서는 원본 chunk 순서를 따릅니다."""
        chunks = [Path("chunk_001.wav"), Path("chunk_002.wav"), Path("chunk_003.wav")]
        stats = transcribe.TranscriptionTimingStats(
            mode="plain",
            model_name="mock-stt",
            chunk_config=transcribe.AudioChunkConfig(duration_seconds=300, overlap_seconds=0),
            concurrency=3,
        )

        def transcribe_chunk_side_effect(audio_file, **kwargs):
            if audio_file.name == "chunk_001.wav":
                time.sleep(0.03)
            return audio_file.stem

        with patch.object(transcribe, "transcribe_chunk", side_effect=transcribe_chunk_side_effect):
            transcripts = transcribe.transcribe_plain_chunks_concurrently(
                files_to_transcribe=chunks,
                chunk_config=stats.chunk_config,
                source_files=[Path("meeting.wav")],
                timing_stats=stats,
                model_name="mock-stt",
                concurrency=3,
            )

        self.assertEqual(transcripts, ["chunk_001", "chunk_002", "chunk_003"])

    def test_plain_concurrency_failed_chunk_raises_clear_error(self) -> None:
        """plain 병렬 처리 중 chunk 실패는 index와 path를 포함해 실패합니다."""
        chunks = [Path("chunk_001.wav"), Path("chunk_002.wav")]
        stats = transcribe.TranscriptionTimingStats(
            mode="plain",
            model_name="mock-stt",
            chunk_config=transcribe.AudioChunkConfig(duration_seconds=300, overlap_seconds=0),
            concurrency=2,
        )

        def transcribe_chunk_side_effect(audio_file, **kwargs):
            if audio_file.name == "chunk_002.wav":
                raise RuntimeError("provider down")
            return audio_file.stem

        with patch.object(transcribe, "transcribe_chunk", side_effect=transcribe_chunk_side_effect):
            with self.assertRaisesRegex(RuntimeError, "Plain transcription chunk failed index=2 path=chunk_002.wav"):
                transcribe.transcribe_plain_chunks_concurrently(
                    files_to_transcribe=chunks,
                    chunk_config=stats.chunk_config,
                    source_files=[Path("meeting.wav")],
                    timing_stats=stats,
                    model_name="mock-stt",
                    concurrency=2,
                )

    def test_transcribe_audio_plain_snapshots_model_for_all_chunks(self) -> None:
        """plain workflow는 시작 시 resolved model을 모든 chunk에 동일하게 사용합니다."""
        used_models: list[str] = []

        def create_side_effect(**kwargs):
            used_models.append(kwargs["model"])
            os.environ["OPENAI_TRANSCRIPTION_MODEL"] = "drifted-stt"
            return types.SimpleNamespace(text=Path(kwargs["file"].name).stem)

        create_mock = Mock(side_effect=create_side_effect)
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "meeting.wav"
            chunk_one = Path(temp_dir) / "chunk_001.wav"
            chunk_two = Path(temp_dir) / "chunk_002.wav"
            for path in (source_file, chunk_one, chunk_two):
                path.write_bytes(b"audio")

            diagnostic = transcribe.AudioChunkDiagnostic(path=chunk_one, duration_seconds=1.0, size_mb=0.001)
            with patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_MODEL": "snapshot-stt"}), patch.object(
                transcribe, "prepare_audio_files", return_value=[chunk_one, chunk_two]
            ), patch.object(transcribe, "normalize_audio_files", return_value=[source_file]), patch.object(
                transcribe, "log_transcription_run_diagnostics"
            ), patch.object(
                transcribe, "validate_chunk_before_transcription", return_value=diagnostic
            ), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.object(
                transcribe, "cleanup_temp_files"
            ):
                transcript = transcribe.transcribe_audio(source_file)

        self.assertEqual(transcript, "chunk_001\n\nchunk_002")
        self.assertEqual(used_models, ["snapshot-stt", "snapshot-stt"])

    def test_transcribe_audio_plain_can_switch_to_full_transcribe_model_for_ab_test(self) -> None:
        """plain workflow는 gpt-4o-transcribe override를 모든 chunk에 동일하게 적용합니다."""
        used_models: list[str] = []

        def create_side_effect(**kwargs):
            used_models.append(kwargs["model"])
            return types.SimpleNamespace(text=Path(kwargs["file"].name).stem)

        create_mock = Mock(side_effect=create_side_effect)
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "meeting.wav"
            chunk_one = Path(temp_dir) / "chunk_001.wav"
            chunk_two = Path(temp_dir) / "chunk_002.wav"
            for path in (source_file, chunk_one, chunk_two):
                path.write_bytes(b"audio")

            diagnostic = transcribe.AudioChunkDiagnostic(path=chunk_one, duration_seconds=1.0, size_mb=0.001)
            with patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_MODEL": "gpt-4o-transcribe"}), patch.object(
                transcribe, "prepare_audio_files", return_value=[chunk_one, chunk_two]
            ), patch.object(transcribe, "normalize_audio_files", return_value=[source_file]), patch.object(
                transcribe, "log_transcription_run_diagnostics"
            ), patch.object(
                transcribe, "validate_chunk_before_transcription", return_value=diagnostic
            ), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.object(
                transcribe, "cleanup_temp_files"
            ):
                transcript = transcribe.transcribe_audio(source_file)

        self.assertEqual(transcript, "chunk_001\n\nchunk_002")
        self.assertEqual(used_models, ["gpt-4o-transcribe", "gpt-4o-transcribe"])

    def test_transcribe_audio_diarized_uses_mocked_provider_segments(self) -> None:
        """diarized path는 provider wrapper 결과를 NormalizedTranscript로 변환합니다."""
        audio_file = Path("meeting.wav")
        segments = [
            {"speaker": "speaker_1", "text": "오늘 회의는 네 가지 안건입니다.", "start": 1.2, "end": 4.5},
            {"speaker": "Speaker 2", "text": "4월 매출이 증가했습니다.", "start": 4.8, "end": 8.0},
        ]

        with patch.object(transcribe, "prepare_audio_files", return_value=[audio_file]), patch.object(
            transcribe, "normalize_audio_files", return_value=[audio_file]
        ), patch.object(transcribe, "log_transcription_run_diagnostics"), patch.object(
            transcribe, "call_diarized_transcription_provider", return_value=segments
        ) as provider_mock, patch.object(
            transcribe, "cleanup_temp_files"
        ):
            normalized = transcribe.transcribe_audio_diarized(audio_file)

        provider_mock.assert_called_once()
        self.assertEqual(provider_mock.call_args.args, (audio_file,))
        self.assertEqual(normalized.utterances[0].speaker, "Speaker 1")
        self.assertEqual(normalized.utterances[0].start_ms, 1200)
        self.assertIn("[u_0001] Speaker 1: 오늘 회의는 네 가지 안건입니다.", normalized.render_for_llm())

    def test_transcribe_audio_diarized_does_not_use_plain_concurrency_helper(self) -> None:
        """diarized workflow는 plain 병렬 chunk helper를 사용하지 않습니다."""
        audio_file = Path("meeting.wav")

        with patch.object(transcribe, "prepare_audio_files", return_value=[audio_file]), patch.object(
            transcribe, "normalize_audio_files", return_value=[audio_file]
        ), patch.object(transcribe, "log_transcription_run_diagnostics"), patch.object(
            transcribe, "call_diarized_transcription_provider", return_value=[]
        ), patch.object(
            transcribe, "transcribe_plain_chunks_concurrently", side_effect=AssertionError("plain concurrency used")
        ), patch.object(
            transcribe, "cleanup_temp_files"
        ):
            normalized = transcribe.transcribe_audio_diarized(audio_file)

        self.assertEqual(normalized.text, "")

    def test_transcribe_audio_diarized_snapshots_model_for_all_chunks(self) -> None:
        """diarized workflow도 시작 시 resolved model을 모든 chunk에 동일하게 사용합니다."""
        used_models: list[str] = []

        def create_side_effect(**kwargs):
            used_models.append(kwargs["model"])
            os.environ["OPENAI_DIARIZED_TRANSCRIPTION_MODEL"] = "drifted-diarized-stt"
            return {"segments": [{"speaker": "Speaker 1", "text": Path(kwargs["file"].name).stem}]}

        create_mock = Mock(side_effect=create_side_effect)
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "meeting.wav"
            chunk_one = Path(temp_dir) / "chunk_001.wav"
            chunk_two = Path(temp_dir) / "chunk_002.wav"
            for path in (source_file, chunk_one, chunk_two):
                path.write_bytes(b"audio")

            diagnostic = transcribe.AudioChunkDiagnostic(path=chunk_one, duration_seconds=1.0, size_mb=0.001)
            with patch.dict(os.environ, {"OPENAI_DIARIZED_TRANSCRIPTION_MODEL": "snapshot-diarized-stt"}), patch.object(
                transcribe, "prepare_audio_files", return_value=[chunk_one, chunk_two]
            ), patch.object(transcribe, "normalize_audio_files", return_value=[source_file]), patch.object(
                transcribe, "log_transcription_run_diagnostics"
            ), patch.object(
                transcribe, "validate_chunk_before_transcription", return_value=diagnostic
            ), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.object(
                transcribe, "cleanup_temp_files"
            ):
                normalized = transcribe.transcribe_audio_diarized(source_file)

        self.assertEqual(normalized.text, "Speaker 1: chunk_001\nSpeaker 1: chunk_002")
        self.assertEqual(used_models, ["snapshot-diarized-stt", "snapshot-diarized-stt"])

    def test_transcribe_audio_diarized_mode_delegates_to_structured_path(self) -> None:
        """transcribe_audio의 diarized mode는 structured transcript 경로로 위임됩니다."""
        normalized = transcribe.diarized_segments_to_normalized_transcript(
            [{"speaker": "Speaker 1", "text": "회의를 시작합니다."}]
        )

        with patch.object(transcribe, "transcribe_audio_diarized", return_value=normalized) as diarized_mock:
            result = transcribe.transcribe_audio(Path("meeting.wav"), mode="diarized")

        diarized_mock.assert_called_once_with(Path("meeting.wav"))
        self.assertEqual(result, normalized)

    def test_transcribe_audio_diarized_wraps_provider_errors(self) -> None:
        """diarized provider 오류는 명확한 예외 메시지로 감쌉니다."""
        audio_file = Path("meeting.wav")

        with patch.object(transcribe, "prepare_audio_files", return_value=[audio_file]), patch.object(
            transcribe, "normalize_audio_files", return_value=[audio_file]
        ), patch.object(
            transcribe,
            "call_diarized_transcription_provider",
            side_effect=RuntimeError("provider down"),
        ), patch.object(transcribe, "cleanup_temp_files"):
            with self.assertRaisesRegex(RuntimeError, "Diarized audio transcription failed"):
                transcribe.transcribe_audio_diarized(audio_file)

    def test_call_diarized_transcription_provider_passes_required_options(self) -> None:
        """diarization 모델 호출에는 OpenAI 필수 옵션을 전달합니다."""
        create_mock = Mock(return_value={"segments": [{"speaker": "Speaker 1", "text": "회의를 시작합니다."}]})
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.dict(os.environ, {"OPENAI_DIARIZED_TRANSCRIPTION_MODEL": "mock-diarized-stt"}, clear=True):
                segments = transcribe.call_diarized_transcription_provider(audio_file)

        self.assertEqual(segments, [{"speaker": "Speaker 1", "text": "회의를 시작합니다."}])
        self.assertEqual(create_mock.call_args.kwargs["model"], "mock-diarized-stt")
        self.assertEqual(create_mock.call_args.kwargs["language"], "ko")
        self.assertEqual(create_mock.call_args.kwargs["chunking_strategy"], "auto")
        self.assertEqual(create_mock.call_args.kwargs["response_format"], "diarized_json")

    def test_call_diarized_transcription_provider_uses_language_env_override(self) -> None:
        """diarized STT 호출에도 언어 환경 변수 override를 전달합니다."""
        create_mock = Mock(return_value={"segments": [{"speaker": "Speaker 1", "text": "meeting starts"}]})
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_LANGUAGE": "en"}):
                transcribe.call_diarized_transcription_provider(audio_file)

        self.assertEqual(create_mock.call_args.kwargs["language"], "en")

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

    def test_prepare_audio_files_plain_uses_plain_chunk_config(self) -> None:
        """plain mode 준비 단계는 기존 크기 기반 config로 분할 함수를 호출합니다."""
        audio_file = Path("meeting.wav")

        with patch.object(transcribe, "ensure_audio_file"), patch.object(
            transcribe, "split_audio_if_needed", return_value=[audio_file]
        ) as split_mock:
            prepared = transcribe.prepare_audio_files(audio_file, mode="plain")

        self.assertEqual(prepared, [audio_file])
        chunk_config = split_mock.call_args.kwargs["chunk_config"]
        self.assertEqual(chunk_config.duration_seconds, 300)
        self.assertEqual(chunk_config.overlap_seconds, 0)

    def test_prepare_audio_files_diarized_uses_diarized_chunk_config(self) -> None:
        """diarized mode 준비 단계는 전용 시간 청크 config를 전달합니다."""
        audio_file = Path("meeting.wav")

        with patch.object(transcribe, "ensure_audio_file"), patch.object(
            transcribe, "split_audio_if_needed", return_value=[audio_file]
        ) as split_mock, patch.dict(
            os.environ,
            {
                "DIARIZED_CHUNK_DURATION_SECONDS": "180",
                "DIARIZED_CHUNK_OVERLAP_SECONDS": "6",
            },
        ):
            prepared = transcribe.prepare_audio_files(audio_file, mode="diarized")

        self.assertEqual(prepared, [audio_file])
        chunk_config = split_mock.call_args.kwargs["chunk_config"]
        self.assertEqual(chunk_config.duration_seconds, 180)
        self.assertEqual(chunk_config.overlap_seconds, 6)

    def test_build_audio_chunk_diagnostic_returns_duration_and_size(self) -> None:
        """청크 진단 helper는 duration과 파일 크기를 함께 반환합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"x" * 1024 * 1024)

            with patch.object(transcribe, "get_audio_duration_seconds", return_value=12.5):
                diagnostic = transcribe.build_audio_chunk_diagnostic(audio_file)

        self.assertEqual(diagnostic.path, audio_file)
        self.assertEqual(diagnostic.duration_seconds, 12.5)
        self.assertAlmostEqual(diagnostic.size_mb, 1.0)

    def test_validate_chunk_before_transcription_rejects_oversized_duration(self) -> None:
        """전사 직전 guard는 설정 길이를 초과한 의심 청크를 차단합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            with patch.object(transcribe, "get_audio_duration_seconds", return_value=190.0):
                with self.assertRaisesRegex(RuntimeError, "audio chunk is too long"):
                    transcribe.validate_chunk_before_transcription(
                        audio_file,
                        "diarized",
                        transcribe.AudioChunkConfig(duration_seconds=150, overlap_seconds=0),
                        [audio_file],
                    )

    def test_transcribe_chunk_uses_chunk_verification(self) -> None:
        """plain chunk 호출도 OpenAI 호출 전 chunk 검증을 거칩니다."""
        create_mock = Mock(return_value=types.SimpleNamespace(text="hello"))
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")
            diagnostic = transcribe.AudioChunkDiagnostic(path=audio_file, duration_seconds=1.0, size_mb=0.001)

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "validate_chunk_before_transcription"
            ) as validate_mock, patch.object(transcribe, "create_openai_client", return_value=fake_client):
                validate_mock.return_value = diagnostic
                transcribe.transcribe_chunk(audio_file)

        validate_mock.assert_called_once()
        self.assertEqual(validate_mock.call_args.args[1], "plain")

    def test_call_diarized_transcription_provider_uses_chunk_verification(self) -> None:
        """diarized chunk 호출도 OpenAI 호출 전 chunk 검증을 거칩니다."""
        create_mock = Mock(return_value={"segments": [{"speaker": "Speaker 1", "text": "회의를 시작합니다."}]})
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")
            diagnostic = transcribe.AudioChunkDiagnostic(path=audio_file, duration_seconds=1.0, size_mb=0.001)

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "validate_chunk_before_transcription"
            ) as validate_mock, patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ):
                validate_mock.return_value = diagnostic
                transcribe.call_diarized_transcription_provider(audio_file)

        validate_mock.assert_called_once()
        self.assertEqual(validate_mock.call_args.args[1], "diarized")

    def test_diarized_input_too_large_retries_with_smaller_chunks(self) -> None:
        """input_too_large 오류는 실패한 diarized chunk를 더 작게 나눠 재시도합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")
            retry_one = Path(temp_dir) / "meeting_retry_001.wav"
            retry_two = Path(temp_dir) / "meeting_retry_002.wav"
            retry_one.write_bytes(b"audio")
            retry_two.write_bytes(b"audio")

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "validate_chunk_before_transcription"
            ), patch.object(
                transcribe,
                "call_diarized_transcription_provider_once",
                side_effect=[
                    RuntimeError("input_too_large: Total number of tokens in instructions + audio is too large"),
                    [{"speaker": "Speaker 1", "text": "첫 번째 재시도"}],
                    [{"speaker": "Speaker 2", "text": "두 번째 재시도"}],
                ],
            ) as provider_mock, patch.object(
                transcribe, "split_audio_if_needed", return_value=[retry_one, retry_two]
            ) as split_mock, patch.object(transcribe, "cleanup_temp_files"):
                segments = transcribe.call_diarized_transcription_provider_with_retry(
                    audio_file,
                    chunk_config=transcribe.AudioChunkConfig(duration_seconds=150, overlap_seconds=0),
                )

        self.assertEqual(provider_mock.call_count, 3)
        self.assertEqual(split_mock.call_args.kwargs["chunk_config"].duration_seconds, 75)
        self.assertEqual([segment["text"] for segment in segments], ["첫 번째 재시도", "두 번째 재시도"])

    def test_all_transcription_paths_use_shared_openai_wrapper(self) -> None:
        """plain과 diarized 경로 모두 공통 OpenAI 호출 래퍼를 통과합니다."""
        audio_file = Path("meeting.wav")

        with patch.object(
            transcribe,
            "call_openai_transcription",
            return_value=types.SimpleNamespace(text="plain text"),
        ) as wrapper_mock:
            result = transcribe.transcribe_chunk(audio_file)

        self.assertEqual(result, "plain text")
        self.assertEqual(wrapper_mock.call_args.kwargs["mode"], "plain")

        with patch.object(
            transcribe,
            "call_openai_transcription",
            return_value={"segments": [{"speaker": "Speaker 1", "text": "회의를 시작합니다."}]},
        ) as wrapper_mock:
            segments = transcribe.call_diarized_transcription_provider(audio_file)

        self.assertEqual(segments, [{"speaker": "Speaker 1", "text": "회의를 시작합니다."}])
        self.assertEqual(wrapper_mock.call_args.kwargs["mode"], "diarized")

    def test_structured_input_too_large_exception_triggers_retry(self) -> None:
        """OpenAI SDK의 structured input_too_large 예외도 재시도를 실행합니다."""

        class FakeOpenAIError(Exception):
            status_code = 400
            body = {
                "error": {
                    "code": "input_too_large",
                    "message": "Total number of tokens in instructions + audio is too large",
                }
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            retry_one = Path(temp_dir) / "meeting_retry_001.wav"
            retry_two = Path(temp_dir) / "meeting_retry_002.wav"
            for path in (audio_file, retry_one, retry_two):
                path.write_bytes(b"audio")

            with patch.object(
                transcribe,
                "call_openai_transcription",
                side_effect=[
                    FakeOpenAIError("bad request"),
                    {"segments": [{"speaker": "Speaker 1", "text": "첫 번째 재시도"}]},
                    {"segments": [{"speaker": "Speaker 2", "text": "두 번째 재시도"}]},
                ],
            ) as wrapper_mock, patch.object(
                transcribe, "split_audio_if_needed", return_value=[retry_one, retry_two]
            ), patch.object(
                transcribe, "cleanup_temp_files"
            ):
                segments = transcribe.call_diarized_transcription_provider_with_retry(
                    audio_file,
                    chunk_config=transcribe.AudioChunkConfig(duration_seconds=150, overlap_seconds=0),
                )

        self.assertEqual(wrapper_mock.call_count, 3)
        self.assertEqual([segment["text"] for segment in segments], ["첫 번째 재시도", "두 번째 재시도"])

    def test_openai_wrapper_logs_diagnostics_before_send(self) -> None:
        """공통 OpenAI 래퍼는 전송 전에 chunk 검증과 진단을 먼저 실행합니다."""
        events: list[str] = []

        def validate_side_effect(*args, **kwargs):
            events.append("validate")
            return transcribe.AudioChunkDiagnostic(path=args[0], duration_seconds=1.0, size_mb=0.001)

        def create_side_effect(**kwargs):
            events.append("openai")
            return types.SimpleNamespace(text="hello")

        create_mock = Mock(side_effect=create_side_effect)
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "validate_chunk_before_transcription", side_effect=validate_side_effect
            ), patch.object(transcribe, "create_openai_client", return_value=fake_client):
                transcribe.call_openai_transcription(
                    audio_file=audio_file,
                    mode="plain",
                    chunk_config=transcribe.AudioChunkConfig(duration_seconds=300, overlap_seconds=0),
                    source_files=[audio_file],
                )

        self.assertEqual(events, ["validate", "openai"])

    def test_input_too_large_retry_depth_is_bounded(self) -> None:
        """input_too_large 재시도는 최대 깊이에서 명확히 중단됩니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            with self.assertRaisesRegex(RuntimeError, "still too large"):
                transcribe.split_chunk_for_input_too_large(
                    audio_file=audio_file,
                    mode="diarized",
                    chunk_config=transcribe.AudioChunkConfig(duration_seconds=60, overlap_seconds=0),
                    retry_depth=transcribe.INPUT_TOO_LARGE_MAX_RETRY_DEPTH,
                    original_error=RuntimeError("input_too_large"),
                )

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
            ), patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_MODEL": "mock-stt"}, clear=True):
                result = transcribe.transcribe_chunk(audio_file)

        self.assertEqual(result, "hello")
        self.assertEqual(create_mock.call_args.kwargs["model"], "mock-stt")
        self.assertEqual(create_mock.call_args.kwargs["language"], "ko")
        self.assertNotIn("chunking_strategy", create_mock.call_args.kwargs)

    def test_transcribe_chunk_uses_language_env_override(self) -> None:
        """plain STT 호출에도 언어 환경 변수 override를 전달합니다."""
        create_mock = Mock(return_value=types.SimpleNamespace(text="hello"))
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_LANGUAGE": "en"}):
                transcribe.transcribe_chunk(audio_file)

        self.assertEqual(create_mock.call_args.kwargs["language"], "en")


if __name__ == "__main__":
    unittest.main()
