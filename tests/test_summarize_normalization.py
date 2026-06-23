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

class SummarizeNormalizationTests(unittest.TestCase):
    """기존 summarize.py 테스트를 도메인별로 분리한 테스트입니다."""

    def test_preprocess_removes_only_standalone_fillers(self) -> None:
        """단독 추임새만 제거하고 plain transcript 줄 구조를 유지합니다."""
        transcript = """
회의일: 2026년 5월 14일
아
네네 확인했습니다
배포는 금요일까지 진행하겠습니다.
음...
품질 검수를 맡겠습니다.
""".strip()

        result = summarize.preprocess_transcript(transcript)

        self.assertEqual(result.meeting_date, "2026-05-14")
        self.assertNotIn("\n아\n", result.text)
        self.assertIn("네네 확인했습니다", result.text)
        self.assertIn("배포는 금요일까지 진행하겠습니다.", result.text)
        self.assertIn("품질 검수를 맡겠습니다.", result.text)

    def test_normalize_transcript_creates_stable_utterance_ids_without_changing_text(self) -> None:
        """normalize_transcript는 stable ID를 만들고 기존 전처리 text와 같은 출력을 유지합니다."""
        transcript = """
회의일: 2026년 5월 14일
아
네네 확인했습니다
배포는 금요일까지 진행하겠습니다.
음...
품질 검수를 맡겠습니다.
""".strip()

        normalized = summarize.normalize_transcript(transcript)
        preprocessed = summarize.preprocess_transcript(transcript)

        self.assertEqual(normalized.text, preprocessed.text)
        self.assertEqual(normalized.meeting_date, "2026-05-14")
        self.assertEqual([utterance.utterance_id for utterance in normalized.utterances], ["u_0001", "u_0002", "u_0003", "u_0004"])
        self.assertEqual([utterance.index for utterance in normalized.utterances], [0, 1, 2, 3])
        self.assertEqual(normalized.utterances[1].text, "네네 확인했습니다")
        self.assertEqual(normalized.utterances[2].text, "배포는 금요일까지 진행하겠습니다.")
        self.assertEqual(normalized.utterances[1].raw_line, "네네 확인했습니다")

    def test_normalized_transcript_renders_utterance_ids_for_llm(self) -> None:
        """LLM 입력용 렌더링은 발화 ID와 원문 텍스트를 보존합니다."""
        normalized = summarize.normalize_transcript(
            """
오늘 회의는 네 가지 안건입니다.
4월 매출이 전월 대비 증가했습니다.
""".strip()
        )

        self.assertEqual(
            normalized.render_for_llm(),
            "\n".join(
                [
                    "[u_0001] 오늘 회의는 네 가지 안건입니다.",
                    "[u_0002] 4월 매출이 전월 대비 증가했습니다.",
                ]
            ),
        )

    def test_normalized_transcript_renders_unknown_speaker_for_plain_transcript(self) -> None:
        """화자 라벨이 없는 plain transcript도 LLM 입력용 렌더링에서 깨지지 않습니다."""
        normalized = summarize.normalize_transcript("오늘 회의는 네 가지 안건입니다.")

        self.assertEqual(normalized.text, "오늘 회의는 네 가지 안건입니다.")
        self.assertEqual(normalized.render_for_llm(), "[u_0001] 오늘 회의는 네 가지 안건입니다.")

    def test_normalize_transcript_splits_long_speakerless_lines_at_sentence_boundaries(self) -> None:
        """긴 plain STT 줄은 sentence boundary 우선으로 source 단위를 나눕니다."""
        first_sentence = "가" * 240 + "."
        second_sentence = "나" * 240 + "?"
        third_sentence = "다" * 100
        normalized = summarize.normalize_transcript(first_sentence + second_sentence + third_sentence)

        self.assertEqual(len(normalized.utterances), 2)
        self.assertEqual(normalized.utterances[0].text, first_sentence + second_sentence)
        self.assertEqual(normalized.utterances[1].text, third_sentence)
        self.assertTrue(all(len(utterance.text) <= 500 for utterance in normalized.utterances))

    def test_normalize_transcript_hard_splits_long_speakerless_lines_without_sentence_boundary(self) -> None:
        """sentence boundary가 없으면 500자 단위로 hard split합니다."""
        normalized = summarize.normalize_transcript("가" * 650)

        self.assertEqual([len(utterance.text) for utterance in normalized.utterances], [500, 150])

    def test_normalize_transcript_treats_common_colon_headings_as_plain_text(self) -> None:
        """plain transcript의 일반 heading/key label은 speaker로 보지 않습니다."""
        heading_lines = [
            "회의 목적: KT와 향후 협력 방향 논의",
            "안건: Tableau 대시보드 전환",
            "이슈: Salesforce 연동 지연",
            "TODO: MCP 검토",
            "API: 응답 속도 확인 필요",
            "Q: 이 방식이 가능한가요?",
            "A: 가능합니다",
            "결론: 다음 주 POC 진행",
            "참석자: 홍길동, 김철수",
        ]

        for line in heading_lines:
            with self.subTest(line=line):
                normalized = summarize.normalize_transcript(line)

                self.assertEqual(len(normalized.utterances), 1)
                self.assertEqual(normalized.utterances[0].text, line)
                self.assertEqual(normalized.text, line)

    def test_normalize_transcript_colon_lines_do_not_create_continuation(self) -> None:
        """colon이 들어간 plain 줄도 continuation 없이 독립 발화로 유지됩니다."""
        transcript = """
회의 목적: KT와 향후 협력 방향 논의
추가 논의 범위를 확인합니다.
김민수: 배포 확인
""".strip()

        normalized = summarize.normalize_transcript(transcript)

        self.assertEqual(normalized.utterances[0].text, "회의 목적: KT와 향후 협력 방향 논의")
        self.assertEqual(normalized.utterances[1].text, "추가 논의 범위를 확인합니다.")
        self.assertEqual(normalized.utterances[2].text, "김민수: 배포 확인")
        self.assertEqual(
            normalized.render_for_llm(),
            "\n".join(
                [
                    "[u_0001] 회의 목적: KT와 향후 협력 방향 논의",
                    "[u_0002] 추가 논의 범위를 확인합니다.",
                    "[u_0003] 김민수: 배포 확인",
                ]
            ),
        )

    def test_normalize_transcript_preserves_plain_line_handling(self) -> None:
        """plain 줄은 기존 순서대로 독립 발화로 유지합니다."""
        transcript = """
회의 목적 공유
김민수: 첫 발언입니다.
추가 설명입니다.
이서연: 확인했습니다.
""".strip()

        normalized = summarize.normalize_transcript(transcript)
        preprocessed = summarize.preprocess_transcript(transcript)

        self.assertEqual(normalized.text, preprocessed.text)
        self.assertEqual(
            normalized.text,
            "회의 목적 공유\n김민수: 첫 발언입니다.\n추가 설명입니다.\n이서연: 확인했습니다.",
        )
        self.assertEqual(normalized.utterances[1].text, "김민수: 첫 발언입니다.")
        self.assertEqual(normalized.utterances[2].text, "추가 설명입니다.")


if __name__ == "__main__":
    unittest.main()
