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

class SummarizeValidationTests(unittest.TestCase):
    """기존 summarize.py 테스트를 도메인별로 분리한 테스트입니다."""

    def test_validate_structure_accepts_payload_without_source_utterance_ids(self) -> None:
        """기존 payload처럼 source_utterance_ids가 없어도 검증됩니다."""
        structure = {
            "summary_facts": [],
            "decisions": [
                {
                    "decision": "배포 확인을 진행한다",
                    "status": "확정",
                    "source_quote": "배포 확인을 진행하겠습니다.",
                }
            ],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "김민수",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "배포 확인을 진행하겠습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.validate_structure(structure, "김민수: 배포 확인을 진행하겠습니다.")

        self.assertEqual(result["action_items"][0]["source_utterance_ids"], [])
        self.assertEqual(result["decisions"][0]["source_utterance_ids"], [])

    def test_validate_structure_accepts_payload_with_source_utterance_ids(self) -> None:
        """source_utterance_ids가 있는 payload도 내부 구조에 보존됩니다."""
        structure = {
            "summary_facts": [],
            "decisions": [
                {
                    "decision": "배포 확인을 진행한다",
                    "status": "확정",
                    "source_quote": "배포 확인을 진행하겠습니다.",
                    "source_utterance_ids": ["u_0001"],
                }
            ],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "김민수",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "배포 확인을 진행하겠습니다.",
                    "source_utterance_ids": ["u_0001"],
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.validate_structure(structure, "김민수: 배포 확인을 진행하겠습니다.")

        self.assertEqual(result["action_items"][0]["source_utterance_ids"], ["u_0001"])
        self.assertEqual(result["decisions"][0]["source_utterance_ids"], ["u_0001"])

    def test_find_quote_in_utterances_returns_exact_match_utterance_ids(self) -> None:
        """source_quote가 발화 text에 exact match되면 해당 utterance_id를 반환합니다."""
        normalized = summarize.normalize_transcript(
            """
오늘 회의는 네 가지 안건입니다.
배포 확인은 제가 진행하겠습니다.
""".strip()
        )

        self.assertEqual(summarize.find_quote_in_utterances("배포 확인은 제가 진행하겠습니다.", normalized), ["u_0002"])

    def test_find_quote_in_utterances_matches_whitespace_normalized_quote(self) -> None:
        """공백 차이가 있어도 source_quote가 포함된 발화를 찾습니다."""
        normalized = summarize.normalize_transcript("배포 확인은 제가 진행하겠습니다.")

        self.assertEqual(summarize.find_quote_in_utterances("배포   확인은 제가 진행하겠습니다.", normalized), ["u_0001"])

    def test_find_quote_in_utterances_strips_utterance_id_only(self) -> None:
        """quote에 발화 ID가 섞여도 실제 발화 텍스트로 매칭합니다."""
        normalized = summarize.normalize_transcript("영업담당자: 제가 고객 공유를 진행하겠습니다.")

        self.assertEqual(
            summarize.find_quote_in_utterances("[u_0001] 영업담당자: 제가 고객 공유를 진행하겠습니다.", normalized),
            ["u_0001"],
        )
        self.assertEqual(
            summarize.normalize_quote_for_matching("영업담당자: 제가 고객 공유를 진행하겠습니다."),
            "영업담당자: 제가 고객 공유를 진행하겠습니다.",
        )

    def test_find_quote_in_utterances_returns_empty_list_when_missing(self) -> None:
        """source_quote가 어떤 발화에도 없으면 빈 목록을 반환합니다."""
        normalized = summarize.normalize_transcript("배포 확인은 제가 진행하겠습니다.")

        self.assertEqual(summarize.find_quote_in_utterances("원문에 없는 문장입니다.", normalized), [])

    def test_validate_structure_can_use_normalized_transcript_for_source_quote(self) -> None:
        """선택적으로 받은 normalized transcript에서 quote를 찾으면 원문 근거 warning을 만들지 않습니다."""
        normalized = summarize.normalize_transcript("김민수: 배포 확인은 제가 진행하겠습니다.")
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "김민수",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "[u_0001] 김민수: 배포 확인은 제가 진행하겠습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.validate_structure(structure, "요약용 축약 transcript", normalized)

        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["action_items"][0]["source_utterance_ids"], ["u_0001"])

    def test_validate_structure_preserves_relative_due_date_from_source_quote(self) -> None:
        """LLM이 ISO 날짜를 만들었더라도 원문 상대 기한이 있으면 그 표현을 보존합니다."""
        transcript = "김하준: 대시보드 라우팅은 이서연님 내일 오전까지입니다."
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "대시보드 라우팅",
                    "owner": "이서연",
                    "due_date": "2026-05-16",
                    "confidence": "high",
                    "source_quote": "대시보드 라우팅은 이서연님 내일 오전까지입니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.validate_structure(structure, transcript)

        self.assertEqual(result["action_items"][0]["due_date"], "내일 오전")
        self.assertEqual(result["warnings"], [])

    def test_validate_structure_removes_decision_only_action_without_owner_due_date(self) -> None:
        """담당자와 기한 없는 정책 결정이 action item으로 들어오면 제거합니다."""
        transcript = "김하준: 이번 PoC에서는 API 응답 캐싱을 적용하지 않기로 결정합니다."
        structure = {
            "summary_facts": [],
            "decisions": [
                {
                    "decision": "API 응답 캐싱을 적용하지 않는다",
                    "status": "확정",
                    "source_quote": "이번 PoC에서는 API 응답 캐싱을 적용하지 않기로 결정합니다.",
                }
            ],
            "action_items": [
                {
                    "task": "API 캐싱 제외",
                    "owner": "미정",
                    "due_date": "미정",
                    "confidence": "low",
                    "source_quote": "이번 PoC에서는 API 응답 캐싱을 적용하지 않기로 결정합니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.validate_structure(structure, transcript)

        self.assertEqual(result["action_items"], [])
        self.assertEqual(result["warnings"], [])

    def test_validate_structure_keeps_warning_for_mismatched_source_utterance_ids(self) -> None:
        """잘못된 source_utterance_ids가 있어도 검증은 실패하지 않고 기존 warning 흐름을 사용합니다."""
        normalized = summarize.normalize_transcript(
            """
김민수: 배포 확인은 제가 진행하겠습니다.
이서연: 자료 정리는 제가 진행하겠습니다.
""".strip()
        )
        structure = {
            "summary_facts": [],
            "decisions": [
                {
                    "decision": "배포 확인을 진행한다",
                    "status": "확정",
                    "source_quote": "배포 확인은 제가 진행하겠습니다.",
                    "source_utterance_ids": ["u_0002"],
                }
            ],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "김민수",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "배포 확인은 제가 진행하겠습니다.",
                    "source_utterance_ids": ["u_0002"],
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.validate_structure(structure, normalized.text, normalized)

        self.assertEqual(result["action_items"][0]["confidence"], "low")
        self.assertEqual(result["action_items"][0]["source_utterance_ids"], ["u_0002"])
        self.assertIn("배포 확인: 원문 근거 확인 필요", result["warnings"])
        self.assertIn("배포 확인을 진행한다: 원문 근거 확인 필요", result["warnings"])

    def test_validate_structure_normalizes_actions_decisions_and_warnings(self) -> None:
        """validate_structure가 grounding, 정규화, 중복 제거를 Python에서 수행합니다."""
        structure = {
            "summary_facts": ["빠른 요약"],
            "decisions": [
                {"decision": "Streamlit 기반 진행", "status": "done", "source_quote": ""},
                {"decision": "Streamlit 기반 진행", "status": "done", "source_quote": ""},
            ],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "제가",
                    "due_date": "",
                    "confidence": "maybe",
                    "source_quote": "없는 근거 문장",
                },
                {
                    "task": "배포 확인",
                    "owner": "제가",
                    "due_date": "",
                    "confidence": "high",
                    "source_quote": "없는 근거 문장",
                },
            ],
            "speaker_highlights": ["주요 발언"],
            "warnings": ["기존 경고", "기존 경고"],
        }

        result = summarize.validate_structure(structure, "김민수: 배포 확인은 금요일까지 진행하겠습니다.")

        self.assertEqual(result["summary_facts"], ["빠른 요약"])
        self.assertEqual(len(result["action_items"]), 1)
        self.assertEqual(
            result["action_items"][0],
            {
                "task": "배포 확인",
                "owner": "미정",
                "due_date": "미정",
                "confidence": "low",
                "source_quote": "없는 근거 문장",
                "source_utterance_ids": [],
            },
        )
        self.assertEqual(len(result["decisions"]), 1)
        self.assertEqual(
            result["decisions"][0],
            {
                "decision": "Streamlit 기반 진행",
                "status": "미확정",
                "source_quote": "",
                "source_utterance_ids": [],
            },
        )
        self.assertEqual(result["warnings"].count("기존 경고"), 1)
        self.assertIn("배포 확인: 담당자 및 기한 확인 필요", result["warnings"])
        self.assertIn("배포 확인: 원문 근거 확인 필요", result["warnings"])
        self.assertIn("Streamlit 기반 진행: 원문 근거 확인 필요", result["warnings"])

    def test_validate_structure_keeps_named_owner_without_owner_warning(self) -> None:
        """명시된 사람/팀 owner는 담당자 미정으로 보지 않습니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "김민수",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "김민수가 배포 확인을 2026-05-20까지 하겠습니다.",
                },
                {
                    "task": "고객 공유",
                    "owner": "영업팀",
                    "due_date": "2026-05-22",
                    "confidence": "high",
                    "source_quote": "영업팀이 고객 공유를 2026-05-22까지 하겠습니다.",
                },
            ],
            "speaker_highlights": [],
            "warnings": [],
        }
        transcript = "\n".join(
            [
                "[u_0001] 김민수가 배포 확인을 2026-05-20까지 하겠습니다.",
                "[u_0002] 영업팀이 고객 공유를 2026-05-22까지 하겠습니다.",
            ]
        )

        result = summarize.validate_structure(structure, transcript)

        self.assertEqual([item["owner"] for item in result["action_items"]], ["김민수", "영업팀"])
        self.assertFalse(any("담당자 확인 필요" in warning for warning in result["warnings"]))
        self.assertFalse(any("담당자 확인이 필요한 액션 아이템" in warning for warning in result["warnings"]))

    def test_validate_structure_treats_unknown_owners_as_unresolved(self) -> None:
        """Unknown 계열 owner는 plain transcript에서 실제 담당자로 보지 않습니다."""
        transcript = "\n".join(
            [
                "제가 자료 정리를 2026-05-21까지 하겠습니다.",
                "제가 로그 확인을 2026-05-22까지 하겠습니다.",
                "제가 고객 공유를 2026-05-23까지 하겠습니다.",
                "김민수가 배포 확인을 2026-05-24까지 하겠습니다.",
            ]
        )
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "자료 정리",
                    "owner": "Unknown",
                    "due_date": "2026-05-21",
                    "confidence": "high",
                    "source_quote": "제가 자료 정리를 2026-05-21까지 하겠습니다.",
                },
                {
                    "task": "고객 공유",
                    "owner": "미상",
                    "due_date": "2026-05-23",
                    "confidence": "high",
                    "source_quote": "제가 고객 공유를 2026-05-23까지 하겠습니다.",
                },
                {
                    "task": "배포 확인",
                    "owner": "김민수",
                    "due_date": "2026-05-24",
                    "confidence": "high",
                    "source_quote": "김민수가 배포 확인을 2026-05-24까지 하겠습니다.",
                },
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.validate_structure(structure, transcript)

        self.assertEqual(
            [item["owner"] for item in result["action_items"]],
            ["미정", "미정", "김민수"],
        )
        self.assertIn("자료 정리: 담당자 확인 필요", result["warnings"])
        self.assertIn("고객 공유: 담당자 확인 필요", result["warnings"])
        self.assertFalse(any("배포 확인: 담당자 확인 필요" == warning for warning in result["warnings"]))

    def test_normalize_action_owner_treats_unknown_markers_as_unresolved(self) -> None:
        """Unknown과 한국어 미상 표기는 모두 미정 owner로 정규화합니다."""
        unresolved_owners = [
            "Unknown",
            "unknown",
            "UNKNOWN",
            "알 수 없음",
            "미상",
        ]

        for owner in unresolved_owners:
            with self.subTest(owner=owner):
                self.assertEqual(summarize.normalize_action_owner(owner), "미정")

        self.assertEqual(summarize.normalize_action_owner("김민수"), "김민수")


if __name__ == "__main__":
    unittest.main()
