"""회의 요약 파이프라인 단위 테스트입니다."""

from __future__ import annotations

import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

from summarize_test_helpers import collect_schema_objects, empty_track_b_structure, schema_contains_key, summarize

class SummarizePipelineTests(unittest.TestCase):
    """기존 summarize.py 테스트를 도메인별로 분리한 테스트입니다."""

    def test_step_a_modules_are_reexported_from_summarize(self) -> None:
        """Step A로 이동한 models/schema/prompt 이름은 summarize에서 계속 참조됩니다."""
        from summarization.prompts import build_extraction_prompt
        from summarization.schemas import MEETING_STRUCTURE_SCHEMA

        self.assertEqual(summarize.PreprocessedTranscript.__module__, "summarization.models")
        self.assertEqual(summarize.MEETING_STRUCTURE_SCHEMA, MEETING_STRUCTURE_SCHEMA)
        self.assertEqual(
            summarize.build_extraction_prompt("회의 내용", "2026-05-14"),
            build_extraction_prompt("회의 내용", "2026-05-14"),
        )

    def test_step_b_validation_helpers_are_reexported_from_summarize(self) -> None:
        """Step B로 이동한 validation helper는 summarize에서 계속 참조됩니다."""
        from summarization.validation import format_display_warnings, normalize_action_owner, validate_structure

        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "제가",
                    "due_date": "",
                    "confidence": "high",
                    "source_quote": "",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        self.assertEqual(summarize.validate_structure.__module__, "summarization.validation")
        self.assertEqual(summarize.normalize_action_owner("제가"), normalize_action_owner("제가"))
        self.assertEqual(
            summarize.format_display_warnings(["배포 확인의 owner가 미정이다."]),
            format_display_warnings(["배포 확인의 owner가 미정이다."]),
        )
        self.assertEqual(
            summarize.validate_structure(structure, "김민수: 배포 확인하겠습니다."),
            validate_structure(structure, "김민수: 배포 확인하겠습니다."),
        )

    def test_step_c_normalization_and_profiling_are_reexported_from_summarize(self) -> None:
        """Step C로 이동한 normalization/profiling helper는 summarize에서 계속 참조됩니다."""
        from summarization.normalization import normalize_transcript, preprocess_transcript
        from summarization.profiling import analyze_transcript_profile, choose_processing_strategy

        transcript = """
회의일: 2026년 5월 14일
김민수: 아
김민수: 배포 확인은 금요일까지 하겠습니다.
이서연: 이걸로 확정하겠습니다.
""".strip()

        self.assertEqual(summarize.preprocess_transcript.__module__, "summarization.normalization")
        self.assertEqual(summarize.analyze_transcript_profile.__module__, "summarization.profiling")
        summarize_preprocessed = summarize.preprocess_transcript(transcript)
        module_preprocessed = preprocess_transcript(transcript)
        self.assertEqual(summarize_preprocessed.text, module_preprocessed.text)
        self.assertEqual(summarize_preprocessed.meeting_date, module_preprocessed.meeting_date)

        summarize_normalized = summarize.normalize_transcript(transcript)
        module_normalized = normalize_transcript(transcript)
        self.assertEqual(summarize_normalized.text, module_normalized.text)
        self.assertEqual(summarize_normalized.meeting_date, module_normalized.meeting_date)
        self.assertEqual(
            [utterance.utterance_id for utterance in summarize_normalized.utterances],
            [utterance.utterance_id for utterance in module_normalized.utterances],
        )
        summarize_profile = summarize.analyze_transcript_profile(summarize.normalize_transcript(transcript))
        module_profile = analyze_transcript_profile(normalize_transcript(transcript))
        self.assertEqual(summarize_profile.char_count, module_profile.char_count)
        self.assertEqual(summarize_profile.utterance_count, module_profile.utterance_count)
        self.assertEqual(summarize_profile.action_cue_count, module_profile.action_cue_count)
        self.assertEqual(summarize_profile.decision_cue_count, module_profile.decision_cue_count)
        self.assertEqual(summarize_profile.risk_cue_count, module_profile.risk_cue_count)
        self.assertEqual(summarize_profile.requirement_cue_count, module_profile.requirement_cue_count)
        self.assertEqual(summarize_profile.estimated_complexity, module_profile.estimated_complexity)
        self.assertEqual(
            summarize.choose_processing_strategy(summarize.analyze_transcript_profile(summarize.normalize_transcript(transcript))),
            choose_processing_strategy(analyze_transcript_profile(normalize_transcript(transcript))),
        )

    def test_remaining_modules_are_reexported_from_summarize(self) -> None:
        """남은 rendering/openai/extraction helper는 summarize에서 계속 참조됩니다."""
        from summarization.openai_utils import extract_response_text
        from summarization.rendering import build_summary_result, render_output

        structure = {
            "summary_facts": ["빠른 요약"],
            "decisions": [{"decision": "진행 확정", "status": "확정", "source_quote": "진행 확정"}],
            "action_items": [
                {
                    "task": "후속 작업",
                    "owner": "김민수",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "후속 작업은 김민수가 2026-05-20까지 진행합니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        self.assertEqual(summarize.render_output.__module__, "summarization.rendering")
        self.assertEqual(summarize.build_summary_result.__module__, "summarization.rendering")
        self.assertEqual(summarize.extract_response_text.__module__, "summarization.openai_utils")
        self.assertEqual(summarize.request_structured_structure.__module__, "summarization.extraction")
        self.assertEqual(summarize.extract_structure.__module__, "summarization.extraction")
        self.assertEqual(
            summarize.render_output(structure, "## 회의 요약\n내용"),
            render_output(structure, "## 회의 요약\n내용"),
        )
        self.assertEqual(
            summarize.extract_response_text({"output": [{"content": [{"text": "nested text"}]}]}),
            extract_response_text({"output": [{"content": [{"text": "nested text"}]}]}),
        )
        public_result = build_summary_result(structure, "최종 출력")
        self.assertEqual(public_result, summarize.build_summary_result(structure, "최종 출력"))
        self.assertNotIn("source_quote", public_result["action_items"][0])
        self.assertNotIn("source_utterance_ids", public_result["action_items"][0])
        self.assertNotIn("source_quote", public_result["decisions"][0])
        self.assertNotIn("source_utterance_ids", public_result["decisions"][0])

    def test_pipeline_orchestration_is_reexported_from_summarize(self) -> None:
        """pipeline orchestration 함수는 새 모듈과 summarize 양쪽에서 참조됩니다."""
        from summarization import pipeline

        self.assertEqual(summarize.summarize_transcript.__module__, "summarization.pipeline")
        self.assertEqual(summarize.summarize_meeting.__module__, "summarization.pipeline")
        self.assertEqual(summarize.run_timed_stage.__module__, "summarization.pipeline")
        self.assertEqual(summarize.generate_minutes.__module__, "summarization.pipeline")
        self.assertEqual(pipeline.run_timed_stage("테스트", lambda value: value + 1, 1)[0], 2)

    def test_summarize_transcript_runs_new_pipeline(self) -> None:
        """공개 인터페이스가 검증 단계를 포함한 파이프라인을 순서대로 호출합니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = empty_track_b_structure()

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ) as validate_mock, patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(summarize, "render_output", return_value="최종 출력") as render_mock:
            result = summarize.summarize_transcript("raw transcript")

        self.assertEqual(result["minutes"], "최종 출력")
        self.assertEqual(result["summary_facts"], [])
        self.assertEqual(result["action_items"], [])
        extract_mock.assert_called_once_with(
            "[u_0001] 정리된 transcript",
            "2026-05-14",
            "",
            "general",
            glossary_terms=ANY,
        )
        validate_mock.assert_called_once()
        self.assertEqual(validate_mock.call_args.args[0], structure)
        self.assertEqual(validate_mock.call_args.args[1], "정리된 transcript")
        self.assertEqual(validate_mock.call_args.args[2].text, "정리된 transcript")
        generate_mock.assert_called_once_with("정리된 transcript", structure, "", "general", glossary_terms=ANY)
        render_mock.assert_called_once_with(structure, "자연어 회의록", "general")

    def test_summarize_transcript_passes_context_to_model_steps(self) -> None:
        """팀 컨텍스트가 구조 추출과 회의록 생성 단계로 전달됩니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = empty_track_b_structure()

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ), patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(summarize, "render_output", return_value="최종 출력"):
            summarize.summarize_transcript("raw transcript", context="VIP 프로젝트: 중요 고객")

        extract_mock.assert_called_once_with(
            "[u_0001] 정리된 transcript",
            "2026-05-14",
            "VIP 프로젝트: 중요 고객",
            "general",
            glossary_terms=ANY,
        )
        generate_mock.assert_called_once_with("정리된 transcript", structure, "VIP 프로젝트: 중요 고객", "general", glossary_terms=ANY)

    def test_summarize_transcript_passes_meeting_type_to_extraction(self) -> None:
        """meeting_type은 구조 추출 단계까지 전달됩니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = empty_track_b_structure()

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ), patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(summarize, "render_output", return_value="최종 출력") as render_mock:
            summarize.summarize_transcript("raw transcript", meeting_type="technical_review")

        extract_mock.assert_called_once_with(
            "[u_0001] 정리된 transcript",
            "2026-05-14",
            "",
            "technical_review",
            glossary_terms=ANY,
        )
        generate_mock.assert_called_once_with("정리된 transcript", structure, "", "technical_review", glossary_terms=ANY)
        render_mock.assert_called_once_with(structure, "자연어 회의록", "technical_review")

    def test_summarize_transcript_defaults_unknown_meeting_type_to_general(self) -> None:
        """지원하지 않는 meeting_type은 general 정책으로 정규화됩니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = empty_track_b_structure()

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ), patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ), patch.object(summarize, "render_output", return_value="최종 출력"):
            summarize.summarize_transcript("raw transcript", meeting_type="unknown")

        extract_mock.assert_called_once_with(
            "[u_0001] 정리된 transcript",
            "2026-05-14",
            "",
            "general",
            glossary_terms=ANY,
        )

    def test_summarize_transcript_rejects_empty_input(self) -> None:
        """빈 transcript는 명확한 에러로 실패합니다."""
        with self.assertRaises(RuntimeError):
            summarize.summarize_transcript("   ")

    def test_summarize_transcript_returns_api_result_shape(self) -> None:
        """summarize_transcript는 API 응답에 필요한 구조형 결과를 반환합니다."""
        preprocessed = summarize.PreprocessedTranscript(
            "김민수: 후속 작업은 2026-05-20까지 진행합니다.\n회의 진행 확정",
            "2026-05-14",
        )
        structure = {
            "summary_facts": ["빠른 요약"],
            "decisions": [{"decision": "진행 확정", "status": "확정", "source_quote": "회의 진행 확정"}],
            "action_items": [
                {
                    "task": "후속 작업",
                    "owner": "김민수",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "후속 작업은 2026-05-20까지 진행합니다.",
                }
            ],
            "speaker_highlights": ["김민수가 후속 작업을 언급했습니다."],
            "warnings": ["확인 필요"],
        }

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ), patch.object(summarize, "generate_minutes", return_value="자연어 회의록"), patch.object(
            summarize, "render_output", return_value="최종 출력"
        ):
            result = summarize.summarize_transcript("raw transcript")

        self.assertEqual(
            set(result),
            {"minutes", "action_items", "summary_facts", "decisions", "speaker_highlights", "warnings"},
        )
        self.assertEqual(result["minutes"], "최종 출력")
        self.assertEqual(
            result["action_items"],
            [{"task": "후속 작업", "owner": "김민수", "due_date": "2026-05-20", "confidence": "high"}],
        )
        self.assertNotIn("source_quote", result["action_items"][0])
        self.assertNotIn("source_utterance_ids", result["action_items"][0])
        self.assertEqual(result["summary_facts"], structure["summary_facts"])
        self.assertEqual(result["decisions"], [{"decision": "진행 확정", "status": "확정"}])
        self.assertNotIn("source_quote", result["decisions"][0])
        self.assertNotIn("source_utterance_ids", result["decisions"][0])
        self.assertEqual(result["speaker_highlights"], structure["speaker_highlights"])
        self.assertEqual(result["warnings"], structure["warnings"])


if __name__ == "__main__":
    unittest.main()
