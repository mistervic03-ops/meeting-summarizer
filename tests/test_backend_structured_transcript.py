"""plain transcript API/storage 하네스 단위 테스트입니다."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
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
from backend.services import pipeline as backend_pipeline
from backend.schemas import JobResultResponse, TranscriptJobRequest, TranscriptResultResponse
from backend.services.pipeline import (
    build_summary_progress_callback,
    run_transcript_summary_pipeline,
    run_transcription_pipeline,
)


class BackendPlainTranscriptTests(unittest.TestCase):
    """plain transcript API/storage 흐름을 확인합니다."""

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
        """plain transcript request는 transcript와 metadata만 파싱합니다."""
        request = TranscriptJobRequest(filename="meeting.txt", transcript="plain text", context="")

        self.assertEqual(request.transcript, "plain text")
        self.assertEqual(request.meeting_type, "general")
        self.assertIsNone(request.transcription_job_id)

    def test_transcript_job_request_accepts_transcription_job_id(self) -> None:
        """transcript job request는 원본 STT job id를 선택적으로 받을 수 있습니다."""
        request = TranscriptJobRequest(
            filename="meeting.txt",
            transcript="plain text",
            transcription_job_id="stt-job-id",
        )

        self.assertEqual(request.transcription_job_id, "stt-job-id")

    def test_transcript_result_response_serializes_plain_transcript(self) -> None:
        """transcript result response는 plain transcript를 직렬화합니다."""
        response = TranscriptResultResponse(
            job_id="job",
            filename="meeting.wav",
            meeting_type="customer_meeting",
            transcript="오늘 회의는 네 가지 안건입니다.",
        )

        dumped = response.model_dump() if hasattr(response, "model_dump") else response.dict()

        self.assertEqual(dumped["transcript"], "오늘 회의는 네 가지 안건입니다.")
        self.assertEqual(dumped["meeting_type"], "customer_meeting")

    def test_job_result_response_serializes_meeting_type(self) -> None:
        """회의록 결과 응답은 result header에 표시할 meeting_type을 포함합니다."""
        response = JobResultResponse(job_id="job", filename="meeting.txt", meeting_type="technical_review", transcript="", minutes="")

        dumped = response.model_dump() if hasattr(response, "model_dump") else response.dict()

        self.assertEqual(dumped["meeting_type"], "technical_review")

    def test_storage_keeps_plain_transcript_without_structured_data(self) -> None:
        """storage는 plain transcript를 저장합니다."""
        job = storage.create_job("meeting.wav")

        storage.mark_job_transcribed(job.id, "plain text")

        self.assertEqual(storage.get_job(job.id).result.transcript, "plain text")

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
        self.assertEqual(updated_job.progress, 38)
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

    def test_delete_meeting_record_removes_row_and_artifact_files(self) -> None:
        """meeting 삭제는 세션 소유권을 확인하고 연결된 artifact 파일을 제거합니다."""
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

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_dir = Path(temp_dir) / "meeting"
            artifact_dir.mkdir()
            transcript_path = artifact_dir / "transcript.txt"
            summary_path = artifact_dir / "summary.txt"
            transcript_path.write_text("transcript", encoding="utf-8")
            summary_path.write_text("summary", encoding="utf-8")
            connection.execute(
                """
                INSERT INTO meetings(id, session_id, title, status, created_at, expires_at, transcript_path, summary_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "meeting-id",
                    "session-id",
                    "meeting.wav",
                    "completed",
                    "created",
                    "expires",
                    str(transcript_path),
                    str(summary_path),
                ),
            )

            try:
                with patch("backend.api.routes.get_db_connection", return_value=connection):
                    self.assertIsNone(routes.delete_meeting_record("meeting-id", "other-session"))
                    artifact_paths = routes.delete_meeting_record("meeting-id", "session-id")

                self.assertEqual(artifact_paths, (str(transcript_path), str(summary_path)))
                self.assertIsNone(connection.execute("SELECT id FROM meetings WHERE id = ?", ("meeting-id",)).fetchone())

                routes.remove_text_artifacts(*artifact_paths)

                self.assertFalse(transcript_path.exists())
                self.assertFalse(summary_path.exists())
                self.assertFalse(artifact_dir.exists())
            finally:
                connection.close()

    def test_transcription_pipeline_plain_mode_keeps_existing_string_flow(self) -> None:
        """transcription pipeline은 plain transcript만 저장합니다."""
        job = storage.create_job("meeting.wav")

        with patch("backend.services.pipeline.transcribe_audio", return_value="plain transcript") as transcribe_mock, patch(
            "backend.services.pipeline.mark_job_progress",
            wraps=backend_pipeline.mark_job_progress,
        ) as progress_mock:
            run_transcription_pipeline(job.id, Path("meeting.wav"), meeting_type="execution")

        transcribe_mock.assert_called_once_with(Path("meeting.wav"), progress_callback=ANY, stt_provider=None)
        self.assertEqual([call.args[1] for call in progress_mock.call_args_list], [15, 90, 100])
        self.assertEqual(storage.get_job(job.id).result.transcript, "plain transcript")
        self.assertEqual(storage.get_job(job.id).meeting_type, "execution")

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

    def test_stt_chunk_progress_uses_10_to_80_percent_range(self) -> None:
        """STT chunk 진행률은 10%에서 시작해 80%까지 올라갑니다."""
        job = storage.create_job("meeting.wav")
        storage.mark_job_processing(job.id)

        storage.mark_job_chunk_progress(job.id, completed_chunks=0, total_chunks=10)
        self.assertEqual(storage.get_job(job.id).progress, 10)

        storage.mark_job_chunk_progress(job.id, completed_chunks=5, total_chunks=10)
        self.assertEqual(storage.get_job(job.id).progress, 45)

        storage.mark_job_chunk_progress(job.id, completed_chunks=10, total_chunks=10)
        self.assertEqual(storage.get_job(job.id).progress, 80)

    def test_summary_progress_callback_uses_summary_stage_range(self) -> None:
        """요약 progress callback은 독립 summary job 기준 구간으로 job 상태를 갱신합니다."""
        job = storage.create_job("meeting.txt")
        storage.mark_job_processing(job.id)
        callback = build_summary_progress_callback(job.id)

        callback("normalized", {})
        self.assertEqual(storage.get_job(job.id).progress, 25)
        self.assertEqual(storage.get_job(job.id).message, "회의 내용을 분석하는 중입니다.")

        callback("strategy_selected", {"strategy": "chunk"})
        self.assertEqual(storage.get_job(job.id).progress, 35)
        self.assertEqual(storage.get_job(job.id).message, "청크 단위로 구조를 추출합니다.")

        callback("chunk_progress", {"completed_chunks": 1, "total_chunks": 2})
        self.assertEqual(storage.get_job(job.id).progress, 55)
        self.assertEqual(storage.get_job(job.id).message, "청크 단위로 구조를 추출합니다. 1/2 구간 완료")

        callback("extraction_complete", {})
        self.assertEqual(storage.get_job(job.id).progress, 80)
        self.assertEqual(storage.get_job(job.id).message, "회의록을 작성하는 중입니다.")

        callback("minutes_complete", {})
        self.assertEqual(storage.get_job(job.id).progress, 88)
        self.assertEqual(storage.get_job(job.id).message, "결과를 정리하는 중입니다.")

    def test_transcript_summary_pipeline_uses_plain_transcript(self) -> None:
        """summary pipeline은 plain transcript 기준으로 요약합니다."""
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
                "오늘 회의는 네 가지 안건입니다.",
                context="",
            )

        summarize_mock.assert_called_once_with("오늘 회의는 네 가지 안건입니다.", context="", meeting_type="general", progress_callback=ANY)
        self.assertEqual(storage.get_job(job.id).result.transcript, "오늘 회의는 네 가지 안건입니다.")

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

        summarize_mock.assert_called_once_with("plain transcript", context="", meeting_type="customer_meeting", progress_callback=ANY)
        self.assertEqual(storage.get_job(job.id).meeting_type, "customer_meeting")

class BackendPipelineMeetingFailureTests(unittest.TestCase):
    """회의록 생성 실패가 영구 meeting row에 기록되는지 확인합니다."""

    def tearDown(self) -> None:
        """테스트가 만든 인메모리 job과 임시 디렉터리를 정리합니다."""
        for job_id in list(storage.JOBS):
            storage.cleanup_job_files(job_id)
        storage.JOBS.clear()

    def test_summary_pipeline_failure_marks_target_meeting_row_failed(self) -> None:
        """summary job id와 meeting row id가 분리되어도 실패 상태는 target row에 기록됩니다."""
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
            INSERT INTO meetings(id, session_id, title, status, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("meeting-row-id", "session-id", "meeting.wav", "pending", "created", "expires"),
        )
        job = storage.create_job("meeting.wav")

        try:
            with patch("backend.services.pipeline.get_db_connection", return_value=connection):
                with patch("backend.services.pipeline.summarize_transcript", side_effect=RuntimeError("bad json")):
                    run_transcript_summary_pipeline(
                        job.id,
                        "plain transcript",
                        meeting_record_id="meeting-row-id",
                    )

            row = connection.execute("SELECT status, error FROM meetings WHERE id = ?", ("meeting-row-id",)).fetchone()
            self.assertEqual(row["status"], "failed")
            self.assertEqual(row["error"], "bad json")
            self.assertEqual(storage.get_job(job.id).status, "failed")
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
