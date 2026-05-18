"""structured transcript API/storage 하네스 단위 테스트입니다."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import storage
from backend.schemas import JobResultResponse, StructuredTranscriptPayload, TranscriptJobRequest, TranscriptResultResponse
from backend.services.pipeline import (
    build_normalized_transcript_from_structured_payload,
    run_transcript_summary_pipeline,
    run_transcription_pipeline,
)
from summarization.models import NormalizedTranscript, TranscriptUtterance


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


def normalized_diarized_transcript() -> NormalizedTranscript:
    """테스트용 diarized NormalizedTranscript를 반환합니다."""
    return NormalizedTranscript(
        utterances=[
            TranscriptUtterance(
                utterance_id="u_0001",
                speaker="Speaker 1",
                text="오늘 회의는 네 가지 안건입니다.",
                index=0,
                raw_line="Speaker 1: 오늘 회의는 네 가지 안건입니다.",
                start_ms=1200,
                end_ms=4500,
            ),
            TranscriptUtterance(
                utterance_id="u_0002",
                speaker="Speaker 2",
                text="4월 매출이 증가했습니다.",
                index=1,
                raw_line="Speaker 2: 4월 매출이 증가했습니다.",
                start_ms=4800,
                end_ms=8000,
            ),
        ],
        text="Speaker 1: 오늘 회의는 네 가지 안건입니다.\nSpeaker 2: 4월 매출이 증가했습니다.",
        meeting_date="",
    )


class BackendStructuredTranscriptTests(unittest.TestCase):
    """structured transcript optional API/storage 흐름을 확인합니다."""

    def tearDown(self) -> None:
        """테스트가 만든 인메모리 job과 임시 디렉터리를 정리합니다."""
        for job_id in list(storage.JOBS):
            storage.cleanup_job_files(job_id)
        storage.JOBS.clear()

    def test_transcript_job_request_accepts_plain_transcript_only(self) -> None:
        """기존 plain transcript request는 structured field 없이도 파싱됩니다."""
        request = TranscriptJobRequest(filename="meeting.txt", transcript="plain text", context="")

        self.assertEqual(request.transcript, "plain text")
        self.assertEqual(request.meeting_type, "general")
        self.assertIsNone(request.structured_transcript)

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

        with patch.dict("os.environ", {"TRANSCRIPTION_MODE": "plain"}), patch(
            "backend.services.pipeline.transcribe_audio", return_value="plain transcript"
        ) as transcribe_mock:
            run_transcription_pipeline(job.id, Path("meeting.wav"), meeting_type="execution")

        transcribe_mock.assert_called_once_with(Path("meeting.wav"))
        self.assertEqual(storage.get_job(job.id).result.transcript, "plain transcript")
        self.assertEqual(storage.get_job(job.id).meeting_type, "execution")
        self.assertIsNone(storage.get_job(job.id).result.structured_transcript)

    def test_transcription_pipeline_diarized_mode_stores_plain_and_structured_transcript(self) -> None:
        """diarized mode는 plain text와 structured transcript를 함께 저장합니다."""
        job = storage.create_job("meeting.wav")
        normalized = normalized_diarized_transcript()

        with patch.dict("os.environ", {"TRANSCRIPTION_MODE": "diarized"}), patch(
            "backend.services.pipeline.transcribe_audio", return_value=normalized
        ) as transcribe_mock:
            run_transcription_pipeline(job.id, Path("meeting.wav"))

        transcribe_mock.assert_called_once_with(Path("meeting.wav"), mode="diarized")
        result = storage.get_job(job.id).result
        self.assertEqual(result.transcript, normalized.text)
        self.assertEqual(result.structured_transcript["utterances"][0]["speaker"], "Speaker 1")
        self.assertEqual(result.structured_transcript["utterances"][0]["start_ms"], 1200)

        response = TranscriptResultResponse(
            job_id=job.id,
            filename=job.filename,
            transcript=result.transcript,
            structured_transcript=result.structured_transcript,
        )
        dumped = response.model_dump() if hasattr(response, "model_dump") else response.dict()
        self.assertEqual(dumped["structured_transcript"]["utterances"][1]["speaker"], "Speaker 2")

    def test_transcription_pipeline_diarized_failure_falls_back_to_plain_transcript(self) -> None:
        """diarized provider 실패 시 upload flow를 깨지 않고 plain STT로 fallback합니다."""
        job = storage.create_job("meeting.wav")

        with patch.dict("os.environ", {"TRANSCRIPTION_MODE": "diarized"}), patch(
            "backend.services.pipeline.transcribe_audio",
            side_effect=[RuntimeError("provider down"), "plain fallback"],
        ) as transcribe_mock:
            run_transcription_pipeline(job.id, Path("meeting.wav"))

        self.assertEqual(transcribe_mock.call_args_list[0].kwargs, {"mode": "diarized"})
        self.assertEqual(transcribe_mock.call_args_list[1].args, (Path("meeting.wav"),))
        result = storage.get_job(job.id).result
        self.assertEqual(result.transcript, "plain fallback")
        self.assertIsNone(result.structured_transcript)

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
