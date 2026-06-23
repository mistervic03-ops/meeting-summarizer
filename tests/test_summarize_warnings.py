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

class SummarizeWarningTests(unittest.TestCase):
    """기존 summarize.py 테스트를 도메인별로 분리한 테스트입니다."""

    def test_validate_structure_warns_only_when_owner_is_unknown_marker(self) -> None:
        """owner가 미정이면 기존 담당자 확인 warning은 유지합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "미정",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "배포 확인은 2026-05-20까지 진행합니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.validate_structure(structure, "김민수: 배포 확인은 2026-05-20까지 진행합니다.")

        self.assertIn("배포 확인: 담당자 확인 필요", result["warnings"])

    def test_validate_structure_removes_stale_owner_warning_for_resolved_owner(self) -> None:
        """resolved owner를 가리키는 오래된 담당자 warning은 제거합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "큐 지연 확인",
                    "owner": "이서연",
                    "due_date": "금요일 오후",
                    "confidence": "high",
                    "source_quote": "큐 지연 쪽을 확인해보겠습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": ["이서연: 담당자 확인 필요"],
        }

        result = summarize.validate_structure(structure, "이서연: 큐 지연 쪽을 확인해보겠습니다.")

        self.assertFalse(any("담당자 확인" in warning for warning in result["warnings"]))

    def test_validate_structure_removes_task_owner_warning_but_keeps_due_date_warning(self) -> None:
        """task 기준 stale owner warning은 제거하되 기한 warning은 유지합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "김민수",
                    "due_date": "미정",
                    "confidence": "high",
                    "source_quote": "배포 확인은 제가 하겠습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": ["배포 확인: 담당자 확인 필요"],
        }

        result = summarize.validate_structure(structure, "김민수: 배포 확인은 제가 하겠습니다.")

        self.assertNotIn("배포 확인: 담당자 확인 필요", result["warnings"])
        self.assertIn("배포 확인: 기한 확인 필요", result["warnings"])

    def test_validate_structure_keeps_owner_warning_for_unresolved_owner(self) -> None:
        """owner가 실제로 미정이면 담당자 warning은 유지합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "저희",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "배포 확인은 저희가 하겠습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": ["배포 확인: 담당자 확인 필요"],
        }

        result = summarize.validate_structure(structure, "배포 확인은 저희가 하겠습니다.")

        self.assertIn("배포 확인: 담당자 확인 필요", result["warnings"])

    def test_validate_structure_owner_cleanup_keeps_source_quote_warning(self) -> None:
        """resolved owner의 stale warning만 제거하고 원문 근거 warning은 유지합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "이서연",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "원문에 없는 근거입니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": ["이서연: 담당자 확인 필요"],
        }

        result = summarize.validate_structure(structure, "이서연: 배포 확인을 진행하겠습니다.")

        self.assertFalse(any("담당자 확인" in warning for warning in result["warnings"]))
        self.assertIn("배포 확인: 원문 근거 확인 필요", result["warnings"])

    def test_validate_structure_removes_medium_fixture_stale_owner_warning(self) -> None:
        """medium fixture smoke에서 보인 speaker subject owner warning을 제거합니다."""
        from tests.test_fixtures import load_fixture_transcript, normalize_fixture

        transcript = load_fixture_transcript("medium_project_meeting.txt")
        normalized = normalize_fixture("medium_project_meeting.txt")
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "테스트 상태 공유",
                    "owner": "정도윤",
                    "due_date": "미정",
                    "confidence": "low",
                    "source_quote": "테스트 데이터 준비 상태는 정도윤님이 매일 오후 5시에 짧게 공유해 주세요.",
                }
            ],
            "speaker_highlights": [],
            "warnings": ["테스트 상태 공유 담당자가 미정입니다.", "정도윤: 담당자 확인 필요"],
        }

        result = summarize.validate_structure(structure, transcript, normalized)

        self.assertFalse(any("담당자 확인" in warning for warning in result["warnings"]))
        self.assertIn("테스트 상태 공유: 기한 확인 필요", result["warnings"])

    def test_validate_structure_filters_stale_model_warnings_for_high_confidence_items(self) -> None:
        """검증된 high confidence 항목과 모순되는 모델 warning만 제거합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [
                {
                    "decision": "배포 방식 확정",
                    "status": "확정",
                    "source_quote": "배포 방식은 FastAPI로 확정하겠습니다.",
                }
            ],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "김민수",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "배포 확인은 김민수가 2026-05-20까지 진행합니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [
                "배포 확인 담당자 미정",
                "배포 확인 기한 미정",
                "배포 방식 확정 근거 부족",
                "회의 전체 맥락은 추가 확인 필요",
            ],
        }
        transcript = "\n".join(
            [
                "김민수: 배포 확인은 김민수가 2026-05-20까지 진행합니다.",
                "김민수: 배포 방식은 FastAPI로 확정하겠습니다.",
            ]
        )

        result = summarize.validate_structure(structure, transcript)

        self.assertNotIn("배포 확인 담당자 미정", result["warnings"])
        self.assertNotIn("배포 확인 기한 미정", result["warnings"])
        self.assertNotIn("배포 방식 확정 근거 부족", result["warnings"])
        self.assertIn("회의 전체 맥락은 추가 확인 필요", result["warnings"])

    def test_validate_structure_keeps_low_confidence_and_validation_warnings(self) -> None:
        """low confidence 항목의 warning과 validation-derived warning은 유지합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "",
                    "due_date": "",
                    "confidence": "low",
                    "source_quote": "원문에 없는 배포 확인 문장",
                }
            ],
            "speaker_highlights": [],
            "warnings": [
                "배포 확인 담당자 미정",
                "보안 이슈는 별도 검토 필요",
            ],
        }

        result = summarize.validate_structure(structure, "김민수: 배포 관련 논의를 진행했습니다.")

        self.assertIn("배포 확인: 담당자 및 기한 확인 필요", result["warnings"])
        self.assertIn("보안 이슈는 별도 검토 필요", result["warnings"])
        self.assertIn("배포 확인: 원문 근거 확인 필요", result["warnings"])

    def test_validate_structure_formats_public_warnings_without_internal_field_names(self) -> None:
        """사용자-facing warnings에는 내부 필드명을 남기지 않습니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "발표자료 준비하기",
                    "owner": "",
                    "due_date": "",
                    "confidence": "high",
                    "source_quote": "발표자료 준비하기는 진행하겠습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [
                "발표자료 준비하기의 owner가 미정이다.",
                "발표자료 준비하기의 due_date가 미정이다.",
            ],
        }

        result = summarize.validate_structure(structure, "김민수: 발표자료 준비하기는 진행하겠습니다.")

        self.assertIn("발표자료 준비하기: 담당자 및 기한 확인 필요", result["warnings"])
        self.assertEqual(result["warnings"].count("발표자료 준비하기: 담당자 및 기한 확인 필요"), 1)
        self.assertFalse(any("owner" in warning for warning in result["warnings"]))
        self.assertFalse(any("due_date" in warning for warning in result["warnings"]))
        self.assertFalse(any("confidence" in warning for warning in result["warnings"]))
        self.assertFalse(any("source_quote" in warning for warning in result["warnings"]))

    def test_validate_structure_sanitizes_residual_internal_field_warnings(self) -> None:
        """일반 warning에 남은 내부 필드명도 공개 warning에서는 제거합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [],
            "speaker_highlights": [],
            "warnings": [
                "owner 미정",
                "due_date 확인 필요",
                "confidence 낮음",
                "source_quote 확인 필요",
            ],
        }

        result = summarize.validate_structure(structure, "김민수: 회의를 진행했습니다.")

        self.assertFalse(
            any(
                internal_name in warning
                for warning in result["warnings"]
                for internal_name in ("owner", "due_date", "confidence", "source_quote")
            )
        )

    def test_validate_structure_formats_first_person_owner_warning(self) -> None:
        """1인칭 담당자 표현 warning도 일반 담당자 확인 문장으로 바꿉니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [],
            "speaker_highlights": [],
            "warnings": ["'담당자는 저로'라는 발언이 있어 owner가 미정이다."],
        }

        result = summarize.validate_structure(structure, "김민수: 담당자는 저로 하겠습니다.")

        self.assertEqual(result["warnings"], ["담당자 확인이 필요한 액션 아이템이 있습니다."])
        self.assertFalse(any("owner" in warning for warning in result["warnings"]))

    def test_validate_structure_removes_generic_owner_warning_when_specific_exists(self) -> None:
        """구체 담당자 warning이 있으면 중복되는 일반 담당자 warning은 제거합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "발표자료 준비하기",
                    "owner": "",
                    "due_date": "2026-06-10",
                    "confidence": "high",
                    "source_quote": "발표자료 준비는 6월 10일까지 진행합니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": ["주요 행동 아이템의 담당자가 명확하지 않습니다."],
        }

        result = summarize.validate_structure(structure, "김민수: 발표자료 준비는 6월 10일까지 진행합니다.")

        self.assertIn("발표자료 준비하기: 담당자 확인 필요", result["warnings"])
        self.assertNotIn("주요 행동 아이템의 담당자가 명확하지 않습니다.", result["warnings"])

    def test_validate_structure_keeps_generic_owner_warning_without_specific_warning(self) -> None:
        """구체 warning이 없으면 일반 담당자 warning은 보존합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [],
            "speaker_highlights": [],
            "warnings": ["일부 액션 아이템의 담당자가 명확하지 않습니다."],
        }

        result = summarize.validate_structure(structure, "김민수: 회의를 진행했습니다.")

        self.assertIn("담당자 확인이 필요한 액션 아이템이 있습니다.", result["warnings"])

    def test_validate_structure_keeps_low_confidence_warning_in_user_friendly_text(self) -> None:
        """low confidence 실행 항목 경고는 자연스러운 문장으로 보존합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "고객 확인 후 배포 일정 확정하기",
                    "owner": "김민수",
                    "due_date": "2026-05-20",
                    "confidence": "low",
                    "source_quote": "고객 확인 후 배포 일정은 2026-05-20까지 확정하겠습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [
                "고객 확인 후 배포 일정 확정하기의 confidence가 low다.",
                "고객 확인 후 배포 일정이 확정되지 않았습니다.",
            ],
        }

        result = summarize.validate_structure(
            structure,
            "김민수: 고객 확인 후 배포 일정은 2026-05-20까지 확정하겠습니다.",
        )

        self.assertIn("고객 확인 후 배포 일정 확정하기: 내용 확인 필요", result["warnings"])
        self.assertIn("고객 확인 후 배포 일정이 확정되지 않았습니다.", result["warnings"])
        self.assertFalse(any("confidence" in warning for warning in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
