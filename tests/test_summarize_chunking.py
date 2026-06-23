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

class SummarizeChunkingTests(unittest.TestCase):
    """기존 summarize.py 테스트를 도메인별로 분리한 테스트입니다."""

    def test_segment_transcript_returns_single_chunk_for_short_transcript(self) -> None:
        """짧은 transcript는 speaker 없는 발화까지 포함한 단일 chunk로 유지합니다."""
        from summarization.chunking import build_chunk_text, segment_transcript

        transcript = """
회의 목적 공유
김민수: 첫 발언입니다.
이서연: 확인했습니다.
""".strip()

        normalized = summarize.normalize_transcript(transcript)
        chunks = segment_transcript(normalized, max_utterances=5, overlap_utterances=1)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, "c_0001")
        self.assertEqual(chunks[0].utterances, normalized.utterances)
        self.assertEqual(chunks[0].start_utterance_id, "u_0001")
        self.assertEqual(chunks[0].end_utterance_id, "u_0003")
        self.assertEqual(chunks[0].overlap_before_ids, [])
        self.assertEqual(chunks[0].overlap_after_ids, [])
        self.assertEqual(chunks[0].text, build_chunk_text(normalized.utterances))
        self.assertEqual(
            chunks[0].text,
            "\n".join(
                [
                    "[u_0001] 회의 목적 공유",
                    "[u_0002] 김민수: 첫 발언입니다.",
                    "[u_0003] 이서연: 확인했습니다.",
                ]
            ),
        )

    def test_segment_transcript_splits_long_transcript_with_stable_ids_and_overlap(self) -> None:
        """긴 transcript는 발화를 자르지 않고 안정적인 chunk_id와 overlap을 부여합니다."""
        from summarization.chunking import segment_transcript

        lines = [
            f"{'김민수' if index % 2 == 0 else '이서연'}: 논의 내용 {index + 1}입니다."
            for index in range(9)
        ]

        chunks = segment_transcript(
            summarize.normalize_transcript("\n".join(lines)),
            max_utterances=4,
            overlap_utterances=1,
        )

        self.assertEqual([chunk.chunk_id for chunk in chunks], ["c_0001", "c_0002", "c_0003"])
        self.assertEqual(
            [(chunk.start_utterance_id, chunk.end_utterance_id) for chunk in chunks],
            [("u_0001", "u_0004"), ("u_0004", "u_0007"), ("u_0007", "u_0009")],
        )
        self.assertEqual(chunks[0].overlap_before_ids, [])
        self.assertEqual(chunks[0].overlap_after_ids, ["u_0004"])
        self.assertEqual(chunks[1].overlap_before_ids, ["u_0004"])
        self.assertEqual(chunks[1].overlap_after_ids, ["u_0007"])
        self.assertEqual(chunks[2].overlap_before_ids, ["u_0007"])
        self.assertEqual(chunks[2].overlap_after_ids, [])
        self.assertEqual([utterance.utterance_id for utterance in chunks[1].utterances], ["u_0004", "u_0005", "u_0006", "u_0007"])
        self.assertIn("[u_0004] 이서연: 논의 내용 4입니다.", chunks[1].text)

    def test_segment_transcript_rejects_invalid_parameters(self) -> None:
        """유효하지 않은 chunk 크기와 overlap 값은 ValueError로 거절합니다."""
        from summarization.chunking import segment_transcript

        normalized = summarize.normalize_transcript("김민수: 확인했습니다.")

        with self.assertRaises(ValueError):
            segment_transcript(normalized, max_utterances=0, overlap_utterances=0)
        with self.assertRaises(ValueError):
            segment_transcript(normalized, max_utterances=5, overlap_utterances=-1)
        with self.assertRaises(ValueError):
            segment_transcript(normalized, max_utterances=5, overlap_utterances=5)
        with self.assertRaises(ValueError):
            segment_transcript(normalized, max_utterances=5, overlap_utterances=6)

    def test_segment_transcript_returns_empty_list_for_empty_utterances(self) -> None:
        """정규화된 발화가 없으면 chunk도 빈 목록으로 반환합니다."""
        from summarization.chunking import segment_transcript

        normalized = summarize.normalize_transcript("   ")

        self.assertEqual(segment_transcript(normalized), [])

    def test_merge_structures_returns_empty_shape_for_empty_input(self) -> None:
        """병합할 structure가 없으면 기존 structure shape의 빈 값을 반환합니다."""
        from summarization.merge import merge_structures

        self.assertEqual(merge_structures([]), empty_track_b_structure())

    def test_merge_structures_deduplicates_text_sections_in_source_order(self) -> None:
        """summary_facts, speaker_highlights, warnings는 정규화 text 기준으로 중복 제거합니다."""
        from summarization.merge import merge_structures

        merged = merge_structures(
            [
                {
                    "summary_facts": ["회의 방향 공유", " 배포 일정 논의 "],
                    "decisions": [],
                    "action_items": [],
                    "speaker_highlights": ["김민수가 배포 일정을 언급했습니다."],
                    "warnings": ["담당자 확인 필요", "기한 확인 필요"],
                },
                {
                    "summary_facts": ["회의   방향 공유", "고객 확인 필요"],
                    "decisions": [],
                    "action_items": [],
                    "speaker_highlights": ["김민수가   배포 일정을 언급했습니다.", "이서연이 검수를 맡았습니다."],
                    "warnings": ["담당자   확인 필요", "추가 확인 필요"],
                },
            ]
        )

        self.assertEqual(merged["summary_facts"], ["회의 방향 공유", "배포 일정 논의", "고객 확인 필요"])
        self.assertEqual(
            merged["speaker_highlights"],
            ["김민수가 배포 일정을 언급했습니다.", "이서연이 검수를 맡았습니다."],
        )
        self.assertEqual(merged["warnings"], ["담당자 확인 필요", "기한 확인 필요", "추가 확인 필요"])

    def test_merge_structures_merges_duplicate_decisions_and_prefers_source_quote(self) -> None:
        """decision/status가 같은 결정은 합치고 source_quote가 있는 항목을 선호합니다."""
        from summarization.merge import merge_structures

        merged = merge_structures(
            [
                {
                    "summary_facts": [],
                    "decisions": [
                        {"decision": "FastAPI로 진행", "status": "확정", "source_quote": ""},
                        {"decision": "배포 일정은 다음 회의에서 논의", "status": "미확정", "source_quote": "다음에 논의합시다."},
                    ],
                    "action_items": [],
                    "speaker_highlights": [],
                    "warnings": [],
                },
                {
                    "summary_facts": [],
                    "decisions": [
                        {
                            "decision": "FastAPI로 진행",
                            "status": "확정",
                            "source_quote": "FastAPI로 진행하는 것으로 확정하겠습니다.",
                        },
                        {"decision": "FastAPI로 진행", "status": "미확정", "source_quote": "아직 확정 전입니다."},
                    ],
                    "action_items": [],
                    "speaker_highlights": [],
                    "warnings": [],
                },
            ]
        )

        self.assertEqual(len(merged["decisions"]), 3)
        self.assertEqual(
            merged["decisions"][0],
            {
                "decision": "FastAPI로 진행",
                "status": "확정",
                "source_quote": "FastAPI로 진행하는 것으로 확정하겠습니다.",
            },
        )
        self.assertEqual(merged["decisions"][1]["decision"], "배포 일정은 다음 회의에서 논의")
        self.assertEqual(merged["decisions"][2], {"decision": "FastAPI로 진행", "status": "미확정", "source_quote": "아직 확정 전입니다."})

    def test_merge_structures_merges_duplicate_action_items_and_preserves_distinct_owners_or_dates(self) -> None:
        """task/owner/due_date가 같은 실행 항목만 합치고 다른 담당자나 기한은 유지합니다."""
        from summarization.merge import merge_structures

        merged = merge_structures(
            [
                {
                    "summary_facts": [],
                    "decisions": [],
                    "action_items": [
                        {
                            "task": "배포 확인",
                            "owner": "김민수",
                            "due_date": "2026-05-20",
                            "confidence": "low",
                            "source_quote": "",
                        },
                        {
                            "task": "배포 확인",
                            "owner": "이서연",
                            "due_date": "2026-05-20",
                            "confidence": "high",
                            "source_quote": "이서연이 배포를 확인합니다.",
                        },
                    ],
                    "speaker_highlights": [],
                    "warnings": [],
                },
                {
                    "summary_facts": [],
                    "decisions": [],
                    "action_items": [
                        {
                            "task": "배포 확인",
                            "owner": "김민수",
                            "due_date": "2026-05-20",
                            "confidence": "high",
                            "source_quote": "김민수가 2026-05-20까지 배포를 확인합니다.",
                        },
                        {
                            "task": "배포 확인",
                            "owner": "김민수",
                            "due_date": "2026-05-21",
                            "confidence": "low",
                            "source_quote": "기한은 2026-05-21일 수 있습니다.",
                        },
                    ],
                    "speaker_highlights": [],
                    "warnings": [],
                },
            ]
        )

        self.assertEqual(len(merged["action_items"]), 3)
        self.assertEqual(
            merged["action_items"][0],
            {
                "task": "배포 확인",
                "owner": "김민수",
                "due_date": "2026-05-20",
                "confidence": "high",
                "source_quote": "김민수가 2026-05-20까지 배포를 확인합니다.",
            },
        )
        self.assertEqual(merged["action_items"][1]["owner"], "이서연")
        self.assertEqual(merged["action_items"][2]["due_date"], "2026-05-21")

    def test_merge_structures_merges_action_heavy_repeated_domains(self) -> None:
        """action-heavy 회의의 반복 표현은 같은 업무 도메인 기준으로 합칩니다."""
        from summarization.merge import merge_structures

        merged = merge_structures(
            [
                {
                    "summary_facts": [],
                    "decisions": [],
                    "action_items": [
                        {
                            "task": "이티엘 재시도 설정",
                            "owner": "박민재",
                            "due_date": "금요일 오후",
                            "confidence": "low",
                            "source_quote": "제가 배치 설정에 재시도 2회를 반영하겠습니다.",
                        },
                        {
                            "task": "campaign_id null 매핑",
                            "owner": "박민재",
                            "due_date": "금요일 오후 3시",
                            "confidence": "high",
                            "source_quote": "campaign_id null 매핑은 박민재님이 금요일 오후 3시까지 반영해 주세요.",
                        },
                    ],
                    "speaker_highlights": [],
                    "warnings": [],
                },
                {
                    "summary_facts": [],
                    "decisions": [],
                    "action_items": [
                        {
                            "task": "재시도 2회 설정",
                            "owner": "박민재",
                            "due_date": "금요일 오후 6시",
                            "confidence": "high",
                            "source_quote": "박민재님 재시도 2회 설정은 금요일 오후 6시까지입니다.",
                        },
                        {
                            "task": "기타 캠페인 라벨 반영",
                            "owner": "박민재",
                            "due_date": "금요일 오후 3시",
                            "confidence": "high",
                            "source_quote": "제가 금요일 오후 3시까지 매핑 반영하겠습니다.",
                        },
                    ],
                    "speaker_highlights": [],
                    "warnings": [],
                },
            ]
        )

        self.assertEqual(len(merged["action_items"]), 2)
        retry_action = next(item for item in merged["action_items"] if "재시도" in item["task"])
        campaign_action = next(item for item in merged["action_items"] if "campaign_id" in item["task"])
        self.assertEqual(retry_action["due_date"], "금요일 오후 6시")
        self.assertEqual(retry_action["confidence"], "high")
        self.assertEqual(campaign_action["source_quote"], "campaign_id null 매핑은 박민재님이 금요일 오후 3시까지 반영해 주세요.")

    def test_merge_structures_does_not_validate_action_items(self) -> None:
        """merge helper는 owner 정규화나 due_date fallback을 수행하지 않습니다."""
        from summarization.merge import merge_structures

        merged = merge_structures(
            [
                {
                    "summary_facts": [],
                    "decisions": [],
                    "action_items": [
                        {
                            "task": "자료 정리",
                            "owner": "제가",
                            "due_date": "",
                            "confidence": "maybe",
                            "source_quote": "자료는 제가 정리하겠습니다.",
                        }
                    ],
                    "speaker_highlights": [],
                    "warnings": [],
                }
            ]
        )

        self.assertEqual(merged["action_items"][0]["owner"], "제가")
        self.assertEqual(merged["action_items"][0]["due_date"], "")
        self.assertEqual(merged["action_items"][0]["confidence"], "maybe")


if __name__ == "__main__":
    unittest.main()
