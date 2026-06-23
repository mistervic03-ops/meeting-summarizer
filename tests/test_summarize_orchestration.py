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

class SummarizeOrchestrationTests(unittest.TestCase):
    """기존 summarize.py 테스트를 도메인별로 분리한 테스트입니다."""

    def test_summarize_transcript_uses_direct_extraction_for_direct_strategy(self) -> None:
        """direct 전략은 기존 단일 extract_structure 흐름을 유지합니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = empty_track_b_structure()
        profile = summarize.TranscriptProfile(
            char_count=10,
            utterance_count=1,
            action_cue_count=0,
            decision_cue_count=0,
            risk_cue_count=0,
            requirement_cue_count=0,
            estimated_complexity="simple",
        )

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ) as validate_mock, patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(
            summarize, "render_output", return_value="최종 출력"
        ) as render_mock, patch.object(
            summarize, "analyze_transcript_profile", return_value=profile
        ) as profile_mock, patch.object(
            summarize, "choose_processing_strategy", return_value="direct"
        ) as strategy_mock, patch.object(summarize, "extract_structure_by_chunks", create=True) as chunk_runner_mock, patch.object(
            summarize.logger, "info"
        ) as log_mock:
            result = summarize.summarize_transcript("raw transcript")

        self.assertEqual(result["minutes"], "최종 출력")
        self.assertEqual(set(result), {"minutes", "action_items", "summary_facts", "decisions", "speaker_highlights", "warnings"})
        chunk_runner_mock.assert_not_called()
        profile_mock.assert_called_once()
        self.assertEqual(profile_mock.call_args.args[0].text, "정리된 transcript")
        strategy_mock.assert_called_once_with(profile)
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
        self.assertTrue(any(call.args == ("summarize_transcript selected_strategy=%s", "direct") for call in log_mock.call_args_list))
        self.assertTrue(
            any(
                call.args
                and call.args[0].startswith("transcript_profile char_count=%s utterance_count=%s")
                and call.args[-1] == "direct"
                for call in log_mock.call_args_list
            )
        )

    def test_summarize_transcript_reports_direct_progress_events(self) -> None:
        """summary pipeline은 direct 경로의 주요 진행 단계를 callback으로 알립니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = empty_track_b_structure()
        profile = summarize.TranscriptProfile(
            char_count=10,
            utterance_count=1,
            action_cue_count=0,
            decision_cue_count=0,
            risk_cue_count=0,
            requirement_cue_count=0,
            estimated_complexity="simple",
        )
        progress_events: list[tuple[str, dict]] = []

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ), patch.object(summarize, "validate_structure", return_value=structure), patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ), patch.object(summarize, "render_output", return_value="최종 출력"), patch.object(
            summarize, "analyze_transcript_profile", return_value=profile
        ), patch.object(summarize, "choose_processing_strategy", return_value="direct"):
            summarize.summarize_transcript(
                "raw transcript",
                progress_callback=lambda event, payload: progress_events.append((event, payload.copy())),
            )

        self.assertEqual(
            [event for event, _payload in progress_events],
            ["normalized", "strategy_selected", "extraction_complete", "minutes_complete"],
        )
        self.assertEqual(progress_events[1][1], {"strategy": "direct"})

    def test_summarize_transcript_uses_provided_normalized_transcript_without_renormalizing(self) -> None:
        """structured path는 제공된 NormalizedTranscript를 우선 사용하고 plain 재정규화를 건너뜁니다."""
        normalized = summarize.NormalizedTranscript(
            utterances=[
                summarize.TranscriptUtterance(
                    utterance_id="u_0099",
                    text="제가 고객사 통화 결과를 공유하겠습니다.",
                    index=0,
                    raw_line="제가 고객사 통화 결과를 공유하겠습니다.",
                )
            ],
            text="제가 고객사 통화 결과를 공유하겠습니다.",
            meeting_date="2026-05-14",
        )
        structure = empty_track_b_structure()
        profile = summarize.TranscriptProfile(
            char_count=30,
            utterance_count=1,
            action_cue_count=1,
            decision_cue_count=0,
            risk_cue_count=0,
            requirement_cue_count=0,
            estimated_complexity="simple",
        )

        with patch.object(summarize, "preprocess_transcript") as preprocess_mock, patch.object(
            summarize, "normalize_transcript"
        ) as normalize_mock, patch.object(
            summarize, "analyze_transcript_profile", return_value=profile
        ), patch.object(
            summarize, "choose_processing_strategy", return_value="direct"
        ), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ) as validate_mock, patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(summarize, "render_output", return_value="최종 출력"):
            result = summarize.summarize_transcript("plain fallback text", normalized_transcript=normalized)

        self.assertEqual(result["minutes"], "최종 출력")
        preprocess_mock.assert_not_called()
        normalize_mock.assert_not_called()
        extract_mock.assert_called_once_with(
            "[u_0099] 제가 고객사 통화 결과를 공유하겠습니다.",
            "2026-05-14",
            "",
            "general",
            glossary_terms=ANY,
        )
        validate_mock.assert_called_once()
        self.assertEqual(validate_mock.call_args.args[1], normalized.text)
        self.assertIs(validate_mock.call_args.args[2], normalized)
        generate_mock.assert_called_once_with(normalized.text, structure, "", "general", glossary_terms=ANY)

    def test_summarize_transcript_uses_chunk_extraction_for_chunk_strategy(self) -> None:
        """chunk 전략은 chunk runner 결과를 merge 후 validation으로 한 번만 넘깁니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        chunk_structure = {**empty_track_b_structure(), "summary_facts": ["chunk 결과"]}
        validated_structure = {**empty_track_b_structure(), "summary_facts": ["검증된 chunk 결과"]}
        profile = summarize.TranscriptProfile(
            char_count=9000,
            utterance_count=80,
            action_cue_count=0,
            decision_cue_count=0,
            risk_cue_count=0,
            requirement_cue_count=0,
            estimated_complexity="standard",
        )

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure"
        ) as extract_mock, patch.object(summarize, "validate_structure", return_value=validated_structure) as validate_mock, patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(summarize, "render_output", return_value="최종 출력") as render_mock, patch.object(
            summarize, "analyze_transcript_profile", return_value=profile
        ), patch.object(summarize, "choose_processing_strategy", return_value="chunk"), patch.object(
            summarize, "extract_structure_by_chunks", create=True, return_value=chunk_structure
        ) as chunk_runner_mock, patch.object(summarize.logger, "info") as log_mock:
            result = summarize.summarize_transcript("raw transcript")

        self.assertEqual(result["minutes"], "최종 출력")
        extract_mock.assert_not_called()
        chunk_runner_mock.assert_called_once()
        normalized_arg, meeting_date_arg, context_arg = chunk_runner_mock.call_args.args
        self.assertEqual(normalized_arg.text, "정리된 transcript")
        self.assertEqual(meeting_date_arg, "2026-05-14")
        self.assertEqual(context_arg, "")
        self.assertEqual(chunk_runner_mock.call_args.kwargs["meeting_type"], "general")
        self.assertEqual(chunk_runner_mock.call_args.kwargs["glossary_terms"], summarize.get_summary_glossary_terms())
        validate_mock.assert_called_once()
        self.assertEqual(validate_mock.call_args.args[0], chunk_structure)
        self.assertEqual(validate_mock.call_args.args[1], "정리된 transcript")
        self.assertEqual(validate_mock.call_args.args[2].text, "정리된 transcript")
        generate_mock.assert_called_once_with("정리된 transcript", validated_structure, "", "general", glossary_terms=ANY)
        render_mock.assert_called_once_with(validated_structure, "자연어 회의록", "general")
        self.assertTrue(any(call.args == ("summarize_transcript using chunk extraction path",) for call in log_mock.call_args_list))

    def test_summarize_transcript_reports_chunk_progress_events(self) -> None:
        """summary pipeline은 chunk 경로에서 chunk별 진행률 event를 전달합니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        chunk_structure = empty_track_b_structure()
        profile = summarize.TranscriptProfile(
            char_count=9000,
            utterance_count=80,
            action_cue_count=0,
            decision_cue_count=0,
            risk_cue_count=0,
            requirement_cue_count=0,
            estimated_complexity="standard",
        )
        progress_events: list[tuple[str, dict]] = []

        def extract_chunks_side_effect(*args, **kwargs):
            """요약 pipeline이 넘긴 chunk progress callback을 호출합니다."""
            kwargs["progress_callback"](1, 2)
            kwargs["progress_callback"](2, 2)
            return chunk_structure

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "validate_structure", return_value=chunk_structure
        ), patch.object(summarize, "generate_minutes", return_value="자연어 회의록"), patch.object(
            summarize, "render_output", return_value="최종 출력"
        ), patch.object(summarize, "analyze_transcript_profile", return_value=profile), patch.object(
            summarize, "choose_processing_strategy", return_value="chunk"
        ), patch.object(
            summarize,
            "extract_structure_by_chunks",
            create=True,
            side_effect=extract_chunks_side_effect,
        ):
            summarize.summarize_transcript(
                "raw transcript",
                progress_callback=lambda event, payload: progress_events.append((event, payload.copy())),
            )

        self.assertEqual(
            [event for event, _payload in progress_events],
            [
                "normalized",
                "strategy_selected",
                "chunk_progress",
                "chunk_progress",
                "extraction_complete",
                "minutes_complete",
            ],
        )
        self.assertEqual(progress_events[1][1], {"strategy": "chunk"})
        self.assertEqual(progress_events[2][1], {"completed_chunks": 1, "total_chunks": 2})
        self.assertEqual(progress_events[3][1], {"completed_chunks": 2, "total_chunks": 2})

    def test_summarize_transcript_loads_glossary_once_for_chunk_extraction(self) -> None:
        """chunk 경로에서도 요약 용어집은 summarize_transcript 단위로 한 번만 로드됩니다."""
        transcript = "\n".join(f"김민수: {index}번째 확인하겠습니다." for index in range(100))
        structure = empty_track_b_structure()
        glossary_terms = ["BigQuery", "Tableau"]

        with patch.object(summarize, "get_summary_glossary_terms", return_value=glossary_terms) as glossary_mock, patch.object(
            summarize,
            "extract_structure_by_chunks",
            create=True,
            return_value=structure,
        ) as chunk_runner_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ), patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(
            summarize, "render_output", return_value="최종 출력"
        ):
            summarize.summarize_transcript(transcript)

        glossary_mock.assert_called_once_with()
        chunk_runner_mock.assert_called_once()
        self.assertEqual(chunk_runner_mock.call_args.kwargs["glossary_terms"], glossary_terms)
        generate_mock.assert_called_once_with(ANY, structure, "", "general", glossary_terms=glossary_terms)

    def test_summarize_transcript_cleans_chunk_public_warnings(self) -> None:
        """chunk mode에서 병합된 raw warning도 공개 결과에서는 표시용 문장으로 정리합니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        chunk_structure = {
            **empty_track_b_structure(),
            "warnings": [
                "owner가 없음",
                "due_date가 '미정'인 항목이 있음",
                "confidence가 'low'인 항목이 있음",
                "source_quote가 없음",
            ],
        }
        profile = summarize.TranscriptProfile(
            char_count=9000,
            utterance_count=80,
            action_cue_count=0,
            decision_cue_count=0,
            risk_cue_count=0,
            requirement_cue_count=0,
            estimated_complexity="standard",
        )

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure"
        ) as extract_mock, patch.object(summarize, "extract_structure_by_chunks", create=True, return_value=chunk_structure), patch.object(
            summarize, "validate_structure", return_value=chunk_structure
        ), patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ), patch.object(summarize, "render_output", return_value="최종 출력"), patch.object(
            summarize, "analyze_transcript_profile", return_value=profile
        ), patch.object(summarize, "choose_processing_strategy", return_value="chunk"):
            result = summarize.summarize_transcript("raw transcript")

        extract_mock.assert_not_called()
        self.assertEqual(
            result["warnings"],
            [
                "담당자 확인이 필요한 액션 아이템이 있습니다.",
                "기한 확인이 필요한 액션 아이템이 있습니다.",
                "내용 확인이 필요한 항목이 있습니다.",
                "원문 근거 확인이 필요한 항목이 있습니다.",
            ],
        )
        self.assertFalse(
            any(
                internal_name in warning
                for warning in result["warnings"]
                for internal_name in ("owner", "due_date", "confidence", "source_quote")
            )
        )

    def test_summarize_transcript_uses_chunk_extraction_for_deep_strategy(self) -> None:
        """deep 전략은 아직 고급 처리 없이 chunk pipeline으로 안전하게 fallback합니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        chunk_structure = empty_track_b_structure()
        profile = summarize.TranscriptProfile(
            char_count=40000,
            utterance_count=240,
            action_cue_count=0,
            decision_cue_count=0,
            risk_cue_count=0,
            requirement_cue_count=0,
            estimated_complexity="complex",
        )

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure"
        ) as extract_mock, patch.object(summarize, "validate_structure", return_value=chunk_structure) as validate_mock, patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ), patch.object(summarize, "render_output", return_value="최종 출력"), patch.object(
            summarize, "analyze_transcript_profile", return_value=profile
        ), patch.object(summarize, "choose_processing_strategy", return_value="deep"), patch.object(
            summarize, "extract_structure_by_chunks", create=True, return_value=chunk_structure
        ) as chunk_runner_mock, patch.object(summarize.logger, "info") as log_mock:
            result = summarize.summarize_transcript("raw transcript")

        self.assertEqual(result["minutes"], "최종 출력")
        extract_mock.assert_not_called()
        chunk_runner_mock.assert_called_once()
        validate_mock.assert_called_once()
        self.assertEqual(validate_mock.call_args.args[0], chunk_structure)
        self.assertEqual(validate_mock.call_args.args[1], "정리된 transcript")
        self.assertEqual(validate_mock.call_args.args[2].text, "정리된 transcript")
        self.assertTrue(any(call.args == ("deep strategy currently uses chunk pipeline",) for call in log_mock.call_args_list))


if __name__ == "__main__":
    unittest.main()
