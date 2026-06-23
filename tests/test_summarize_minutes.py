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

class SummarizeMinutesTests(unittest.TestCase):
    """기존 summarize.py 테스트를 도메인별로 분리한 테스트입니다."""

    def test_glossary_is_inserted_into_minutes_prompt_after_context(self) -> None:
        """회의록 생성 프롬프트는 컨텍스트 뒤 검증 JSON 지침 앞에 용어집을 넣습니다."""
        prompt = summarize.build_minutes_prompt(
            "회의 내용",
            empty_track_b_structure(),
            context="홍길동 - 데이터팀장",
            glossary_terms=["Tableau"],
        )

        self.assertIn("- Tableau", prompt)
        self.assertLess(prompt.index("아래는 이 회의 이해를 돕기 위한 배경 메모입니다."), prompt.index("아래 용어집"))
        self.assertLess(prompt.index("아래 용어집"), prompt.index("아래 JSON은 이미 검증된 사실입니다."))

    def test_generate_minutes_uses_gpt54_and_verified_json_prompt(self) -> None:
        """generate_minutes는 검증 JSON 기준 프롬프트로 자연어 회의록을 요청합니다."""
        structure = {
            "summary_facts": ["내부 배포 방향을 논의했습니다."],
            "decisions": [{"decision": "Streamlit 기반으로 우선 진행", "status": "확정"}],
            "action_items": [{"task": "배포 확인", "owner": "김민수", "due_date": "미정", "confidence": "high"}],
            "speaker_highlights": ["김민수는 배포 확인 필요성을 언급했습니다."],
            "warnings": ["기한 확인 필요"],
        }
        fake_client = types.SimpleNamespace(
            responses=types.SimpleNamespace(create=Mock(return_value={"output_text": "자연스러운 회의록"}))
        )

        with patch.object(summarize, "create_openai_client", return_value=fake_client):
            result = summarize.generate_minutes(
                summarize.PreprocessedTranscript("김민수: 배포 확인하겠습니다.", "2026-05-14"),
                structure,
            )

        self.assertEqual(result, "자연스러운 회의록")
        call_kwargs = fake_client.responses.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], summarize.DEFAULT_SUMMARY_MODEL)
        prompt = call_kwargs["input"][1]["content"]
        self.assertIn("아래 JSON은 이미 검증된 사실입니다.", prompt)
        self.assertIn("회의록 작성 시 반드시 이 JSON을 기준", prompt)
        self.assertIn("원문은 표현과 문맥을 자연스럽게 다듬기 위한 참고용", prompt)
        self.assertIn("summary_facts는 회의 요약", prompt)
        self.assertIn("decisions는 status에 따라 확정 결정과 미확정 논의로 구분", prompt)
        self.assertIn("speaker_highlights는 주요 발언/논의 포인트", prompt)
        self.assertIn("액션 아이템 담당자는 검증 JSON의 owner를 따르고", prompt)
        self.assertIn("1인칭 표현(저, 제가) 자체를 담당자명으로 쓰지 마세요", prompt)
        self.assertIn("회의록 작성 초점", prompt)
        self.assertIn("JSON 내용을 그대로 나열하지 말고", prompt)
        self.assertIn("숫자 범위 표현에 물결표(~)를 사용하지 마세요", prompt)
        self.assertIn('"10~20건" 대신 "10-20건"', prompt)
        self.assertIn("회의 요약", prompt)
        self.assertIn("주요 결정사항", prompt)
        self.assertIn("액션 아이템", prompt)
        self.assertIn("주요 발언/논의 포인트", prompt)

    def test_generate_minutes_can_use_claude_provider(self) -> None:
        """SUMMARIZATION_PROVIDER=claude이면 회의록 생성은 Claude 요청 함수로 분기합니다."""
        structure = empty_track_b_structure()
        claude_request_mock = Mock(return_value="Claude 회의록")
        openai_client_mock = Mock()

        with patch.object(summarize, "get_summarization_provider", Mock(return_value="claude")), patch.object(
            summarize, "request_claude_minutes_generation", claude_request_mock
        ), patch.object(summarize, "create_openai_client", openai_client_mock):
            result = summarize.generate_minutes("회의 내용", structure)

        self.assertEqual(result, "Claude 회의록")
        openai_client_mock.assert_not_called()
        claude_request_mock.assert_called_once()
        self.assertIn("아래 JSON은 이미 검증된 사실입니다.", claude_request_mock.call_args.args[0])

    def test_request_claude_minutes_generation_returns_text(self) -> None:
        """Claude 회의록 생성은 message content의 텍스트를 반환합니다."""
        fake_response = types.SimpleNamespace(content=[types.SimpleNamespace(text="자연스러운 Claude 회의록")])
        fake_client = types.SimpleNamespace(messages=types.SimpleNamespace(create=Mock(return_value=fake_response)))
        claude_globals = summarize.request_claude_minutes_generation.__globals__

        with patch.dict(claude_globals, {"create_anthropic_client": Mock(return_value=fake_client)}):
            result = summarize.request_claude_minutes_generation("회의록 prompt")

        self.assertEqual(result, "자연스러운 Claude 회의록")
        call_kwargs = fake_client.messages.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], summarize.DEFAULT_CLAUDE_SUMMARY_MODEL)
        self.assertEqual(call_kwargs["messages"], [{"role": "user", "content": "회의록 prompt"}])

    def test_build_minutes_prompt_separates_confirmed_and_tentative_decisions(self) -> None:
        """회의록 생성 프롬프트는 확정 결정과 미확정 논의를 구분하도록 지시합니다."""
        structure = empty_track_b_structure()
        structure["decisions"] = [
            {"decision": "배포 일정을 확정한다", "status": "확정"},
            {"decision": "온톨로지 구축 방향을 검토한다", "status": "미확정"},
        ]

        prompt = summarize.build_minutes_prompt("회의 내용", structure)

        self.assertIn('status가 "확정"인 항목만 확정된 주요 결정사항', prompt)
        self.assertIn('status가 "미확정"인 항목은 확정 결정처럼 쓰지 말고', prompt)
        self.assertIn('"논의된 방향"', prompt)
        self.assertIn('"검토 중인 사항"', prompt)
        self.assertIn('"추가 확인이 필요한 방향성"', prompt)
        self.assertIn('"결정했다"보다 "논의됐다"', prompt)
        self.assertIn('"검토가 필요하다"', prompt)
        self.assertIn('"방향으로 언급됐다"', prompt)
        self.assertIn('확정 결정이 없으면 "주요 결정사항"을 억지로 만들지 말고', prompt)
        self.assertIn('검토/논의된 방향 (status가 "미확정"인 항목이 있을 때)', prompt)

    def test_build_minutes_prompt_uses_meeting_type_focus(self) -> None:
        """회의록 생성 프롬프트는 meeting_type별 작성 초점을 포함합니다."""
        technical_prompt = summarize.build_minutes_prompt("회의 내용", empty_track_b_structure(), meeting_type="technical_review")
        customer_prompt = summarize.build_minutes_prompt("회의 내용", empty_track_b_structure(), meeting_type="customer_meeting")
        brainstorming_prompt = summarize.build_minutes_prompt("회의 내용", empty_track_b_structure(), meeting_type="brainstorming")
        execution_prompt = summarize.build_minutes_prompt("회의 내용", empty_track_b_structure(), meeting_type="execution")

        self.assertIn("핵심 개념, 아키텍처, 기술 방향", technical_prompt)
        self.assertIn("고객 관심사, 검증 포인트, 협업 방향", customer_prompt)
        self.assertIn("아이디어, 대안, 탐색적 논의", brainstorming_prompt)
        self.assertIn("진행 상황, blocker, 일정", execution_prompt)
        self.assertIn("blocker와 상태 업데이트는 명시적 담당자, 요청, 실행 약속", execution_prompt)

    def test_normalize_generated_minutes_markdown_preserves_regular_content(self) -> None:
        """회의록 Markdown 정리는 의미 있는 heading, bullet, table-like text를 바꾸지 않습니다."""
        from summarization.rendering import normalize_generated_minutes_markdown

        minutes = "## 회의 요약\n\n- 첫 번째 내용\n\n| 항목 | 내용 |\n| --- | --- |\n| A | B |"

        self.assertEqual(normalize_generated_minutes_markdown(minutes), minutes)

    def test_normalize_generated_minutes_markdown_removes_strikethrough_artifacts(self) -> None:
        """Markdown 취소선 self-correction은 제거하고 정상 범위 표기는 보존합니다."""
        from summarization.rendering import normalize_generated_minutes_markdown

        minutes = """
## 회의 요약
- 전환율은 ~~90~~91%로 정리했습니다.
- 달성률은 ~~83~~84%입니다.
- 다음 주 ~~월요일~~화요일에 재확인합니다.
- 정상 범위는 90~91%, 10~15개, 월요일~화요일입니다.
""".strip()

        cleaned_minutes = normalize_generated_minutes_markdown(minutes)

        self.assertIn("- 전환율은 91%로 정리했습니다.", cleaned_minutes)
        self.assertIn("- 달성률은 84%입니다.", cleaned_minutes)
        self.assertIn("- 다음 주 화요일에 재확인합니다.", cleaned_minutes)
        self.assertIn("- 정상 범위는 90~91%, 10~15개, 월요일~화요일입니다.", cleaned_minutes)
        self.assertNotIn("~~90~~91%", cleaned_minutes)
        self.assertNotIn("~~83~~84%", cleaned_minutes)
        self.assertNotIn("~~월요일~~화요일", cleaned_minutes)


if __name__ == "__main__":
    unittest.main()
