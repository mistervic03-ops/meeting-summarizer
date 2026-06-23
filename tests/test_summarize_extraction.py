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

class SummarizeExtractionTests(unittest.TestCase):
    """기존 summarize.py 테스트를 도메인별로 분리한 테스트입니다."""

    def test_extract_structure_by_chunks_segments_extracts_and_merges_in_order(self) -> None:
        """chunk runner는 segment, chunk별 extract, merge 순서로만 실행합니다."""
        from summarization import chunk_pipeline

        normalized = summarize.normalize_transcript("김민수: 첫 번째 논의\n이서연: 두 번째 논의")
        chunks = [
            types.SimpleNamespace(
                chunk_id="c_0001",
                start_utterance_id="u_0001",
                end_utterance_id="u_0001",
                text="김민수: 첫 번째 논의",
            ),
            types.SimpleNamespace(
                chunk_id="c_0002",
                start_utterance_id="u_0002",
                end_utterance_id="u_0002",
                text="이서연: 두 번째 논의",
            ),
        ]
        first_structure = {**empty_track_b_structure(), "summary_facts": ["첫 번째"]}
        second_structure = {**empty_track_b_structure(), "summary_facts": ["두 번째"]}
        merged_structure = {**empty_track_b_structure(), "summary_facts": ["첫 번째", "두 번째"]}
        events: list[str] = []

        def segment_side_effect(*args, **kwargs):
            """호출 순서를 확인하기 위해 segment 이벤트를 기록합니다."""
            events.append("segment")
            return chunks

        def extract_side_effect(
            chunk_text: str,
            meeting_date: str,
            context: str = "",
            meeting_type: str = "general",
            glossary_terms: list[str] | None = None,
        ):
            """호출 순서를 확인하기 위해 extract 이벤트를 기록합니다."""
            events.append(f"extract:{chunk_text}")
            if chunk_text == "김민수: 첫 번째 논의":
                return first_structure
            return second_structure

        def merge_side_effect(structures: list[dict[str, list]]):
            """호출 순서를 확인하기 위해 merge 이벤트를 기록합니다."""
            events.append("merge")
            return merged_structure

        with patch.object(chunk_pipeline, "segment_transcript", side_effect=segment_side_effect) as segment_mock, patch.object(
            chunk_pipeline, "extract_structure", side_effect=extract_side_effect
        ) as extract_mock, patch.object(chunk_pipeline, "merge_structures", side_effect=merge_side_effect) as merge_mock:
            result = chunk_pipeline.extract_structure_by_chunks(
                normalized,
                "2026-05-14",
                context="VIP 프로젝트",
                max_utterances=1,
                overlap_utterances=0,
                glossary_terms=["BigQuery"],
            )

        self.assertEqual(result, merged_structure)
        segment_mock.assert_called_once_with(normalized, max_utterances=1, overlap_utterances=0)
        self.assertEqual(extract_mock.call_count, 2)
        extract_mock.assert_any_call(
            "김민수: 첫 번째 논의",
            "2026-05-14",
            "VIP 프로젝트",
            meeting_type="general",
            glossary_terms=["BigQuery"],
        )
        extract_mock.assert_any_call(
            "이서연: 두 번째 논의",
            "2026-05-14",
            "VIP 프로젝트",
            meeting_type="general",
            glossary_terms=["BigQuery"],
        )
        merge_mock.assert_called_once_with([first_structure, second_structure])
        self.assertEqual(events[0], "segment")
        self.assertEqual(events[-1], "merge")
        self.assertCountEqual(
            events[1:-1],
            ["extract:김민수: 첫 번째 논의", "extract:이서연: 두 번째 논의"],
        )

    def test_extract_structure_by_chunks_reports_chunk_progress(self) -> None:
        """chunk runner는 완료된 chunk 수와 전체 chunk 수를 callback으로 알립니다."""
        from summarization import chunk_pipeline

        normalized = summarize.normalize_transcript("김민수: 첫 번째 논의\n이서연: 두 번째 논의")
        chunks = [
            types.SimpleNamespace(
                chunk_id="c_0001",
                start_utterance_id="u_0001",
                end_utterance_id="u_0001",
                text="김민수: 첫 번째 논의",
            ),
            types.SimpleNamespace(
                chunk_id="c_0002",
                start_utterance_id="u_0002",
                end_utterance_id="u_0002",
                text="이서연: 두 번째 논의",
            ),
        ]
        progress_events: list[tuple[int, int]] = []

        with patch.object(chunk_pipeline, "segment_transcript", return_value=chunks), patch.object(
            chunk_pipeline, "extract_structure", return_value=empty_track_b_structure()
        ), patch.object(chunk_pipeline, "merge_structures", return_value=empty_track_b_structure()):
            chunk_pipeline.extract_structure_by_chunks(
                normalized,
                "2026-05-14",
                max_utterances=1,
                overlap_utterances=0,
                progress_callback=lambda completed, total: progress_events.append((completed, total)),
            )

        self.assertEqual(progress_events, [(1, 2), (2, 2)])

    def test_summary_chunk_concurrency_uses_env_with_bounds(self) -> None:
        """SUMMARY_CHUNK_CONCURRENCY는 1~8 범위로 제한됩니다."""
        from summarization import chunk_pipeline

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(chunk_pipeline.get_summary_chunk_concurrency(), 4)
        with patch.dict(os.environ, {"SUMMARY_CHUNK_CONCURRENCY": "12"}):
            self.assertEqual(chunk_pipeline.get_summary_chunk_concurrency(), 8)
        with patch.dict(os.environ, {"SUMMARY_CHUNK_CONCURRENCY": "0"}):
            self.assertEqual(chunk_pipeline.get_summary_chunk_concurrency(), 1)
        with patch.dict(os.environ, {"SUMMARY_CHUNK_CONCURRENCY": "invalid"}):
            self.assertEqual(chunk_pipeline.get_summary_chunk_concurrency(), 4)

    def test_extract_structure_by_chunks_returns_empty_shape_for_empty_transcript(self) -> None:
        """chunk가 없으면 extract나 merge 없이 빈 structure shape를 반환합니다."""
        from summarization import chunk_pipeline

        normalized = summarize.normalize_transcript("   ")

        with patch.object(chunk_pipeline, "extract_structure") as extract_mock, patch.object(
            chunk_pipeline, "merge_structures"
        ) as merge_mock:
            result = chunk_pipeline.extract_structure_by_chunks(normalized, "2026-05-14")

        self.assertEqual(result, empty_track_b_structure())
        extract_mock.assert_not_called()
        merge_mock.assert_not_called()

    def test_extract_structure_by_chunks_does_not_validate_structure(self) -> None:
        """chunk runner는 merge까지만 수행하고 validate_structure는 호출하지 않습니다."""
        from summarization import chunk_pipeline

        normalized = summarize.normalize_transcript("김민수: 배포 확인하겠습니다.")
        chunks = [
            types.SimpleNamespace(
                chunk_id="c_0001",
                start_utterance_id="u_0001",
                end_utterance_id="u_0001",
                text="김민수: 배포 확인하겠습니다.",
            )
        ]
        structure = {**empty_track_b_structure(), "summary_facts": ["배포 확인 논의"]}

        with patch.object(chunk_pipeline, "segment_transcript", return_value=chunks), patch.object(
            chunk_pipeline, "extract_structure", return_value=structure
        ), patch.object(chunk_pipeline, "merge_structures", return_value=structure), patch(
            "summarization.validation.validate_structure"
        ) as validate_mock, patch.object(chunk_pipeline, "ThreadPoolExecutor") as executor_mock:
            result = chunk_pipeline.extract_structure_by_chunks(normalized, "2026-05-14")

        self.assertEqual(result, structure)
        executor_mock.assert_not_called()
        validate_mock.assert_not_called()

    def test_extract_structure_requests_track_b_once(self) -> None:
        """extract_structure는 전처리 텍스트를 Track B 구조 추출 요청으로 전달합니다."""
        fake_client = object()
        request_mock = Mock(return_value={**empty_track_b_structure(), "warnings": ["확인 필요"]})
        extraction_globals = summarize.extract_structure.__globals__
        with patch.dict(
            extraction_globals,
            {
                "get_summarization_provider": Mock(return_value="openai"),
                "create_openai_client": Mock(return_value=fake_client),
                "request_structured_structure": request_mock,
            },
        ):
            result = summarize.extract_structure("정리된 transcript", "2026-05-14")

        self.assertEqual(result["warnings"], ["확인 필요"])
        request_mock.assert_called_once()
        self.assertIn("정리된 transcript", request_mock.call_args.args[1])

    def test_extract_structure_can_use_claude_provider(self) -> None:
        """SUMMARIZATION_PROVIDER=claude이면 구조 추출은 Claude 요청 함수로 분기합니다."""
        request_mock = Mock(return_value={**empty_track_b_structure(), "warnings": ["Claude 확인"]})
        openai_client_mock = Mock()
        extraction_globals = summarize.extract_structure.__globals__
        with patch.dict(
            extraction_globals,
            {
                "get_summarization_provider": Mock(return_value="claude"),
                "create_openai_client": openai_client_mock,
                "request_claude_structured_structure": request_mock,
            },
        ):
            result = summarize.extract_structure("정리된 transcript", "2026-05-14")

        self.assertEqual(result["warnings"], ["Claude 확인"])
        openai_client_mock.assert_not_called()
        request_mock.assert_called_once()
        self.assertIn("정리된 transcript", request_mock.call_args.args[0])

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
        decision_schema = schema["properties"]["decisions"]["items"]
        self.assertEqual(decision_schema["required"], ["decision", "status", "source_quote", "source_utterance_ids"])
        self.assertIn("source_quote", decision_schema["properties"])
        self.assertIn("source_utterance_ids", decision_schema["properties"])
        self.assertNotIn("default", decision_schema["properties"]["source_utterance_ids"])
        action_item_schema = schema["properties"]["action_items"]["items"]
        self.assertEqual(
            action_item_schema["required"],
            ["task", "owner", "due_date", "confidence", "source_quote", "source_utterance_ids"],
        )
        self.assertIn("source_quote", action_item_schema["properties"])
        self.assertIn("source_utterance_ids", action_item_schema["properties"])
        self.assertNotIn("default", action_item_schema["properties"]["source_utterance_ids"])

    def test_request_claude_structured_structure_parses_json_response(self) -> None:
        """Claude 구조 추출은 JSON 텍스트를 기존 structure shape로 정규화합니다."""
        response_json = {
            "summary_facts": ["핵심 논의"],
            "decisions": [],
            "action_items": [],
            "speaker_highlights": [],
            "warnings": [],
        }
        fake_response = types.SimpleNamespace(
            content=[types.SimpleNamespace(text=json.dumps(response_json, ensure_ascii=False))]
        )
        fake_client = types.SimpleNamespace(messages=types.SimpleNamespace(create=Mock(return_value=fake_response)))
        claude_globals = summarize.request_claude_structured_structure.__globals__

        with patch.dict(claude_globals, {"create_anthropic_client": Mock(return_value=fake_client)}):
            result = summarize.request_claude_structured_structure("구조 추출 prompt")

        self.assertEqual(result, response_json)
        call_kwargs = fake_client.messages.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], summarize.DEFAULT_CLAUDE_STRUCTURE_MODEL)
        self.assertIn("구조 추출 prompt", call_kwargs["messages"][0]["content"])
        self.assertIn("<OUTPUT_SCHEMA>", call_kwargs["messages"][0]["content"])
        self.assertIn("JSON object 하나만 반환", call_kwargs["messages"][0]["content"])

    def test_request_claude_structured_structure_ignores_text_after_json_object(self) -> None:
        """Claude 구조 추출은 JSON 뒤에 붙은 설명문을 무시하고 첫 JSON object만 파싱합니다."""
        response_json = {
            "summary_facts": ["핵심 논의"],
            "decisions": [],
            "action_items": [],
            "speaker_highlights": [],
            "warnings": [],
        }
        response_text = f"{json.dumps(response_json, ensure_ascii=False)}\n\n추가 설명입니다."
        fake_response = types.SimpleNamespace(content=[types.SimpleNamespace(text=response_text)])
        fake_client = types.SimpleNamespace(messages=types.SimpleNamespace(create=Mock(return_value=fake_response)))
        claude_globals = summarize.request_claude_structured_structure.__globals__

        with patch.dict(claude_globals, {"create_anthropic_client": Mock(return_value=fake_client)}):
            result = summarize.request_claude_structured_structure("구조 추출 prompt")

        self.assertEqual(result, response_json)

    def test_build_claude_json_prompt_uses_compact_schema(self) -> None:
        """Claude 구조 추출 prompt는 같은 schema를 compact JSON으로 포함합니다."""
        from summarization.llm_provider import build_claude_json_prompt

        prompt = build_claude_json_prompt("구조 추출 prompt")
        schema_text = prompt.split("<OUTPUT_SCHEMA>", 1)[1].split("</OUTPUT_SCHEMA>", 1)[0].strip()
        parsed_schema = json.loads(schema_text)

        self.assertEqual(parsed_schema, summarize.MEETING_STRUCTURE_SCHEMA)
        for key in ("summary_facts", "decisions", "action_items", "speaker_highlights", "warnings"):
            self.assertIn(key, schema_text)
        self.assertNotIn('\n  "properties"', schema_text)
        self.assertNotIn('\n    "summary_facts"', schema_text)

    def test_request_claude_structured_structure_rejects_malformed_json(self) -> None:
        """Claude 구조 추출 응답이 JSON object가 아니면 명확히 실패합니다."""
        fake_response = types.SimpleNamespace(content=[types.SimpleNamespace(text="설명: JSON이 아닙니다")])
        fake_client = types.SimpleNamespace(messages=types.SimpleNamespace(create=Mock(return_value=fake_response)))
        claude_globals = summarize.request_claude_structured_structure.__globals__

        with patch.dict(claude_globals, {"create_anthropic_client": Mock(return_value=fake_client)}):
            with self.assertRaisesRegex(RuntimeError, "Claude structure extraction request failed"):
                summarize.request_claude_structured_structure("구조 추출 prompt")

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

    def test_claude_response_text_supports_common_response_shapes(self) -> None:
        """Claude message 응답 객체와 dict에서 텍스트를 추출합니다."""
        self.assertEqual(
            summarize.extract_claude_response_text(types.SimpleNamespace(content=[types.SimpleNamespace(text="object text")])),
            "object text",
        )
        self.assertEqual(
            summarize.extract_claude_response_text({"content": [{"type": "text", "text": "dict text"}]}),
            "dict text",
        )


if __name__ == "__main__":
    unittest.main()
