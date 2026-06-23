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

class SummarizeWarningFormattingTests(unittest.TestCase):
    """기존 summarize.py 테스트를 도메인별로 분리한 테스트입니다."""

    def test_format_display_warnings_standardizes_generic_korean_warnings(self) -> None:
        """구체 항목이 없는 한국어 warning도 간결한 표준 문장으로 정리합니다."""
        warnings = summarize.format_display_warnings(
            [
                "회의의 일부 결정사항에 대해 담당자가 명확하지 않습니다.",
                "액션 아이템의 기한이 미정이다.",
            ]
        )

        self.assertEqual(
            warnings,
            [
                "담당자 확인이 필요한 액션 아이템이 있습니다.",
                "기한 확인이 필요한 액션 아이템이 있습니다.",
            ],
        )

    def test_format_display_warnings_polishes_generic_action_subjects(self) -> None:
        """일반 action item 주어와 내부 처리 용어는 공개 warning에서 정형 문장으로 바꿉니다."""
        warnings = summarize.format_display_warnings(
            [
                "모든 action item: 담당자 확인 필요",
                "확인 요청된 일부 사항: 담당자 확인 필요",
                "중복되는 항목은 merge에서 하나로 남기기로 함.: 담당자 및 기한 확인 필요",
                "고객사 데모 계정 생성: 기한 확인 필요",
            ]
        )

        self.assertIn("담당자 확인이 필요한 액션 아이템이 있습니다.", warnings)
        self.assertIn("담당자 및 기한 확인이 필요한 액션 아이템이 있습니다.", warnings)
        self.assertIn("고객사 데모 계정 생성: 기한 확인 필요", warnings)
        self.assertEqual(warnings.count("담당자 확인이 필요한 액션 아이템이 있습니다."), 1)
        self.assertFalse(any("action item" in warning.lower() or "merge" in warning.lower() for warning in warnings))

    def test_format_display_warnings_filters_source_utterance_id_only_subjects(self) -> None:
        """source utterance ID만 주어인 warning은 공개 warning에 raw ID를 남기지 않습니다."""
        warnings = summarize.format_display_warnings(
            [
                "u_0026: 담당자 확인 필요",
                "u_0015: 기한 확인 필요",
                "u_0031: 담당자 및 기한 확인 필요",
                "u_0042: 원문 근거 확인 필요",
                "u_0043: 내용 확인 필요",
                "u_0050: 추가 확인이 필요할 수 있습니다",
                "U_0007: 담당자 확인 필요",
                "API 응답 오류 재현: 담당자 확인 필요",
                "고객사 데이터 전달: 추가 확인이 필요할 수 있습니다",
            ]
        )

        self.assertIn("담당자 확인이 필요한 액션 아이템이 있습니다.", warnings)
        self.assertIn("기한 확인이 필요한 액션 아이템이 있습니다.", warnings)
        self.assertIn("담당자 및 기한 확인이 필요한 액션 아이템이 있습니다.", warnings)
        self.assertIn("원문 근거 확인이 필요한 항목이 있습니다.", warnings)
        self.assertIn("내용 확인이 필요한 항목이 있습니다.", warnings)
        self.assertIn("API 응답 오류 재현: 담당자 확인 필요", warnings)
        self.assertIn("고객사 데이터 전달: 추가 확인이 필요할 수 있습니다", warnings)
        self.assertEqual(warnings.count("담당자 확인이 필요한 액션 아이템이 있습니다."), 1)
        self.assertFalse(any("u_" in warning.lower() for warning in warnings))
        self.assertFalse(any("추가 확인이 필요할 수 있습니다" == warning for warning in warnings))

    def test_format_display_warnings_polishes_overly_generic_subjects(self) -> None:
        """너무 넓은 주어는 구체 task가 아니라 일반 warning으로 접습니다."""
        warnings = summarize.format_display_warnings(
            [
                "결정: 담당자 확인 필요",
                "업무: 담당자 및 기한 확인 필요",
                "사항: 원문 근거 확인 필요",
                "검증 결과 테이블 위치 공유: 기한 확인 필요",
                "배치 지연 알람 룰 포함: 담당자 및 기한 확인 필요",
            ]
        )

        self.assertIn("담당자 확인이 필요한 액션 아이템이 있습니다.", warnings)
        self.assertIn("담당자 및 기한 확인이 필요한 액션 아이템이 있습니다.", warnings)
        self.assertIn("원문 근거 확인이 필요한 항목이 있습니다.", warnings)
        self.assertIn("검증 결과 테이블 위치 공유: 기한 확인 필요", warnings)
        self.assertIn("배치 지연 알람 룰 포함: 담당자 및 기한 확인 필요", warnings)
        self.assertNotIn("결정: 담당자 확인 필요", warnings)
        self.assertNotIn("업무: 담당자 및 기한 확인 필요", warnings)
        self.assertNotIn("사항: 원문 근거 확인 필요", warnings)

    def test_validate_structure_deduplicates_exact_action_warnings(self) -> None:
        """같은 업무의 명확한 warning은 중복 없이 표준 문장으로 합칩니다."""
        structure = {
            "summary_facts": [],
            "decisions": [
                {
                    "decision": "발표자료를 6월 10일까지 준비하기로 했다",
                    "status": "확정",
                    "source_quote": "발표자료를 6월 10일까지 준비하기로 했습니다.",
                },
                {
                    "decision": "데이터 정제 작업을 이번 주 안으로 완료하기로 했다",
                    "status": "확정",
                    "source_quote": "데이터 정제 작업을 이번 주 안으로 완료하기로 했습니다.",
                },
            ],
            "action_items": [
                {
                    "task": "발표자료를 6월 10일까지 준비하기",
                    "owner": "",
                    "due_date": "2026-06-10",
                    "confidence": "high",
                    "source_quote": "발표자료를 6월 10일까지 준비하기로 했습니다.",
                },
                {
                    "task": "데이터 정제 작업을 이번 주 안으로 완료하기",
                    "owner": "",
                    "due_date": "",
                    "confidence": "high",
                    "source_quote": "데이터 정제 작업을 이번 주 안으로 완료하기로 했습니다.",
                },
            ],
            "speaker_highlights": [],
            "warnings": [
                "발표자료 액션 아이템의 담당자가 명확하지 않습니다.",
                "발표자료를 6월 10일까지 준비하기의 담당자가 명확하지 않습니다.",
                "데이터 정제 작업 액션 아이템의 기한이 명확하지 않습니다.",
                "데이터 정제 작업을 이번 주 안으로 완료하기의 담당자가 명확하지 않습니다.",
            ],
        }
        transcript = "\n".join(
            [
                "김민수: 발표자료를 6월 10일까지 준비하기로 했습니다.",
                "이서연: 데이터 정제 작업을 이번 주 안으로 완료하기로 했습니다.",
            ]
        )

        result = summarize.validate_structure(structure, transcript)

        self.assertIn("발표자료를 6월 10일까지 준비하기: 담당자 확인 필요", result["warnings"])
        self.assertIn("데이터 정제 작업을 이번 주 안으로 완료하기: 담당자 및 기한 확인 필요", result["warnings"])
        self.assertEqual(result["warnings"].count("발표자료를 6월 10일까지 준비하기: 담당자 확인 필요"), 1)
        self.assertEqual(result["warnings"].count("데이터 정제 작업을 이번 주 안으로 완료하기: 담당자 및 기한 확인 필요"), 1)
        self.assertFalse(any("액션 아이템의의" in warning or "의의의" in warning for warning in result["warnings"]))

    def test_validate_structure_does_not_merge_unrelated_decision_action_warnings(self) -> None:
        """서로 다른 업무는 decision/action warning을 의미적으로 합치지 않습니다."""
        structure = {
            "summary_facts": [],
            "decisions": [
                {
                    "decision": "모바일 앱 배포 확정",
                    "status": "확정",
                    "source_quote": "모바일 앱 배포는 확정했습니다.",
                }
            ],
            "action_items": [
                {
                    "task": "웹 배포 확인",
                    "owner": "",
                    "due_date": "2026-06-10",
                    "confidence": "high",
                    "source_quote": "웹 배포 확인은 6월 10일까지 진행합니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }
        transcript = "\n".join(
            [
                "김민수: 모바일 앱 배포는 확정했습니다.",
                "이서연: 웹 배포 확인은 6월 10일까지 진행합니다.",
            ]
        )

        result = summarize.validate_structure(structure, transcript)

        self.assertIn("웹 배포 확인: 담당자 확인 필요", result["warnings"])
        self.assertFalse(any("확정되었지만" in warning for warning in result["warnings"]))

    def test_validate_structure_keeps_source_quote_warning_after_simplified_formatting(self) -> None:
        """단순 표시 형식에서도 source_quote 검증 warning은 사라지지 않습니다."""
        structure = {
            "summary_facts": [],
            "decisions": [
                {
                    "decision": "발표자료를 준비하기로 했다",
                    "status": "확정",
                    "source_quote": "발표자료를 준비하기로 했습니다.",
                }
            ],
            "action_items": [
                {
                    "task": "발표자료 준비하기",
                    "owner": "",
                    "due_date": "2026-06-10",
                    "confidence": "high",
                    "source_quote": "원문에 없는 발표자료 근거입니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.validate_structure(structure, "김민수: 발표자료를 준비하기로 했습니다.")

        self.assertIn("발표자료 준비하기: 담당자 확인 필요", result["warnings"])
        self.assertIn("발표자료 준비하기: 원문 근거 확인 필요", result["warnings"])
        self.assertFalse(
            any(
                internal_name in warning
                for warning in result["warnings"]
                for internal_name in ("owner", "due_date", "confidence", "source_quote")
            )
        )


if __name__ == "__main__":
    unittest.main()
