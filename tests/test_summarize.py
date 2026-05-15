"""Unit tests for the meeting summarization pipeline."""

from __future__ import annotations

import importlib
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def import_summarize_with_fakes():
    """Import summarize.py with fake OpenAI/dotenv modules."""
    fake_dotenv = types.SimpleNamespace(load_dotenv=lambda: None)
    fake_openai = types.SimpleNamespace(OpenAI=Mock)

    with patch.dict(sys.modules, {"dotenv": fake_dotenv, "openai": fake_openai}):
        sys.modules.pop("summarize", None)
        return importlib.import_module("summarize")


summarize = import_summarize_with_fakes()


def empty_track_b_structure() -> dict[str, list]:
    """Return the minimal structured extraction shape used by summarize.py."""
    return {
        "summary_facts": [],
        "decisions": [],
        "action_items": [],
        "speaker_highlights": [],
        "warnings": [],
    }


class SummarizeTests(unittest.TestCase):
    """Test each summarization stage without real API calls."""

    def test_preprocess_removes_only_standalone_fillers_and_merges_speakers(self) -> None:
        """단독 추임새만 제거하고 같은 화자의 연속 발언은 병합합니다."""
        transcript = """
회의일: 2026년 5월 14일
김민수: 아
김민수: 네네 확인했습니다
김민수: 배포는 금요일까지 진행하겠습니다.
이서연: 음...
이서연: 품질 검수를 맡겠습니다.
""".strip()

        result = summarize.preprocess_transcript(transcript)

        self.assertEqual(result.meeting_date, "2026-05-14")
        self.assertNotIn("김민수: 아\n", result.text)
        self.assertIn("김민수: 네네 확인했습니다 배포는 금요일까지 진행하겠습니다.", result.text)
        self.assertIn("이서연: 품질 검수를 맡겠습니다.", result.text)

    def test_summarize_transcript_runs_new_pipeline(self) -> None:
        """공개 인터페이스가 새 4단계 파이프라인을 순서대로 호출합니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = empty_track_b_structure()

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(summarize, "render_output", return_value="최종 출력") as render_mock:
            result = summarize.summarize_transcript("raw transcript")

        self.assertEqual(result["minutes"], "최종 출력")
        self.assertEqual(result["summary_facts"], [])
        self.assertEqual(result["action_items"], [])
        extract_mock.assert_called_once_with("정리된 transcript", "2026-05-14", "")
        generate_mock.assert_called_once_with("정리된 transcript", structure, "")
        render_mock.assert_called_once_with(structure, "자연어 회의록")

    def test_summarize_transcript_passes_context_to_model_steps(self) -> None:
        """팀 컨텍스트가 구조 추출과 회의록 생성 단계로 전달됩니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = empty_track_b_structure()

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(summarize, "render_output", return_value="최종 출력"):
            summarize.summarize_transcript("raw transcript", context="VIP 프로젝트: 중요 고객")

        extract_mock.assert_called_once_with("정리된 transcript", "2026-05-14", "VIP 프로젝트: 중요 고객")
        generate_mock.assert_called_once_with("정리된 transcript", structure, "VIP 프로젝트: 중요 고객")

    def test_summarize_transcript_rejects_empty_input(self) -> None:
        """빈 transcript는 명확한 에러로 실패합니다."""
        with self.assertRaises(RuntimeError):
            summarize.summarize_transcript("   ")

    def test_summarize_transcript_returns_api_result_shape(self) -> None:
        """summarize_transcript는 API 응답에 필요한 구조형 결과를 반환합니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = {
            "summary_facts": ["빠른 요약"],
            "decisions": [{"decision": "진행 확정", "status": "확정"}],
            "action_items": [{"task": "후속 작업", "owner": "김민수", "due_date": "2026-05-20", "confidence": "high"}],
            "speaker_highlights": ["김민수가 후속 작업을 언급했습니다."],
            "warnings": ["확인 필요"],
        }

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ), patch.object(summarize, "generate_minutes", return_value="자연어 회의록"), patch.object(
            summarize, "render_output", return_value="최종 출력"
        ):
            result = summarize.summarize_transcript("raw transcript")

        self.assertEqual(
            set(result),
            {"minutes", "action_items", "summary_facts", "decisions", "speaker_highlights", "warnings"},
        )
        self.assertEqual(result["minutes"], "최종 출력")
        self.assertEqual(result["action_items"], structure["action_items"])
        self.assertEqual(result["summary_facts"], structure["summary_facts"])
        self.assertEqual(result["decisions"], structure["decisions"])
        self.assertEqual(result["speaker_highlights"], structure["speaker_highlights"])
        self.assertEqual(result["warnings"], structure["warnings"])

    def test_extract_structure_requests_track_b_once(self) -> None:
        """extract_structure는 전처리 텍스트를 Track B 구조 추출 요청으로 전달합니다."""
        fake_client = object()
        with patch.object(summarize, "create_openai_client", return_value=fake_client), patch.object(
            summarize, "request_structured_structure", return_value={**empty_track_b_structure(), "warnings": ["확인 필요"]}
        ) as request_mock:
            result = summarize.extract_structure("정리된 transcript", "2026-05-14")

        self.assertEqual(result["warnings"], ["확인 필요"])
        request_mock.assert_called_once()
        self.assertIn("정리된 transcript", request_mock.call_args.args[1])

    def test_build_extraction_prompt_contains_required_principles(self) -> None:
        """구조 추출 프롬프트가 Track B warning 원칙을 포함합니다."""
        prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14")

        self.assertIn("회의 날짜: 2026-05-14", prompt)
        self.assertIn("스키마에 없는 필드는 생성하지 마라", prompt)
        self.assertIn("summary_facts에는 회의 요약", prompt)
        self.assertIn("decisions에는 명확한 결정", prompt)
        self.assertIn("결정사항에 행동 지시가 포함되면 반드시 action_items", prompt)
        self.assertIn("\"~하기로 했다\", \"~담당\", \"~까지 완료\"", prompt)
        self.assertIn("owner가 없으면 warnings에 추가", prompt)
        self.assertIn("confidence가 low인 항목은 warnings에 추가", prompt)
        self.assertIn("due_date는 \"미정\"으로 두고 warnings에 추가", prompt)
        self.assertIn("1인칭이면 owner를 \"미정\"", prompt)
        self.assertIn("owner와 due_date가 둘 다 명확할 때만 \"high\"", prompt)
        self.assertIn("speaker_highlights에는 주요 발언", prompt)

    def test_context_is_inserted_at_prompt_front(self) -> None:
        """컨텍스트가 있으면 두 프롬프트 맨 앞에 삽입됩니다."""
        context = "홍길동 (홍팀장) - 데이터팀장"
        extraction_prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14", context)
        minutes_prompt = summarize.build_minutes_prompt("회의 내용", empty_track_b_structure(), context)

        self.assertTrue(extraction_prompt.startswith("아래는 이 회의와 관련된 팀 컨텍스트입니다."))
        self.assertTrue(minutes_prompt.startswith("아래는 이 회의와 관련된 팀 컨텍스트입니다."))
        self.assertIn(context, extraction_prompt)
        self.assertIn(context, minutes_prompt)

    def test_request_structured_structure_uses_json_schema_format(self) -> None:
        """OpenAI 요청이 Structured Output JSON schema 옵션을 사용합니다."""
        fake_response = {"output_text": json.dumps(empty_track_b_structure(), ensure_ascii=False)}
        fake_client = types.SimpleNamespace(responses=types.SimpleNamespace(create=Mock(return_value=fake_response)))

        result = summarize.request_structured_structure(fake_client, "prompt")

        self.assertEqual(result, empty_track_b_structure())
        call_kwargs = fake_client.responses.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], summarize.DEFAULT_STRUCTURE_MODEL)
        self.assertEqual(call_kwargs["text"]["format"]["type"], "json_schema")
        self.assertTrue(call_kwargs["text"]["format"]["strict"])
        schema = call_kwargs["text"]["format"]["schema"]
        self.assertEqual(
            schema["required"],
            ["summary_facts", "decisions", "action_items", "speaker_highlights", "warnings"],
        )
        self.assertEqual(
            set(schema["properties"]),
            {"summary_facts", "decisions", "action_items", "speaker_highlights", "warnings"},
        )

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
        self.assertIn("decisions는 주요 결정사항", prompt)
        self.assertIn("speaker_highlights는 주요 발언 요약", prompt)
        self.assertIn("1인칭 표현(저, 제가)은 담당자로 쓰지 말고 \"미정\"", prompt)
        self.assertIn("JSON 내용을 그대로 나열하지 말고", prompt)
        self.assertIn("회의 요약", prompt)
        self.assertIn("주요 결정사항", prompt)
        self.assertIn("액션 아이템", prompt)
        self.assertIn("주요 발언 요약", prompt)

    def test_render_output_combines_warnings_quick_summary_actions_and_full_minutes(self) -> None:
        """render_output은 Track B JSON과 자연어 회의록을 요청 순서대로 조합합니다."""
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

        self.assertLess(output.index("## ⚠️ 확인 필요"), output.index("## 📋 빠른 요약"))
        self.assertLess(output.index("## 📋 빠른 요약"), output.index("## ✅ 액션 아이템"))
        self.assertLess(output.index("## ✅ 액션 아이템"), output.index("## 📝 전체 회의록"))
        self.assertIn("- 배포 확인 기한 필요", output)
        self.assertIn("- 내부 배포 방향을 논의했습니다.", output)
        self.assertIn("- 테스트 모드와 저장 흐름을 검토했습니다.", output)
        self.assertIn("- API 키 설정 확인이 필요합니다.", output)
        self.assertNotIn("이 줄은 빠른 요약에서 제외됩니다.", output)
        self.assertIn("- ⚠️ 담당자: 미정 / 기한: 미정 / 할 일: 배포 확인", output)
        self.assertIn("- 담당자: 이서연 / 기한: 2026-05-20 / 할 일: 샘플 검수", output)
        self.assertNotIn("## 액션 아이템\n-", output)

    def test_extract_response_text_supports_common_response_shapes(self) -> None:
        """Responses API 객체/dict/중첩 content 응답에서 텍스트를 추출합니다."""
        self.assertEqual(
            summarize.extract_response_text(types.SimpleNamespace(output_text="direct text")),
            "direct text",
        )
        self.assertEqual(summarize.extract_response_text({"output_text": "dict text"}), "dict text")
        self.assertEqual(
            summarize.extract_response_text({"output": [{"content": [{"text": "nested text"}]}]}),
            "nested text",
        )

    def test_get_structure_model_uses_env_override(self) -> None:
        """환경 변수로 구조 추출 모델명을 덮어쓸 수 있습니다."""
        with patch.dict(os.environ, {"OPENAI_STRUCTURE_MODEL": "custom-structure"}):
            self.assertEqual(summarize.get_structure_model(), "custom-structure")

    def test_get_summary_model_uses_env_override(self) -> None:
        """환경 변수로 회의록 생성 모델명을 덮어쓸 수 있습니다."""
        with patch.dict(os.environ, {"OPENAI_SUMMARY_MODEL": "custom-summary"}):
            self.assertEqual(summarize.get_summary_model(), "custom-summary")


if __name__ == "__main__":
    unittest.main()
