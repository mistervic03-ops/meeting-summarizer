"""structured transcript API/storage 하네스 단위 테스트입니다."""

from __future__ import annotations

import sqlite3
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

fake_itsdangerous = types.SimpleNamespace(
    BadSignature=Exception,
    SignatureExpired=Exception,
    TimestampSigner=lambda secret: None,
)
sys.modules.setdefault("itsdangerous", fake_itsdangerous)

from backend.api import routes
from backend import storage
from backend.schemas import JobResultResponse, StructuredTranscriptPayload, TranscriptJobRequest, TranscriptResultResponse
from backend.services.pipeline import (
    build_normalized_transcript_from_structured_payload,
    run_transcript_summary_pipeline,
    run_transcription_pipeline,
)


def structured_payload_dict() -> dict:
    """테스트용 structured transcript dict를 반환합니다."""
    return {
        "utterances": [
            {
                "utterance_id": "u_0001",
                "speaker": "Speaker 1",
                "text": "오늘 회의는 네 가지 안건입니다.",
                "start_ms": 1200,
                "end_ms": 4500,
            }
        ]
    }


class BackendStructuredTranscriptTests(unittest.TestCase):
    """structured transcript optional API/storage 흐름을 확인합니다."""

    def setUp(self) -> None:
        """pipeline의 영구 DB artifact update는 이 단위 테스트에서 제외합니다."""
        self.update_meeting_artifacts_patch = patch(
            "backend.services.pipeline.update_meeting_artifacts",
            MagicMock(),
        )
        self.mark_meeting_failed_patch = patch(
            "backend.services.pipeline.mark_meeting_failed",
            MagicMock(),
        )
        self.update_meeting_artifacts_patch.start()
        self.mark_meeting_failed_patch.start()

    def tearDown(self) -> None:
        """테스트가 만든 인메모리 job과 임시 디렉터리를 정리합니다."""
        self.mark_meeting_failed_patch.stop()
        self.update_meeting_artifacts_patch.stop()
        for job_id in list(storage.JOBS):
            storage.cleanup_job_files(job_id)
        storage.JOBS.clear()

    def test_transcript_job_request_accepts_plain_transcript_only(self) -> None:
        """기존 plain transcript request는 structured field 없이도 파싱됩니다."""
        request = TranscriptJobRequest(filename="meeting.txt", transcript="plain text", context="")

        self.assertEqual(request.transcript, "plain text")
        self.assertEqual(request.meeting_type, "general")
        self.assertIsNone(request.structured_transcript)
        self.assertIsNone(request.transcription_job_id)

    def test_transcript_job_request_accepts_transcription_job_id(self) -> None:
        """transcript job request는 원본 STT job id를 선택적으로 받을 수 있습니다."""
        request = TranscriptJobRequest(
            filename="meeting.txt",
            transcript="plain text",
            transcription_job_id="stt-job-id",
        )

        self.assertEqual(request.transcription_job_id, "stt-job-id")

    def test_transcript_job_request_accepts_structured_transcript(self) -> None:
        """transcript job request는 optional structured transcript를 받을 수 있습니다."""
        request = TranscriptJobRequest(
            filename="meeting.txt",
            transcript="Speaker 1: 오늘 회의는 네 가지 안건입니다.",
            structured_transcript=structured_payload_dict(),
        )

        self.assertIsNotNone(request.structured_transcript)
        self.assertEqual(request.structured_transcript.utterances[0].utterance_id, "u_0001")
        self.assertEqual(request.structured_transcript.utterances[0].speaker, "Speaker 1")

    def test_transcript_result_response_serializes_optional_structured_transcript(self) -> None:
        """transcript result response는 structured transcript를 선택적으로 직렬화합니다."""
        response = TranscriptResultResponse(
            job_id="job",
            filename="meeting.wav",
            meeting_type="customer_meeting",
            transcript="Speaker 1: 오늘 회의는 네 가지 안건입니다.",
            structured_transcript=StructuredTranscriptPayload(**structured_payload_dict()),
        )

        dumped = response.model_dump() if hasattr(response, "model_dump") else response.dict()

        self.assertEqual(dumped["structured_transcript"]["utterances"][0]["speaker"], "Speaker 1")
        self.assertEqual(dumped["meeting_type"], "customer_meeting")
        self.assertEqual(dumped["structured_transcript"]["utterances"][0]["start_ms"], 1200)

    def test_job_result_response_serializes_meeting_type(self) -> None:
        """회의록 결과 응답은 result header에 표시할 meeting_type을 포함합니다."""
        response = JobResultResponse(job_id="job", filename="meeting.txt", meeting_type="technical_review", transcript="", minutes="")

        dumped = response.model_dump() if hasattr(response, "model_dump") else response.dict()

        self.assertEqual(dumped["meeting_type"], "technical_review")

    def test_storage_keeps_plain_transcript_without_structured_data(self) -> None:
        """storage는 structured transcript 없이 기존 plain transcript를 저장합니다."""
        job = storage.create_job("meeting.wav")

        storage.mark_job_transcribed(job.id, "plain text")

        self.assertEqual(storage.get_job(job.id).result.transcript, "plain text")
        self.assertIsNone(storage.get_job(job.id).result.structured_transcript)

    def test_storage_keeps_optional_structured_transcript(self) -> None:
        """storage는 STT 결과의 optional structured transcript를 함께 보관합니다."""
        job = storage.create_job("meeting.wav")
        structured_transcript = structured_payload_dict()

        storage.mark_job_transcribed(job.id, "plain text", structured_transcript=structured_transcript)

        self.assertEqual(storage.get_job(job.id).result.structured_transcript, structured_transcript)

    def test_storage_keeps_meeting_type_metadata(self) -> None:
        """storage는 작업별 meeting_type metadata를 보관합니다."""
        job = storage.create_job("meeting.wav")

        storage.set_job_meeting_type(job.id, "technical_review")

        self.assertEqual(storage.get_job(job.id).meeting_type, "technical_review")

    def test_storage_tracks_chunk_progress(self) -> None:
        """storage는 사용자용 STT 청크 진행률을 저장합니다."""
        job = storage.create_job("meeting.wav")

        storage.mark_job_processing(job.id)
        storage.mark_job_chunk_progress(job.id, completed_chunks=2, total_chunks=5)

        updated_job = storage.get_job(job.id)
        self.assertEqual(updated_job.completed_chunks, 2)
        self.assertEqual(updated_job.total_chunks, 5)
        self.assertEqual(updated_job.progress, 46)
        self.assertEqual(updated_job.stage, "음성 변환")
        self.assertIn("2/5 구간 완료", updated_job.message)

    def test_link_transcript_to_transcription_meeting_updates_existing_row(self) -> None:
        """회의록 job은 기존 STT meeting row id를 새 job id로 바꿔 연결합니다."""
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE meetings(
                id TEXT PRIMARY KEY,
                session_id TEXT,
                title TEXT,
                status TEXT,
                created_at TEXT,
                expires_at TEXT,
                transcript_path TEXT,
                summary_path TEXT,
                error TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO meetings(id, session_id, title, status, created_at, expires_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("stt-job-id", "session-id", "meeting.wav", "transcript_ready", "created", "expires", "old error"),
        )

        try:
            with patch("backend.api.routes.get_db_connection", return_value=connection):
                self.assertEqual(routes.get_meeting_title("stt-job-id", "session-id"), "meeting.wav")
                self.assertTrue(
                    routes.link_transcript_to_transcription_meeting(
                        "stt-job-id",
                        "summary-job-id",
                        "session-id",
                    )
                )
                self.assertFalse(
                    routes.link_transcript_to_transcription_meeting(
                        "missing-job-id",
                        "unused-job-id",
                        "session-id",
                    )
                )

            rows = connection.execute("SELECT id, title, status, error FROM meetings").fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], "summary-job-id")
            self.assertEqual(rows[0]["title"], "meeting.wav")
            self.assertEqual(rows[0]["status"], "pending")
            self.assertIsNone(rows[0]["error"])
        finally:
            connection.close()

    def test_backend_pipeline_builds_normalized_transcript_from_structured_payload(self) -> None:
        """backend pipeline helper는 structured payload를 내부 NormalizedTranscript로 바꿉니다."""
        normalized = build_normalized_transcript_from_structured_payload(structured_payload_dict())

        self.assertIsNotNone(normalized)
        self.assertEqual(normalized.utterances[0].utterance_id, "u_0001")
        self.assertEqual(normalized.utterances[0].speaker, "Speaker 1")
        self.assertIn("[u_0001] Speaker 1:", normalized.render_for_llm())

    def test_transcription_pipeline_plain_mode_keeps_existing_string_flow(self) -> None:
        """diarized mode가 꺼져 있으면 기존 plain transcript만 저장합니다."""
        job = storage.create_job("meeting.wav")

        with patch("backend.services.pipeline.transcribe_audio", return_value="plain transcript") as transcribe_mock:
            run_transcription_pipeline(job.id, Path("meeting.wav"), meeting_type="execution")

        transcribe_mock.assert_called_once_with(Path("meeting.wav"), progress_callback=ANY, stt_provider=None)
        self.assertEqual(storage.get_job(job.id).result.transcript, "plain transcript")
        self.assertEqual(storage.get_job(job.id).meeting_type, "execution")
        self.assertIsNone(storage.get_job(job.id).result.structured_transcript)

    def test_transcription_pipeline_passes_requested_stt_provider(self) -> None:
        """업로드 요청의 STT provider 선택은 전사 호출까지 전달됩니다."""
        job = storage.create_job("meeting.wav")

        with patch("backend.services.pipeline.transcribe_audio", return_value="cloud transcript") as transcribe_mock:
            run_transcription_pipeline(
                job.id,
                Path("meeting.wav"),
                meeting_type="execution",
                stt_provider="openai",
            )

        transcribe_mock.assert_called_once_with(Path("meeting.wav"), progress_callback=ANY, stt_provider="openai")
        self.assertEqual(storage.get_job(job.id).result.transcript, "cloud transcript")

    def test_transcript_summary_pipeline_preserves_structured_transcript_for_later_use(self) -> None:
        """summary pipeline은 structured transcript를 받되 요약은 plain transcript 기준으로 유지합니다."""
        job = storage.create_job("meeting.txt")
        structured_transcript = structured_payload_dict()
        summary = {
            "minutes": "회의록",
            "action_items": [],
            "summary_facts": [],
            "decisions": [],
            "speaker_highlights": [],
            "warnings": [],
        }

        with patch("backend.services.pipeline.summarize_transcript", return_value=summary) as summarize_mock:
            run_transcript_summary_pipeline(
                job.id,
                "Speaker 1: 오늘 회의는 네 가지 안건입니다.",
                context="",
                structured_transcript=structured_transcript,
            )

        summarize_mock.assert_called_once()
        self.assertEqual(summarize_mock.call_args.args, ("Speaker 1: 오늘 회의는 네 가지 안건입니다.",))
        self.assertEqual(summarize_mock.call_args.kwargs["context"], "")
        self.assertEqual(summarize_mock.call_args.kwargs["meeting_type"], "general")
        normalized = summarize_mock.call_args.kwargs["normalized_transcript"]
        self.assertEqual(normalized.render_for_llm(), "[u_0001] Speaker 1: 오늘 회의는 네 가지 안건입니다.")
        self.assertEqual(storage.get_job(job.id).result.structured_transcript, structured_transcript)

    def test_transcript_summary_pipeline_passes_meeting_type(self) -> None:
        """backend summary pipeline은 meeting_type을 summarize_transcript로 전달합니다."""
        job = storage.create_job("meeting.txt")
        summary = {
            "minutes": "회의록",
            "action_items": [],
            "summary_facts": [],
            "decisions": [],
            "speaker_highlights": [],
            "warnings": [],
        }

        with patch("backend.services.pipeline.summarize_transcript", return_value=summary) as summarize_mock:
            run_transcript_summary_pipeline(
                job.id,
                "plain transcript",
                context="",
                meeting_type="customer_meeting",
        )

        summarize_mock.assert_called_once_with("plain transcript", context="", meeting_type="customer_meeting")
        self.assertEqual(storage.get_job(job.id).meeting_type, "customer_meeting")

    def test_transcript_summary_pipeline_falls_back_to_plain_transcript_when_structured_payload_is_invalid(self) -> None:
        """structured payload가 비어 있거나 유효하지 않으면 기존 plain transcript 경로를 사용합니다."""
        job = storage.create_job("meeting.txt")
        summary = {
            "minutes": "회의록",
            "action_items": [],
            "summary_facts": [],
            "decisions": [],
            "speaker_highlights": [],
            "warnings": [],
        }

        with patch("backend.services.pipeline.summarize_transcript", return_value=summary) as summarize_mock:
            run_transcript_summary_pipeline(
                job.id,
                "plain transcript",
                context="",
                structured_transcript={"utterances": [{"speaker": "Speaker 1", "text": "   "}]},
            )

        summarize_mock.assert_called_once_with("plain transcript", context="", meeting_type="general")
        self.assertEqual(storage.get_job(job.id).result.transcript, "plain transcript")


if __name__ == "__main__":
    unittest.main()
