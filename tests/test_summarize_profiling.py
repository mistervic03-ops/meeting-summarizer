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

class SummarizeProfilingTests(unittest.TestCase):
    """기존 summarize.py 테스트를 도메인별로 분리한 테스트입니다."""

    def test_analyze_transcript_profile_counts_size_and_cues(self) -> None:
        """transcript profile은 발화 수와 보수적 cue count를 계산합니다."""
        transcript = """
김민수: 배포 확인은 제가 금요일까지 하겠습니다.
이서연: 방식은 FastAPI로 확정했고 이걸로 진행하기로 했습니다.
박지훈: 지연 리스크와 이슈가 있습니다.
최유진: 고객 요구 조건이 필요합니다.
""".strip()

        profile = summarize.analyze_transcript_profile(summarize.normalize_transcript(transcript))

        self.assertEqual(profile.utterance_count, 4)
        self.assertEqual(profile.action_cue_count, 3)
        self.assertEqual(profile.decision_cue_count, 3)
        self.assertEqual(profile.risk_cue_count, 3)
        self.assertEqual(profile.requirement_cue_count, 3)
        self.assertEqual(profile.estimated_complexity, "simple")

    def test_choose_processing_strategy_uses_direct_for_short_simple_transcript(self) -> None:
        """짧고 단순한 회의는 기본 Direct 전략을 유지합니다."""
        transcript = """
김민수: 오늘 진행 상황을 공유했습니다.
이서연: 네 확인했습니다.
""".strip()

        profile = summarize.analyze_transcript_profile(summarize.normalize_transcript(transcript))

        self.assertEqual(summarize.choose_processing_strategy(profile), "direct")

    def test_choose_processing_strategy_ignores_many_utterances_without_size_or_cues(self) -> None:
        """발화 수만 많은 transcript는 chunk 후보로 분류하지 않습니다."""
        lines = [
            f"{'김민수' if index % 2 == 0 else '이서연'}: 일반 논의 내용 {index}입니다."
            for index in range(80)
        ]

        profile = summarize.analyze_transcript_profile(summarize.normalize_transcript("\n".join(lines)))

        self.assertEqual(profile.utterance_count, 80)
        self.assertEqual(summarize.choose_processing_strategy(profile), "direct")

    def test_choose_processing_strategy_uses_chunk_for_high_cue_count(self) -> None:
        """cue가 많은 transcript는 길지 않아도 chunk 후보로 분류합니다."""
        lines = [
            f"{'김민수' if index % 2 == 0 else '이서연'}: 확인하고 정리해서 공유하겠습니다."
            for index in range(12)
        ]

        profile = summarize.analyze_transcript_profile(summarize.normalize_transcript("\n".join(lines)))

        self.assertEqual(profile.action_cue_count, 48)
        self.assertEqual(summarize.choose_processing_strategy(profile), "chunk")

    def test_choose_processing_strategy_uses_deep_for_very_high_cue_count(self) -> None:
        """cue가 매우 많은 transcript는 Deep 전략을 선택합니다."""
        lines = [
            f"{'김민수' if index % 2 == 0 else '이서연'}: 확인하고 정리해서 공유하겠습니다."
            for index in range(30)
        ]

        profile = summarize.analyze_transcript_profile(summarize.normalize_transcript("\n".join(lines)))

        self.assertEqual(profile.action_cue_count, 120)
        self.assertEqual(summarize.choose_processing_strategy(profile), "deep")


if __name__ == "__main__":
    unittest.main()
