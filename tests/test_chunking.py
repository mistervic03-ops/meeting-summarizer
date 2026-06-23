"""합성 transcript fixture 기반 chunking 회귀 테스트입니다."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TESTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from test_fixtures import load_fixture_transcript, normalize_fixture


def empty_structure() -> dict[str, list]:
    """테스트용 빈 structure shape를 반환합니다."""
    return {
        "summary_facts": [],
        "decisions": [],
        "action_items": [],
        "speaker_highlights": [],
        "warnings": [],
    }


class TranscriptChunkingFixtureTests(unittest.TestCase):
    """fixture 기반 chunk 생성과 chunk pipeline helper를 확인합니다."""

    def test_long_fixture_segments_into_stable_overlapping_chunks(self) -> None:
        """긴 fixture는 안정적인 chunk_id와 overlap을 가진 여러 chunk로 나뉩니다."""
        from summarization.chunking import segment_transcript

        normalized = normalize_fixture("long_action_heavy_meeting.txt")
        chunks = segment_transcript(normalized, max_utterances=80, overlap_utterances=8)

        self.assertGreater(len(chunks), 1)
        self.assertEqual([chunk.chunk_id for chunk in chunks], [f"c_{index + 1:04d}" for index in range(len(chunks))])
        self.assertEqual(chunks[0].chunk_id, "c_0001")
        self.assertTrue(all(chunk.text.strip() for chunk in chunks))
        self.assertEqual(chunks[0].overlap_before_ids, [])
        self.assertEqual(len(chunks[0].overlap_after_ids), 8)
        self.assertEqual(chunks[0].overlap_after_ids, chunks[1].overlap_before_ids)
        self.assertEqual(len(chunks[1].overlap_after_ids), 8)
        self.assertEqual(chunks[1].overlap_after_ids, chunks[2].overlap_before_ids)
        self.assertEqual(chunks[-1].overlap_after_ids, [])

    def test_short_fixture_remains_direct_or_single_chunk(self) -> None:
        """짧은 fixture는 direct strategy이며 chunking해도 단일 chunk로 유지됩니다."""
        from summarization.chunking import segment_transcript
        from summarization.profiling import analyze_transcript_profile, choose_processing_strategy

        normalized = normalize_fixture("short_clear_meeting.txt")
        profile = analyze_transcript_profile(normalized)
        chunks = segment_transcript(normalized, max_utterances=80, overlap_utterances=8)

        self.assertEqual(choose_processing_strategy(profile), "direct")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, "c_0001")
        self.assertEqual(chunks[0].utterances, normalized.utterances)

    def test_long_fixture_is_deep_strategy_candidate(self) -> None:
        """cue가 매우 많은 fixture는 실제 profiling 기준으로 deep mode 대상입니다."""
        from summarization.profiling import analyze_transcript_profile, choose_processing_strategy

        profile = analyze_transcript_profile(normalize_fixture("long_action_heavy_meeting.txt"))

        self.assertEqual(profile.utterance_count, 207)
        self.assertEqual(choose_processing_strategy(profile), "deep")

    def test_extract_structure_by_chunks_extracts_each_chunk_and_merges_without_validation(self) -> None:
        """chunk runner는 chunk별 extract 후 merge하며 validate_structure를 호출하지 않습니다."""
        from summarization import chunk_pipeline
        from summarization.chunking import segment_transcript

        normalized = normalize_fixture("long_action_heavy_meeting.txt")
        expected_chunks = segment_transcript(normalized, max_utterances=80, overlap_utterances=8)
        extracted_structure = {**empty_structure(), "summary_facts": ["chunk fact"]}
        merged_structure = {**empty_structure(), "summary_facts": ["merged fact"]}

        with patch.object(chunk_pipeline, "extract_structure", return_value=extracted_structure) as extract_mock, patch.object(
            chunk_pipeline, "merge_structures", return_value=merged_structure
        ) as merge_mock, patch("summarization.validation.validate_structure") as validate_mock:
            result = chunk_pipeline.extract_structure_by_chunks(
                normalized,
                "2026-05-15",
                context="fixture test",
                max_utterances=80,
                overlap_utterances=8,
            )

        self.assertEqual(result, merged_structure)
        self.assertEqual(extract_mock.call_count, len(expected_chunks))
        self.assertCountEqual(
            [call.args for call in extract_mock.call_args_list],
            [(chunk.text, "2026-05-15", "fixture test") for chunk in expected_chunks],
        )
        merge_mock.assert_called_once()
        self.assertEqual(len(merge_mock.call_args.args[0]), len(expected_chunks))
        validate_mock.assert_not_called()

    def test_chunk_pipeline_uses_fixture_text_without_openai_when_extract_is_mocked(self) -> None:
        """mock extract를 사용하면 fixture 기반 chunk pipeline 테스트에서 OpenAI 호출이 없습니다."""
        from summarization import chunk_pipeline

        normalized = normalize_fixture("long_action_heavy_meeting.txt")

        with patch.object(chunk_pipeline, "extract_structure", return_value=empty_structure()) as extract_mock, patch.object(
            chunk_pipeline, "merge_structures", return_value=empty_structure()
        ):
            chunk_pipeline.extract_structure_by_chunks(normalized, "2026-05-15")

        self.assertGreater(extract_mock.call_count, 1)
        self.assertIn("PoC", load_fixture_transcript("long_action_heavy_meeting.txt"))


if __name__ == "__main__":
    unittest.main()
