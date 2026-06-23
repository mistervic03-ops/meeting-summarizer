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

class SummarizeRenderingTests(unittest.TestCase):
    """기존 summarize.py 테스트를 도메인별로 분리한 테스트입니다."""

    def test_build_summary_result_formats_raw_internal_warnings(self) -> None:
        """공개 SummaryResult warnings는 내부 필드명을 사용자 문장으로 정리합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [],
            "speaker_highlights": [],
            "warnings": [
                "owner가 없음",
                "due_date가 '미정'인 항목이 있음",
                "confidence가 'low'인 항목이 있음",
                "source_quote가 없음",
            ],
        }

        result = summarize.build_summary_result(structure, "최종 출력")

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

    def test_render_output_omits_warning_review_section(self) -> None:
        """Markdown 회의록에는 warning 검토 섹션을 렌더링하지 않습니다."""
        structure = {
            "summary_facts": ["요약"],
            "decisions": [],
            "action_items": [],
            "speaker_highlights": [],
            "warnings": [
                "owner가 없음",
                "due_date가 '미정'인 항목이 있음",
                "confidence가 'low'인 항목이 있음",
                "source_quote가 없음",
            ],
        }

        output = summarize.render_output(structure, "## 회의 요약\n내용")

        self.assertNotIn("## ⚠️ 확인 필요", output)
        self.assertNotIn("## 검토 필요", output)
        self.assertNotIn("- 담당자 확인이 필요한 액션 아이템이 있습니다.", output)
        self.assertNotIn("- 기한 확인이 필요한 액션 아이템이 있습니다.", output)
        self.assertNotIn("- 내용 확인이 필요한 항목이 있습니다.", output)
        self.assertNotIn("- 원문 근거 확인이 필요한 항목이 있습니다.", output)
        self.assertIn("## 📋 빠른 요약", output)
        self.assertIn("## ✅ 액션 아이템", output)
        self.assertIn("## 📝 전체 회의록", output)

    def test_render_output_combines_quick_summary_actions_and_full_minutes_without_warnings(self) -> None:
        """render_output은 warning 섹션 없이 Track B JSON과 자연어 회의록을 조합합니다."""
        structure = {
            "summary_facts": [
                "내부 배포 방향을 논의했습니다.",
                "테스트 모드와 저장 흐름을 검토했습니다.",
                "API 키 설정 확인이 필요합니다.",
                "이 줄은 빠른 요약에서 제외됩니다.",
            ],
            "decisions": [{"decision": "Streamlit 기반으로 우선 진행", "status": "확정"}],
            "action_items": [
                {"task": "배포 확인", "owner": "저", "due_date": "미정", "confidence": "low"},
                {"task": "샘플 검수", "owner": "이서연", "due_date": "2026-05-20", "confidence": "high"},
            ],
            "speaker_highlights": ["이서연은 샘플 검수 필요성을 언급했습니다."],
            "warnings": ["배포 확인 기한 필요"],
        }
        minutes = """
## 회의 요약
- 내부 배포 방향을 논의했습니다.

## 주요 결정사항
- Streamlit 기반으로 우선 진행합니다.

## 액션 아이템
- 담당자: 김민수 / 할 일: 배포 확인

## 주요 발언 요약
- 이서연은 샘플 검수가 필요하다고 말했습니다.
""".strip()

        output = summarize.render_output(structure, minutes)

        self.assertLess(output.index("## 📋 빠른 요약"), output.index("## ✅ 액션 아이템"))
        self.assertLess(output.index("## ✅ 액션 아이템"), output.index("## 📝 전체 회의록"))
        self.assertNotIn("## ⚠️ 확인 필요", output)
        self.assertNotIn("## 검토 필요", output)
        self.assertNotIn("- 배포 확인 기한 필요", output)
        self.assertIn("- 내부 배포 방향을 논의했습니다.", output)
        self.assertIn("- 테스트 모드와 저장 흐름을 검토했습니다.", output)
        self.assertIn("- API 키 설정 확인이 필요합니다.", output)
        self.assertNotIn("이 줄은 빠른 요약에서 제외됩니다.", output)
        self.assertIn("- 배포 확인", output)
        self.assertIn("- 샘플 검수 (담당자: 이서연 / 기한: 2026-05-20)", output)
        self.assertNotIn("담당자: 미정", output)
        self.assertNotIn("담당자: 확인 필요", output)
        self.assertNotIn("기한: 미정", output)
        self.assertNotIn("할 일:", output)
        self.assertNotIn("- ⚠️", output)
        self.assertNotIn("## 액션 아이템\n-", output)

    def test_render_output_formats_action_items_task_first_with_optional_metadata(self) -> None:
        """Markdown 액션 아이템은 업무명을 먼저 표시하고 의미 있는 metadata만 붙입니다."""
        structure = {
            "summary_facts": ["요약"],
            "decisions": [],
            "action_items": [
                {"task": "POC 환경 구성", "owner": "미정", "due_date": "검토 필요", "confidence": "low"},
                {"task": "회의록 공유", "owner": "김민수", "due_date": "확인 필요", "confidence": "low"},
                {"task": "데이터 정제 작업 완료", "owner": " 확인 필요 ", "due_date": "이번주 안", "confidence": "low"},
                {"task": "발표자료 준비", "owner": "이서연", "due_date": "6월 10일", "confidence": "high"},
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        output = summarize.render_output(structure, "## 회의 요약\n내용")

        self.assertIn("- POC 환경 구성", output)
        self.assertIn("- 회의록 공유 (담당자: 김민수)", output)
        self.assertIn("- 데이터 정제 작업 완료 (기한: 이번주 안)", output)
        self.assertIn("- 발표자료 준비 (담당자: 이서연 / 기한: 6월 10일)", output)
        self.assertNotIn("담당자: 미정", output)
        self.assertNotIn("담당자: 확인 필요", output)
        self.assertNotIn("담당자: 검토 필요", output)
        self.assertNotIn("기한: 미정", output)
        self.assertNotIn("기한: 확인 필요", output)
        self.assertNotIn("기한: 검토 필요", output)
        self.assertNotIn("담당자: 확인 필요 / 기한:", output)
        self.assertNotIn("할 일:", output)
        self.assertNotIn("- ⚠️", output)

    def test_render_output_removes_generated_minutes_title_headings(self) -> None:
        """모델이 생성한 최상단 회의록 제목은 backend wrapper와 중복되지 않게 제거합니다."""
        structure = empty_track_b_structure()

        for title in ("# 회의록", "## 회의록", "# 전체 회의록", "## 전체 회의록"):
            with self.subTest(title=title):
                output = summarize.render_output(structure, f"{title}\n\n## 회의 요약\n내용")
                full_minutes = output.split("## 📝 전체 회의록\n", 1)[1]

                self.assertTrue(full_minutes.startswith("## 회의 요약\n내용"))
                self.assertNotIn(title, full_minutes)

    def test_render_output_removes_horizontal_rule_only_lines(self) -> None:
        """모델이 생성한 Markdown 구분선 전용 줄은 최종 회의록에서 제거합니다."""
        structure = empty_track_b_structure()
        minutes = """
# 회의록
---

## 회의 요약
내용

----

## 주요 결정사항
- 진행합니다.
***
___
""".strip()

        output = summarize.render_output(structure, minutes)
        full_minutes = output.split("## 📝 전체 회의록\n", 1)[1]

        self.assertNotRegex(full_minutes, r"(?m)^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
        self.assertIn("## 회의 요약\n내용", full_minutes)
        self.assertIn("## 주요 결정사항\n- 진행합니다.", full_minutes)

    def test_build_summary_result_keeps_unresolved_owner_value_for_api(self) -> None:
        """Markdown 표시와 달리 공개 구조화 결과의 owner 값은 호환성을 위해 미정으로 유지합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {"task": "배포 확인", "owner": "저", "due_date": "미정", "confidence": "low"},
                {"task": "샘플 검수", "owner": "김민수", "due_date": "2026-05-20", "confidence": "high"},
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.build_summary_result(structure, "회의록")

        self.assertEqual(result["action_items"][0]["owner"], "미정")
        self.assertEqual(result["action_items"][0]["due_date"], "미정")
        self.assertEqual(result["action_items"][1]["owner"], "김민수")
        self.assertEqual(result["action_items"][1]["due_date"], "2026-05-20")

    def test_render_output_separates_discussion_notes_for_technical_review(self) -> None:
        """기술 리뷰의 downgrade 메모는 요약이 아니라 논의 메모로 표시합니다."""
        structure = {
            "summary_facts": [
                "아키텍처 구조와 데이터 흐름을 설명했습니다.",
                "논의 메모: 신규 구조 적용 가능성이 언급되었습니다.",
            ],
            "decisions": [],
            "action_items": [],
            "speaker_highlights": ["이서연은 API 구조를 설명했습니다."],
            "warnings": ["결정 후보 '신규 구조 적용 가능성'는 확정 근거가 약해 논의 메모로 분류했습니다."],
        }

        output = summarize.render_output(structure, "## 회의 요약\n기술 논의", meeting_type="technical_review")

        self.assertIn("## 주요 논의", output)
        self.assertIn("## 논의 메모", output)
        self.assertIn("- 신규 구조 적용 가능성이 언급되었습니다.", output)
        self.assertLess(output.index("## 주요 논의"), output.index("## 논의 메모"))
        self.assertNotIn("논의 메모: 신규 구조 적용 가능성이 언급되었습니다.", output)
        self.assertNotIn("확정 근거가 약해", output)

    def test_render_output_omits_non_execution_warnings(self) -> None:
        """비운영 회의도 warning 검토 섹션을 Markdown에 렌더링하지 않습니다."""
        structure = {
            "summary_facts": ["요구사항을 검토했습니다."],
            "decisions": [],
            "action_items": [],
            "speaker_highlights": [],
            "warnings": ["요구사항 후속 논의: 담당자 및 기한 확인 필요"],
        }

        output = summarize.render_output(structure, "## 회의 요약\n고객 논의", meeting_type="customer_meeting")

        self.assertIn("## 고객 관심사 및 검토 포인트", output)
        self.assertNotIn("## 검토 메모", output)
        self.assertNotIn("## 검토 필요", output)
        self.assertNotIn("요구사항 후속 논의: 추가 확인이 필요할 수 있습니다", output)
        self.assertNotIn("담당자 및 기한 확인 필요", output)


if __name__ == "__main__":
    unittest.main()
