"""회의 요약 파이프라인 단위 테스트입니다."""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def import_summarize_with_fakes():
    """fake OpenAI/dotenv 모듈로 summarize.py를 import합니다."""
    fake_dotenv = types.SimpleNamespace(load_dotenv=lambda: None)
    fake_openai = types.SimpleNamespace(OpenAI=Mock)

    with patch.dict(sys.modules, {"dotenv": fake_dotenv, "openai": fake_openai}):
        sys.modules.pop("summarize", None)
        return importlib.import_module("summarize")


summarize = import_summarize_with_fakes()


def empty_track_b_structure() -> dict[str, list]:
    """summarize.py에서 사용하는 최소 구조화 추출 형태를 반환합니다."""
    return {
        "summary_facts": [],
        "decisions": [],
        "action_items": [],
        "speaker_highlights": [],
        "warnings": [],
    }


def collect_schema_objects(schema: dict) -> list[dict]:
    """JSON schema 안의 object schema를 모두 수집합니다."""
    objects: list[dict] = []
    if schema.get("type") == "object":
        objects.append(schema)
    for value in schema.get("properties", {}).values():
        if isinstance(value, dict):
            objects.extend(collect_schema_objects(value))
    items = schema.get("items")
    if isinstance(items, dict):
        objects.extend(collect_schema_objects(items))
    return objects


def schema_contains_key(schema: object, key: str) -> bool:
    """JSON schema 안에 특정 key가 남아 있는지 확인합니다."""
    if isinstance(schema, dict):
        return key in schema or any(schema_contains_key(value, key) for value in schema.values())
    if isinstance(schema, list):
        return any(schema_contains_key(value, key) for value in schema)
    return False


class SummarizeTests(unittest.TestCase):
    """실제 API 호출 없이 각 요약 단계를 테스트합니다."""

    def test_step_a_modules_are_reexported_from_summarize(self) -> None:
        """Step A로 이동한 models/schema/prompt 이름은 summarize에서 계속 참조됩니다."""
        from summarization.prompts import build_extraction_prompt
        from summarization.schemas import MEETING_STRUCTURE_SCHEMA

        self.assertEqual(summarize.PreprocessedTranscript.__module__, "summarization.models")
        self.assertEqual(summarize.MEETING_STRUCTURE_SCHEMA, MEETING_STRUCTURE_SCHEMA)
        self.assertEqual(
            summarize.build_extraction_prompt("회의 내용", "2026-05-14"),
            build_extraction_prompt("회의 내용", "2026-05-14"),
        )

    def test_step_b_validation_helpers_are_reexported_from_summarize(self) -> None:
        """Step B로 이동한 validation helper는 summarize에서 계속 참조됩니다."""
        from summarization.validation import format_display_warnings, normalize_action_owner, validate_structure

        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "제가",
                    "due_date": "",
                    "confidence": "high",
                    "source_quote": "",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        self.assertEqual(summarize.validate_structure.__module__, "summarization.validation")
        self.assertEqual(summarize.normalize_action_owner("제가"), normalize_action_owner("제가"))
        self.assertEqual(
            summarize.format_display_warnings(["배포 확인의 owner가 미정이다."]),
            format_display_warnings(["배포 확인의 owner가 미정이다."]),
        )
        self.assertEqual(
            summarize.validate_structure(structure, "김민수: 배포 확인하겠습니다."),
            validate_structure(structure, "김민수: 배포 확인하겠습니다."),
        )

    def test_step_c_normalization_and_profiling_are_reexported_from_summarize(self) -> None:
        """Step C로 이동한 normalization/profiling helper는 summarize에서 계속 참조됩니다."""
        from summarization.normalization import normalize_transcript, preprocess_transcript, structured_transcript_payload_to_normalized_transcript
        from summarization.profiling import analyze_transcript_profile, choose_processing_strategy

        transcript = """
회의일: 2026년 5월 14일
김민수: 아
김민수: 배포 확인은 금요일까지 하겠습니다.
이서연: 이걸로 확정하겠습니다.
""".strip()

        self.assertEqual(summarize.preprocess_transcript.__module__, "summarization.normalization")
        self.assertEqual(summarize.structured_transcript_payload_to_normalized_transcript.__module__, "summarization.normalization")
        self.assertEqual(summarize.analyze_transcript_profile.__module__, "summarization.profiling")
        summarize_preprocessed = summarize.preprocess_transcript(transcript)
        module_preprocessed = preprocess_transcript(transcript)
        self.assertEqual(summarize_preprocessed.text, module_preprocessed.text)
        self.assertEqual(summarize_preprocessed.meeting_date, module_preprocessed.meeting_date)

        summarize_normalized = summarize.normalize_transcript(transcript)
        module_normalized = normalize_transcript(transcript)
        self.assertEqual(summarize_normalized.text, module_normalized.text)
        self.assertEqual(summarize_normalized.meeting_date, module_normalized.meeting_date)
        self.assertEqual(
            [utterance.utterance_id for utterance in summarize_normalized.utterances],
            [utterance.utterance_id for utterance in module_normalized.utterances],
        )
        summarize_profile = summarize.analyze_transcript_profile(summarize.normalize_transcript(transcript))
        module_profile = analyze_transcript_profile(normalize_transcript(transcript))
        self.assertEqual(summarize_profile.char_count, module_profile.char_count)
        self.assertEqual(summarize_profile.utterance_count, module_profile.utterance_count)
        self.assertEqual(summarize_profile.speaker_count, module_profile.speaker_count)
        self.assertEqual(summarize_profile.action_cue_count, module_profile.action_cue_count)
        self.assertEqual(summarize_profile.decision_cue_count, module_profile.decision_cue_count)
        self.assertEqual(summarize_profile.risk_cue_count, module_profile.risk_cue_count)
        self.assertEqual(summarize_profile.requirement_cue_count, module_profile.requirement_cue_count)
        self.assertEqual(summarize_profile.estimated_complexity, module_profile.estimated_complexity)
        self.assertEqual(
            summarize.choose_processing_strategy(summarize.analyze_transcript_profile(summarize.normalize_transcript(transcript))),
            choose_processing_strategy(analyze_transcript_profile(normalize_transcript(transcript))),
        )
        summarize_structured = summarize.structured_transcript_payload_to_normalized_transcript({"utterances": [{"text": "테스트"}]})
        module_structured = structured_transcript_payload_to_normalized_transcript({"utterances": [{"text": "테스트"}]})
        self.assertEqual(summarize_structured.text, module_structured.text)
        self.assertEqual(summarize_structured.meeting_date, module_structured.meeting_date)
        self.assertEqual(
            [utterance.render_for_llm() for utterance in summarize_structured.utterances],
            [utterance.render_for_llm() for utterance in module_structured.utterances],
        )

    def test_remaining_modules_are_reexported_from_summarize(self) -> None:
        """남은 rendering/openai/extraction helper는 summarize에서 계속 참조됩니다."""
        from summarization.openai_utils import extract_response_text
        from summarization.rendering import build_summary_result, render_output

        structure = {
            "summary_facts": ["빠른 요약"],
            "decisions": [{"decision": "진행 확정", "status": "확정", "source_quote": "진행 확정"}],
            "action_items": [
                {
                    "task": "후속 작업",
                    "owner": "김민수",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "후속 작업은 김민수가 2026-05-20까지 진행합니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        self.assertEqual(summarize.render_output.__module__, "summarization.rendering")
        self.assertEqual(summarize.build_summary_result.__module__, "summarization.rendering")
        self.assertEqual(summarize.extract_response_text.__module__, "summarization.openai_utils")
        self.assertEqual(summarize.request_structured_structure.__module__, "summarization.extraction")
        self.assertEqual(summarize.extract_structure.__module__, "summarization.extraction")
        self.assertEqual(
            summarize.render_output(structure, "## 회의 요약\n내용"),
            render_output(structure, "## 회의 요약\n내용"),
        )
        self.assertEqual(
            summarize.extract_response_text({"output": [{"content": [{"text": "nested text"}]}]}),
            extract_response_text({"output": [{"content": [{"text": "nested text"}]}]}),
        )
        public_result = build_summary_result(structure, "최종 출력")
        self.assertEqual(public_result, summarize.build_summary_result(structure, "최종 출력"))
        self.assertNotIn("source_quote", public_result["action_items"][0])
        self.assertNotIn("source_utterance_ids", public_result["action_items"][0])
        self.assertNotIn("source_quote", public_result["decisions"][0])
        self.assertNotIn("source_utterance_ids", public_result["decisions"][0])

    def test_pipeline_orchestration_is_reexported_from_summarize(self) -> None:
        """pipeline orchestration 함수는 새 모듈과 summarize 양쪽에서 참조됩니다."""
        from summarization import pipeline

        self.assertEqual(summarize.summarize_transcript.__module__, "summarization.pipeline")
        self.assertEqual(summarize.summarize_meeting.__module__, "summarization.pipeline")
        self.assertEqual(summarize.run_timed_stage.__module__, "summarization.pipeline")
        self.assertEqual(summarize.generate_minutes.__module__, "summarization.pipeline")
        self.assertEqual(pipeline.run_timed_stage("테스트", lambda value: value + 1, 1)[0], 2)

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

    def test_normalize_transcript_creates_stable_utterance_ids_without_changing_text(self) -> None:
        """normalize_transcript는 stable ID를 만들고 기존 전처리 text와 같은 출력을 유지합니다."""
        transcript = """
회의일: 2026년 5월 14일
김민수: 아
김민수: 네네 확인했습니다
김민수: 배포는 금요일까지 진행하겠습니다.
이서연: 음...
이서연: 품질 검수를 맡겠습니다.
""".strip()

        normalized = summarize.normalize_transcript(transcript)
        preprocessed = summarize.preprocess_transcript(transcript)

        self.assertEqual(normalized.text, preprocessed.text)
        self.assertEqual(normalized.meeting_date, "2026-05-14")
        self.assertEqual([utterance.utterance_id for utterance in normalized.utterances], ["u_0001", "u_0002", "u_0003"])
        self.assertEqual([utterance.index for utterance in normalized.utterances], [0, 1, 2])
        self.assertEqual(normalized.utterances[1].speaker, "김민수")
        self.assertEqual(normalized.utterances[1].text, "네네 확인했습니다 배포는 금요일까지 진행하겠습니다.")
        self.assertIn("김민수: 네네 확인했습니다", normalized.utterances[1].raw_line)
        self.assertIn("김민수: 배포는 금요일까지 진행하겠습니다.", normalized.utterances[1].raw_line)

    def test_normalized_transcript_renders_utterance_ids_and_speakers_for_llm(self) -> None:
        """LLM 입력용 렌더링은 발화 ID와 화자를 함께 보존합니다."""
        normalized = summarize.normalize_transcript(
            """
김민수: 오늘 회의는 네 가지 안건입니다.
이서연: 4월 매출이 전월 대비 증가했습니다.
""".strip()
        )

        self.assertEqual(
            normalized.render_for_llm(),
            "\n".join(
                [
                    "[u_0001] 김민수: 오늘 회의는 네 가지 안건입니다.",
                    "[u_0002] 이서연: 4월 매출이 전월 대비 증가했습니다.",
                ]
            ),
        )

    def test_normalized_transcript_renders_unknown_speaker_for_plain_transcript(self) -> None:
        """화자 라벨이 없는 plain transcript도 LLM 입력용 렌더링에서 깨지지 않습니다."""
        normalized = summarize.normalize_transcript("오늘 회의는 네 가지 안건입니다.")

        self.assertEqual(normalized.text, "오늘 회의는 네 가지 안건입니다.")
        self.assertEqual(normalized.render_for_llm(), "[u_0001] Unknown: 오늘 회의는 네 가지 안건입니다.")

    def test_structured_transcript_payload_to_normalized_transcript_preserves_metadata(self) -> None:
        """structured transcript payload는 발화 ID, 화자, timestamp를 보존합니다."""
        normalized = summarize.structured_transcript_payload_to_normalized_transcript(
            {
                "utterances": [
                    {
                        "utterance_id": "u_0042",
                        "speaker": "영업담당자",
                        "text": "제가 고객사 통화 결과를 공유하겠습니다.",
                        "start_ms": 1200,
                        "end_ms": 4500,
                    }
                ]
            }
        )

        self.assertEqual(normalized.utterances[0].utterance_id, "u_0042")
        self.assertEqual(normalized.utterances[0].speaker, "영업담당자")
        self.assertEqual(normalized.utterances[0].start_ms, 1200)
        self.assertEqual(normalized.utterances[0].end_ms, 4500)
        self.assertEqual(normalized.text, "영업담당자: 제가 고객사 통화 결과를 공유하겠습니다.")
        self.assertEqual(normalized.render_for_llm(), "[u_0042] 영업담당자: 제가 고객사 통화 결과를 공유하겠습니다.")

    def test_structured_transcript_payload_to_normalized_transcript_fills_defaults_and_skips_empty_text(self) -> None:
        """structured payload에서 비어 있는 발화는 제외하고 누락된 ID와 화자는 기본값을 씁니다."""
        normalized = summarize.structured_transcript_payload_to_normalized_transcript(
            {
                "utterances": [
                    {"speaker": "Speaker 1", "text": "   "},
                    {"text": "오늘 회의는 네 가지 안건입니다."},
                    {"speaker": "", "text": "후속 작업은 정리해서 공유하겠습니다."},
                ]
            }
        )

        self.assertEqual([utterance.utterance_id for utterance in normalized.utterances], ["u_0001", "u_0002"])
        self.assertEqual([utterance.speaker for utterance in normalized.utterances], ["Unknown", "Unknown"])
        self.assertEqual(
            normalized.render_for_llm(),
            "\n".join(
                [
                    "[u_0001] Unknown: 오늘 회의는 네 가지 안건입니다.",
                    "[u_0002] Unknown: 후속 작업은 정리해서 공유하겠습니다.",
                ]
            ),
        )

    def test_normalize_transcript_preserves_speakerless_line_handling(self) -> None:
        """speaker 없는 줄은 기존 전처리와 같은 방식으로 유지하거나 직전 발화에 붙입니다."""
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
            "회의 목적 공유\n김민수: 첫 발언입니다. 추가 설명입니다.\n이서연: 확인했습니다.",
        )
        self.assertIsNone(normalized.utterances[0].speaker)
        self.assertEqual(normalized.utterances[1].speaker, "김민수")
        self.assertIn("추가 설명입니다.", normalized.utterances[1].raw_line)

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
                    "[u_0001] Unknown: 회의 목적 공유",
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
        self.assertEqual(
            events,
            ["segment", "extract:김민수: 첫 번째 논의", "extract:이서연: 두 번째 논의", "merge"],
        )

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
        ) as validate_mock:
            result = chunk_pipeline.extract_structure_by_chunks(normalized, "2026-05-14")

        self.assertEqual(result, structure)
        validate_mock.assert_not_called()

    def test_analyze_transcript_profile_counts_speakers_and_cues(self) -> None:
        """transcript profile은 speaker 수와 보수적 cue count를 계산합니다."""
        transcript = """
김민수: 배포 확인은 제가 금요일까지 하겠습니다.
이서연: 방식은 FastAPI로 확정했고 이걸로 진행하기로 했습니다.
박지훈: 지연 리스크와 이슈가 있습니다.
최유진: 고객 요구 조건이 필요합니다.
""".strip()

        profile = summarize.analyze_transcript_profile(summarize.normalize_transcript(transcript))

        self.assertEqual(profile.utterance_count, 4)
        self.assertEqual(profile.speaker_count, 4)
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

    def test_choose_processing_strategy_uses_chunk_for_many_utterances(self) -> None:
        """발화 수가 많은 transcript는 향후 chunk 후보로 분류합니다."""
        lines = [
            f"{'김민수' if index % 2 == 0 else '이서연'}: 일반 논의 내용 {index}입니다."
            for index in range(80)
        ]

        profile = summarize.analyze_transcript_profile(summarize.normalize_transcript("\n".join(lines)))

        self.assertEqual(profile.utterance_count, 80)
        self.assertEqual(summarize.choose_processing_strategy(profile), "chunk")

    def test_choose_processing_strategy_uses_chunk_for_high_cue_density(self) -> None:
        """cue가 많은 transcript는 길지 않아도 chunk 후보로 분류합니다."""
        lines = [
            f"{'김민수' if index % 2 == 0 else '이서연'}: 확인하고 정리해서 공유하겠습니다."
            for index in range(12)
        ]

        profile = summarize.analyze_transcript_profile(summarize.normalize_transcript("\n".join(lines)))

        self.assertEqual(profile.action_cue_count, 48)
        self.assertEqual(summarize.choose_processing_strategy(profile), "chunk")

    def test_choose_processing_strategy_uses_deep_for_very_long_transcript(self) -> None:
        """매우 긴 transcript는 보수적으로 Deep 전략을 선택할 수 있습니다."""
        speakers = ["김민수", "이서연", "박지훈"]
        lines = [f"{speakers[index % len(speakers)]}: 긴 회의 논의 내용 {index}입니다." for index in range(240)]

        profile = summarize.analyze_transcript_profile(summarize.normalize_transcript("\n".join(lines)))

        self.assertEqual(profile.utterance_count, 240)
        self.assertEqual(profile.estimated_complexity, "complex")
        self.assertEqual(summarize.choose_processing_strategy(profile), "deep")

    def test_summarize_transcript_uses_direct_extraction_for_direct_strategy(self) -> None:
        """direct 전략은 기존 단일 extract_structure 흐름을 유지합니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = empty_track_b_structure()
        profile = summarize.TranscriptProfile(
            char_count=10,
            utterance_count=1,
            speaker_count=0,
            action_cue_count=0,
            decision_cue_count=0,
            risk_cue_count=0,
            requirement_cue_count=0,
            estimated_complexity="simple",
        )

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ) as validate_mock, patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(
            summarize, "render_output", return_value="최종 출력"
        ) as render_mock, patch.object(
            summarize, "analyze_transcript_profile", return_value=profile
        ) as profile_mock, patch.object(
            summarize, "choose_processing_strategy", return_value="direct"
        ) as strategy_mock, patch.object(summarize, "extract_structure_by_chunks", create=True) as chunk_runner_mock, patch.object(
            summarize.logger, "info"
        ) as log_mock:
            result = summarize.summarize_transcript("raw transcript")

        self.assertEqual(result["minutes"], "최종 출력")
        self.assertEqual(set(result), {"minutes", "action_items", "summary_facts", "decisions", "speaker_highlights", "warnings"})
        chunk_runner_mock.assert_not_called()
        profile_mock.assert_called_once()
        self.assertEqual(profile_mock.call_args.args[0].text, "정리된 transcript")
        strategy_mock.assert_called_once_with(profile)
        extract_mock.assert_called_once_with(
            "[u_0001] Unknown: 정리된 transcript",
            "2026-05-14",
            "",
            "general",
            glossary_terms=ANY,
        )
        validate_mock.assert_called_once()
        self.assertEqual(validate_mock.call_args.args[0], structure)
        self.assertEqual(validate_mock.call_args.args[1], "정리된 transcript")
        self.assertEqual(validate_mock.call_args.args[2].text, "정리된 transcript")
        generate_mock.assert_called_once_with("정리된 transcript", structure, "", "general", glossary_terms=ANY)
        render_mock.assert_called_once_with(structure, "자연어 회의록", "general")
        self.assertTrue(any(call.args == ("summarize_transcript selected_strategy=%s", "direct") for call in log_mock.call_args_list))
        self.assertTrue(
            any(
                call.args
                and call.args[0].startswith("transcript_profile char_count=%s utterance_count=%s")
                and call.args[-1] == "direct"
                for call in log_mock.call_args_list
            )
        )

    def test_summarize_transcript_uses_provided_normalized_transcript_without_renormalizing(self) -> None:
        """structured path는 제공된 NormalizedTranscript를 우선 사용하고 plain 재정규화를 건너뜁니다."""
        normalized = summarize.NormalizedTranscript(
            utterances=[
                summarize.TranscriptUtterance(
                    utterance_id="u_0099",
                    speaker="Speaker 2",
                    text="제가 고객사 통화 결과를 공유하겠습니다.",
                    index=0,
                    raw_line="Speaker 2: 제가 고객사 통화 결과를 공유하겠습니다.",
                )
            ],
            text="Speaker 2: 제가 고객사 통화 결과를 공유하겠습니다.",
            meeting_date="2026-05-14",
        )
        structure = empty_track_b_structure()
        profile = summarize.TranscriptProfile(
            char_count=30,
            utterance_count=1,
            speaker_count=1,
            action_cue_count=1,
            decision_cue_count=0,
            risk_cue_count=0,
            requirement_cue_count=0,
            estimated_complexity="simple",
        )

        with patch.object(summarize, "preprocess_transcript") as preprocess_mock, patch.object(
            summarize, "normalize_transcript"
        ) as normalize_mock, patch.object(
            summarize, "analyze_transcript_profile", return_value=profile
        ), patch.object(
            summarize, "choose_processing_strategy", return_value="direct"
        ), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ) as validate_mock, patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(summarize, "render_output", return_value="최종 출력"):
            result = summarize.summarize_transcript("plain fallback text", normalized_transcript=normalized)

        self.assertEqual(result["minutes"], "최종 출력")
        preprocess_mock.assert_not_called()
        normalize_mock.assert_not_called()
        extract_mock.assert_called_once_with(
            "[u_0099] Speaker 2: 제가 고객사 통화 결과를 공유하겠습니다.",
            "2026-05-14",
            "",
            "general",
            glossary_terms=ANY,
        )
        validate_mock.assert_called_once()
        self.assertEqual(validate_mock.call_args.args[1], normalized.text)
        self.assertIs(validate_mock.call_args.args[2], normalized)
        generate_mock.assert_called_once_with(normalized.text, structure, "", "general", glossary_terms=ANY)

    def test_summarize_transcript_uses_chunk_extraction_for_chunk_strategy(self) -> None:
        """chunk 전략은 chunk runner 결과를 merge 후 validation으로 한 번만 넘깁니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        chunk_structure = {**empty_track_b_structure(), "summary_facts": ["chunk 결과"]}
        validated_structure = {**empty_track_b_structure(), "summary_facts": ["검증된 chunk 결과"]}
        profile = summarize.TranscriptProfile(
            char_count=9000,
            utterance_count=80,
            speaker_count=2,
            action_cue_count=0,
            decision_cue_count=0,
            risk_cue_count=0,
            requirement_cue_count=0,
            estimated_complexity="standard",
        )

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure"
        ) as extract_mock, patch.object(summarize, "validate_structure", return_value=validated_structure) as validate_mock, patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(summarize, "render_output", return_value="최종 출력") as render_mock, patch.object(
            summarize, "analyze_transcript_profile", return_value=profile
        ), patch.object(summarize, "choose_processing_strategy", return_value="chunk"), patch.object(
            summarize, "extract_structure_by_chunks", create=True, return_value=chunk_structure
        ) as chunk_runner_mock, patch.object(summarize.logger, "info") as log_mock:
            result = summarize.summarize_transcript("raw transcript")

        self.assertEqual(result["minutes"], "최종 출력")
        extract_mock.assert_not_called()
        chunk_runner_mock.assert_called_once()
        normalized_arg, meeting_date_arg, context_arg = chunk_runner_mock.call_args.args
        self.assertEqual(normalized_arg.text, "정리된 transcript")
        self.assertEqual(meeting_date_arg, "2026-05-14")
        self.assertEqual(context_arg, "")
        self.assertEqual(chunk_runner_mock.call_args.kwargs["meeting_type"], "general")
        self.assertEqual(chunk_runner_mock.call_args.kwargs["glossary_terms"], summarize.get_summary_glossary_terms())
        validate_mock.assert_called_once()
        self.assertEqual(validate_mock.call_args.args[0], chunk_structure)
        self.assertEqual(validate_mock.call_args.args[1], "정리된 transcript")
        self.assertEqual(validate_mock.call_args.args[2].text, "정리된 transcript")
        generate_mock.assert_called_once_with("정리된 transcript", validated_structure, "", "general", glossary_terms=ANY)
        render_mock.assert_called_once_with(validated_structure, "자연어 회의록", "general")
        self.assertTrue(any(call.args == ("summarize_transcript using chunk extraction path",) for call in log_mock.call_args_list))

    def test_summarize_transcript_loads_glossary_once_for_chunk_extraction(self) -> None:
        """chunk 경로에서도 요약 용어집은 summarize_transcript 단위로 한 번만 로드됩니다."""
        transcript = "\n".join(f"김민수: {index}번째 확인하겠습니다." for index in range(100))
        structure = empty_track_b_structure()
        glossary_terms = ["BigQuery", "Tableau"]

        with patch.object(summarize, "get_summary_glossary_terms", return_value=glossary_terms) as glossary_mock, patch.object(
            summarize,
            "extract_structure_by_chunks",
            create=True,
            return_value=structure,
        ) as chunk_runner_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ), patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(
            summarize, "render_output", return_value="최종 출력"
        ):
            summarize.summarize_transcript(transcript)

        glossary_mock.assert_called_once_with()
        chunk_runner_mock.assert_called_once()
        self.assertEqual(chunk_runner_mock.call_args.kwargs["glossary_terms"], glossary_terms)
        generate_mock.assert_called_once_with(ANY, structure, "", "general", glossary_terms=glossary_terms)

    def test_summarize_transcript_cleans_chunk_public_warnings(self) -> None:
        """chunk mode에서 병합된 raw warning도 공개 결과에서는 표시용 문장으로 정리합니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        chunk_structure = {
            **empty_track_b_structure(),
            "warnings": [
                "owner가 없음",
                "due_date가 '미정'인 항목이 있음",
                "confidence가 'low'인 항목이 있음",
                "source_quote가 없음",
            ],
        }
        profile = summarize.TranscriptProfile(
            char_count=9000,
            utterance_count=80,
            speaker_count=2,
            action_cue_count=0,
            decision_cue_count=0,
            risk_cue_count=0,
            requirement_cue_count=0,
            estimated_complexity="standard",
        )

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure"
        ) as extract_mock, patch.object(summarize, "extract_structure_by_chunks", create=True, return_value=chunk_structure), patch.object(
            summarize, "validate_structure", return_value=chunk_structure
        ), patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ), patch.object(summarize, "render_output", return_value="최종 출력"), patch.object(
            summarize, "analyze_transcript_profile", return_value=profile
        ), patch.object(summarize, "choose_processing_strategy", return_value="chunk"):
            result = summarize.summarize_transcript("raw transcript")

        extract_mock.assert_not_called()
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

    def test_summarize_transcript_uses_chunk_extraction_for_deep_strategy(self) -> None:
        """deep 전략은 아직 고급 처리 없이 chunk pipeline으로 안전하게 fallback합니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        chunk_structure = empty_track_b_structure()
        profile = summarize.TranscriptProfile(
            char_count=40000,
            utterance_count=240,
            speaker_count=4,
            action_cue_count=0,
            decision_cue_count=0,
            risk_cue_count=0,
            requirement_cue_count=0,
            estimated_complexity="complex",
        )

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure"
        ) as extract_mock, patch.object(summarize, "validate_structure", return_value=chunk_structure) as validate_mock, patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ), patch.object(summarize, "render_output", return_value="최종 출력"), patch.object(
            summarize, "analyze_transcript_profile", return_value=profile
        ), patch.object(summarize, "choose_processing_strategy", return_value="deep"), patch.object(
            summarize, "extract_structure_by_chunks", create=True, return_value=chunk_structure
        ) as chunk_runner_mock, patch.object(summarize.logger, "info") as log_mock:
            result = summarize.summarize_transcript("raw transcript")

        self.assertEqual(result["minutes"], "최종 출력")
        extract_mock.assert_not_called()
        chunk_runner_mock.assert_called_once()
        validate_mock.assert_called_once()
        self.assertEqual(validate_mock.call_args.args[0], chunk_structure)
        self.assertEqual(validate_mock.call_args.args[1], "정리된 transcript")
        self.assertEqual(validate_mock.call_args.args[2].text, "정리된 transcript")
        self.assertTrue(any(call.args == ("deep strategy currently uses chunk pipeline",) for call in log_mock.call_args_list))

    def test_summarize_transcript_runs_new_pipeline(self) -> None:
        """공개 인터페이스가 검증 단계를 포함한 파이프라인을 순서대로 호출합니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = empty_track_b_structure()

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ) as validate_mock, patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(summarize, "render_output", return_value="최종 출력") as render_mock:
            result = summarize.summarize_transcript("raw transcript")

        self.assertEqual(result["minutes"], "최종 출력")
        self.assertEqual(result["summary_facts"], [])
        self.assertEqual(result["action_items"], [])
        extract_mock.assert_called_once_with(
            "[u_0001] Unknown: 정리된 transcript",
            "2026-05-14",
            "",
            "general",
            glossary_terms=ANY,
        )
        validate_mock.assert_called_once()
        self.assertEqual(validate_mock.call_args.args[0], structure)
        self.assertEqual(validate_mock.call_args.args[1], "정리된 transcript")
        self.assertEqual(validate_mock.call_args.args[2].text, "정리된 transcript")
        generate_mock.assert_called_once_with("정리된 transcript", structure, "", "general", glossary_terms=ANY)
        render_mock.assert_called_once_with(structure, "자연어 회의록", "general")

    def test_summarize_transcript_passes_context_to_model_steps(self) -> None:
        """팀 컨텍스트가 구조 추출과 회의록 생성 단계로 전달됩니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = empty_track_b_structure()

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ), patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(summarize, "render_output", return_value="최종 출력"):
            summarize.summarize_transcript("raw transcript", context="VIP 프로젝트: 중요 고객")

        extract_mock.assert_called_once_with(
            "[u_0001] Unknown: 정리된 transcript",
            "2026-05-14",
            "VIP 프로젝트: 중요 고객",
            "general",
            glossary_terms=ANY,
        )
        generate_mock.assert_called_once_with("정리된 transcript", structure, "VIP 프로젝트: 중요 고객", "general", glossary_terms=ANY)

    def test_summarize_transcript_passes_meeting_type_to_extraction(self) -> None:
        """meeting_type은 구조 추출 단계까지 전달됩니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = empty_track_b_structure()

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ), patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ) as generate_mock, patch.object(summarize, "render_output", return_value="최종 출력") as render_mock:
            summarize.summarize_transcript("raw transcript", meeting_type="technical_review")

        extract_mock.assert_called_once_with(
            "[u_0001] Unknown: 정리된 transcript",
            "2026-05-14",
            "",
            "technical_review",
            glossary_terms=ANY,
        )
        generate_mock.assert_called_once_with("정리된 transcript", structure, "", "technical_review", glossary_terms=ANY)
        render_mock.assert_called_once_with(structure, "자연어 회의록", "technical_review")

    def test_summarize_transcript_defaults_unknown_meeting_type_to_general(self) -> None:
        """지원하지 않는 meeting_type은 general 정책으로 정규화됩니다."""
        preprocessed = summarize.PreprocessedTranscript("정리된 transcript", "2026-05-14")
        structure = empty_track_b_structure()

        with patch.object(summarize, "preprocess_transcript", return_value=preprocessed), patch.object(
            summarize, "extract_structure", return_value=structure
        ) as extract_mock, patch.object(
            summarize, "validate_structure", return_value=structure
        ), patch.object(
            summarize, "generate_minutes", return_value="자연어 회의록"
        ), patch.object(summarize, "render_output", return_value="최종 출력"):
            summarize.summarize_transcript("raw transcript", meeting_type="unknown")

        extract_mock.assert_called_once_with(
            "[u_0001] Unknown: 정리된 transcript",
            "2026-05-14",
            "",
            "general",
            glossary_terms=ANY,
        )

    def test_summarize_transcript_rejects_empty_input(self) -> None:
        """빈 transcript는 명확한 에러로 실패합니다."""
        with self.assertRaises(RuntimeError):
            summarize.summarize_transcript("   ")

    def test_summarize_transcript_returns_api_result_shape(self) -> None:
        """summarize_transcript는 API 응답에 필요한 구조형 결과를 반환합니다."""
        preprocessed = summarize.PreprocessedTranscript(
            "김민수: 후속 작업은 2026-05-20까지 진행합니다.\n회의 진행 확정",
            "2026-05-14",
        )
        structure = {
            "summary_facts": ["빠른 요약"],
            "decisions": [{"decision": "진행 확정", "status": "확정", "source_quote": "회의 진행 확정"}],
            "action_items": [
                {
                    "task": "후속 작업",
                    "owner": "김민수",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "후속 작업은 2026-05-20까지 진행합니다.",
                }
            ],
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
        self.assertEqual(
            result["action_items"],
            [{"task": "후속 작업", "owner": "김민수", "due_date": "2026-05-20", "confidence": "high"}],
        )
        self.assertNotIn("source_quote", result["action_items"][0])
        self.assertNotIn("source_utterance_ids", result["action_items"][0])
        self.assertEqual(result["summary_facts"], structure["summary_facts"])
        self.assertEqual(result["decisions"], [{"decision": "진행 확정", "status": "확정"}])
        self.assertNotIn("source_quote", result["decisions"][0])
        self.assertNotIn("source_utterance_ids", result["decisions"][0])
        self.assertEqual(result["speaker_highlights"], structure["speaker_highlights"])
        self.assertEqual(result["warnings"], structure["warnings"])

    def test_extract_structure_requests_track_b_once(self) -> None:
        """extract_structure는 전처리 텍스트를 Track B 구조 추출 요청으로 전달합니다."""
        fake_client = object()
        request_mock = Mock(return_value={**empty_track_b_structure(), "warnings": ["확인 필요"]})
        extraction_globals = summarize.extract_structure.__globals__
        with patch.dict(
            extraction_globals,
            {
                "create_openai_client": Mock(return_value=fake_client),
                "request_structured_structure": request_mock,
            },
        ):
            result = summarize.extract_structure("정리된 transcript", "2026-05-14")

        self.assertEqual(result["warnings"], ["확인 필요"])
        request_mock.assert_called_once()
        self.assertIn("정리된 transcript", request_mock.call_args.args[1])

    def test_build_extraction_prompt_contains_required_principles(self) -> None:
        """구조 추출 프롬프트가 Track B warning 원칙을 포함합니다."""
        prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14")

        self.assertIn("회의 날짜: 2026-05-14", prompt)
        self.assertIn("회의 유형: general", prompt)
        self.assertIn("회의 유형은 요약의 강조점을 정하기 위한 참고 정보", prompt)
        self.assertIn("일반 회의에서는 명확한 실행 약속", prompt)
        self.assertIn("스키마에 없는 필드는 생성하지 마세요", prompt)
        self.assertIn("due_date는 확실한 절대 날짜가 원문에 직접 나온 경우가 아니면 ISO 날짜로 바꾸지 말고", prompt)
        self.assertIn("\"금요일 오후 3시\"", prompt)
        self.assertIn("summary_facts에는 회의 요약", prompt)
        self.assertIn("decisions에는 명확한 결정", prompt)
        self.assertIn("decisions의 decision은 회의록에 바로 표시 가능한 자연스러운 한국어 결정사항", prompt)
        self.assertIn("decisions의 decision에 원문 발화를 그대로 복사하지 마세요", prompt)
        self.assertIn("내부 구현 표현처럼 보이는 merge, schema, validation", prompt)
        self.assertIn("decisions의 source_quote", prompt)
        self.assertIn("decisions의 source_utterance_ids", prompt)
        self.assertIn("bracket 없는 값만 사용", prompt)
        self.assertIn("source_quote와 같은 발화의 id", prompt)
        self.assertIn("source_quote에는 원문 근거를 넣되 decision은 정리된 결정 문장", prompt)
        self.assertIn("status는 반드시 \"확정\" 또는 \"미확정\"", prompt)
        self.assertIn("중복 항목은 병합 결과에서 하나만 유지한다", prompt)
        self.assertIn("결정사항에 행동 지시가 포함되면 반드시 action_items", prompt)
        self.assertIn("단순 정책 결정은 action_item으로 만들지 말고 decisions에만", prompt)
        self.assertIn("문서 표기를 데이터 마트로 통일", prompt)
        self.assertIn("10개 내외로 줄이지 말고 명시적 action은 가능한 모두 추출", prompt)
        self.assertIn("\"공유해 주세요\"", prompt)
        self.assertIn("closing recap이나 중간 정리에서 다시 언급된 항목", prompt)
        self.assertIn("\"~하기로 했다\", \"~담당\", \"~까지 완료\"", prompt)
        self.assertIn("action_items의 task는 5~20자 내외의 짧은 업무명", prompt)
        self.assertIn("task에 담당자 이름, 기한, 원문 문장 전체를 넣지 마세요", prompt)
        self.assertIn("owner, due_date, source_quote 필드로 각각 분리", prompt)
        self.assertIn("action_items의 source_quote", prompt)
        self.assertIn("source_quote는 요약하거나 재작성하지 말고 transcript의 실제 발화 일부를 그대로 복사", prompt)
        self.assertIn("대시보드 라우팅은 이서연님 내일 오전까지입니다", prompt)
        self.assertIn("action_items의 source_utterance_ids", prompt)
        self.assertIn("source_quote에는 원문 근거를 넣되 task는 요약된 업무명", prompt)
        self.assertIn("merge, schema, validation", prompt)
        self.assertIn("DWH 적재 로그 확인", prompt)
        self.assertIn("source_quote는 \"미정\"이 아니라 빈 문자열", prompt)
        self.assertIn("삭제하지 말고 confidence를 low", prompt)
        self.assertIn("1인칭으로 업무 수행을 말하면 owner는 \"제가\"나 \"저희\"가 아니라 해당 speaker label", prompt)
        self.assertIn("owner는 \"영업담당자\"", prompt)
        self.assertIn("speaker label이 \"Speaker 2\"처럼 익명이어도 owner로 사용할 수 있습니다", prompt)
        self.assertIn("owner가 실제로 \"미정\"일 때만 담당자 확인 warning", prompt)
        self.assertIn("confidence가 low인 항목은 warnings에 추가", prompt)
        self.assertIn("due_date는 \"미정\"으로 두고 warnings에 추가", prompt)
        self.assertIn("speaker label이 있는 1인칭 발화에서 owner가 speaker label로 해결되면 담당자 확인 warning을 만들지 마세요", prompt)
        self.assertIn("owner에 \"저\", \"제가\", \"저희\" 같은 1인칭 표현 자체를 쓰지 마세요", prompt)
        self.assertIn("owner와 due_date가 둘 다 명확할 때만 \"high\"", prompt)
        self.assertIn("speaker_highlights에는 주요 발언", prompt)

    def test_build_extraction_prompt_includes_meeting_type_policy(self) -> None:
        """회의 유형별 정책이 구조 추출 프롬프트에 삽입됩니다."""
        technical_prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14", meeting_type="technical_review")
        execution_prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14", meeting_type="execution")
        customer_prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14", meeting_type="customer_meeting")
        brainstorming_prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14", meeting_type="brainstorming")
        general_prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14", meeting_type="general")

        self.assertIn("회의 유형: technical_review", technical_prompt)
        self.assertIn("제약 조건, 설계 tradeoff, 리스크", technical_prompt)
        self.assertIn("회의 유형: execution", execution_prompt)
        self.assertIn("진행 상황, 담당자, 일정, 후속 작업을 원문 근거", execution_prompt)
        self.assertIn("회의 유형: customer_meeting", customer_prompt)
        self.assertIn("고객 요구, 우려사항, 요구사항, 리스크", customer_prompt)
        self.assertIn("회의 유형: brainstorming", brainstorming_prompt)
        self.assertIn("아이디어, 선택지, 질문, 우려사항", brainstorming_prompt)
        self.assertIn("회의 유형: general", general_prompt)
        self.assertIn("핵심 논의 맥락을 균형 있게", general_prompt)

        for prompt in [technical_prompt, execution_prompt, customer_prompt, brainstorming_prompt, general_prompt]:
            self.assertIn("회의 유형은 요약의 강조점을 정하기 위한 참고 정보", prompt)
            self.assertIn("항목 생성 여부는 항상 transcript의 명시적 근거", prompt)
            self.assertIn("회의 유형만으로 결정, 액션, 참석자, 사실, 약속을 만들거나 제외하지 마세요", prompt)

    def test_extraction_policy_selects_by_meeting_type(self) -> None:
        """meeting_type에 따라 중앙 정책 profile을 선택합니다."""
        execution_policy = summarize.get_extraction_policy("execution")
        technical_policy = summarize.get_extraction_policy("technical_review")
        fallback_policy = summarize.get_extraction_policy("unknown")

        self.assertEqual(execution_policy.action_threshold, "aggressive")
        self.assertEqual(execution_policy.decision_threshold, "moderate")
        self.assertEqual(technical_policy.action_threshold, "strict")
        self.assertEqual(technical_policy.discussion_emphasis, "technical")
        self.assertEqual(fallback_policy.meeting_type, "general")

    def test_policy_prompt_guidance_is_assembled_from_policy_values(self) -> None:
        """정책 profile 값이 프롬프트 지침 문장으로 조립됩니다."""
        prompt_guidance = summarize.build_policy_prompt_guidance("customer_meeting")

        self.assertIn("회의 유형: customer_meeting", prompt_guidance)
        self.assertIn("회의 유형은 요약의 강조점을 정하기 위한 참고 정보", prompt_guidance)
        self.assertIn("transcript의 명시적 근거를 우선", prompt_guidance)
        self.assertIn("회의 유형만으로 결정, 액션, 참석자, 사실, 약속을 만들거나 제외하지 마세요", prompt_guidance)
        self.assertIn("transcript에 명확한 요청, 담당, 기한, 실행 약속", prompt_guidance)
        self.assertIn("고객 요구, 우려사항, 요구사항, 리스크", prompt_guidance)
        self.assertIn("약한 관심 표현이나 탐색적 논의", prompt_guidance)

    def test_apply_extraction_policy_downgrades_weak_action_items(self) -> None:
        """약한 action 후보는 삭제하지 않고 논의 메모로 낮춥니다."""
        structure = {
            "summary_facts": ["기존 요약"],
            "decisions": [],
            "action_items": [
                {
                    "task": "도입 가능성 검토",
                    "owner": "미정",
                    "due_date": "미정",
                    "confidence": "low",
                    "source_quote": "도입 가능성을 검토해볼 수 있습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.apply_extraction_policy(structure, "technical_review")

        self.assertEqual(result.downgraded_action_count, 1)
        self.assertEqual(result.structure["action_items"], [])
        self.assertIn("논의 메모: 도입 가능성을 검토해볼 수 있습니다.", result.structure["summary_facts"])
        self.assertTrue(any("실행 약속이 불명확" in warning for warning in result.structure["warnings"]))

    def test_apply_extraction_policy_preserves_execution_actions_aggressively(self) -> None:
        """실행 회의는 운영 후속 작업 후보를 약화시키지 않습니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "도입 가능성 검토",
                    "owner": "미정",
                    "due_date": "미정",
                    "confidence": "low",
                    "source_quote": "도입 가능성을 검토해볼 수 있습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.apply_extraction_policy(structure, "execution")

        self.assertEqual(result.downgraded_action_count, 0)
        self.assertEqual(result.structure["action_items"], structure["action_items"])
        self.assertEqual(result.structure["summary_facts"], [])

    def test_technical_review_suppresses_conceptual_actions(self) -> None:
        """기술 설명은 개념 설명 residue를 action_item으로 유지하지 않습니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "아키텍처 구조 검토",
                    "owner": "미정",
                    "due_date": "미정",
                    "confidence": "low",
                    "source_quote": "아키텍처 구조를 설명했습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.apply_extraction_policy(structure, "technical_review")

        self.assertEqual(result.structure["action_items"], [])
        self.assertIn("논의 메모: 아키텍처 구조를 설명했습니다.", result.structure["summary_facts"])

    def test_customer_meeting_suppresses_weak_followup_actions(self) -> None:
        """고객 미팅의 약한 후속 논의 표현은 action_item에서 낮춥니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "요구사항 후속 논의",
                    "owner": "미정",
                    "due_date": "미정",
                    "confidence": "low",
                    "source_quote": "요구사항은 다음에 논의했습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.apply_extraction_policy(structure, "customer_meeting")

        self.assertEqual(result.downgraded_action_count, 1)
        self.assertEqual(result.structure["action_items"], [])
        self.assertIn("논의 메모: 요구사항은 다음에 논의했습니다.", result.structure["summary_facts"])

    def test_strict_policy_downgrades_weak_decisions(self) -> None:
        """강한 확정 표현이 없는 결정 후보는 strict 유형에서 논의 메모로 낮춥니다."""
        structure = {
            "summary_facts": [],
            "decisions": [
                {
                    "decision": "신규 구조 적용 가능성이 언급되었다",
                    "status": "미확정",
                    "source_quote": "신규 구조 적용 가능성이 언급되었습니다.",
                }
            ],
            "action_items": [],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.apply_extraction_policy(structure, "brainstorming")

        self.assertEqual(result.downgraded_decision_count, 1)
        self.assertEqual(result.structure["decisions"], [])
        self.assertIn("논의 메모: 신규 구조 적용 가능성이 언급되었습니다.", result.structure["summary_facts"])
        self.assertTrue(any("확정 근거가 약" in warning for warning in result.structure["warnings"]))

    def test_apply_extraction_policy_preserves_schema_shape(self) -> None:
        """정책 후처리 이후에도 기존 구조화 schema key를 유지합니다."""
        structure = empty_track_b_structure()

        result = summarize.apply_extraction_policy(structure, "technical_review")

        self.assertEqual(
            set(result.structure),
            {"summary_facts", "decisions", "action_items", "speaker_highlights", "warnings"},
        )

    def test_context_is_inserted_at_prompt_front(self) -> None:
        """컨텍스트가 있으면 두 프롬프트 맨 앞에 삽입됩니다."""
        context = "홍길동 (홍팀장) - 데이터팀장"
        extraction_prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14", context)
        minutes_prompt = summarize.build_minutes_prompt("회의 내용", empty_track_b_structure(), context)

        self.assertTrue(extraction_prompt.startswith("아래는 이 회의 이해를 돕기 위한 배경 메모입니다."))
        self.assertTrue(minutes_prompt.startswith("아래는 이 회의 이해를 돕기 위한 배경 메모입니다."))
        self.assertIn("원문에 없는 결정이나 액션을 새로 만들지는 마세요", extraction_prompt)
        self.assertIn("원문에 없는 결정이나 액션을 새로 만들지는 마세요", minutes_prompt)
        self.assertIn(context, extraction_prompt)
        self.assertIn(context, minutes_prompt)

    def test_glossary_prompt_prefix_is_hint_only(self) -> None:
        """용어집 프롬프트는 근거 없는 사실 생성을 금지하는 참고 힌트입니다."""
        prompt = summarize.build_glossary_prompt_prefix(["Tableau", "BigQuery"])

        self.assertIn("표기와 용어 해석을 돕기 위한 참고 자료", prompt)
        self.assertIn("결정, 액션, 참석자, 사실, 약속으로 추가하지 마세요", prompt)
        self.assertIn("원문 근거가 있는 표현", prompt)
        self.assertIn("- Tableau", prompt)
        self.assertIn("- BigQuery", prompt)
        self.assertEqual(summarize.build_glossary_prompt_prefix([]), "")
        self.assertEqual(summarize.build_glossary_prompt_prefix(None), "")

    def test_glossary_is_inserted_into_extraction_prompt_after_policy(self) -> None:
        """구조 추출 프롬프트는 회의 유형 정책 뒤 원칙 앞에 용어집을 넣습니다."""
        prompt = summarize.build_extraction_prompt(
            "회의 내용",
            "2026-05-14",
            meeting_type="technical_review",
            glossary_terms=["Tableau", "BigQuery"],
        )

        self.assertIn("- Tableau", prompt)
        self.assertIn("- BigQuery", prompt)
        self.assertLess(prompt.index("회의 유형: technical_review"), prompt.index("아래 용어집"))
        self.assertLess(prompt.index("아래 용어집"), prompt.index("원칙:"))

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

    def test_empty_glossary_adds_no_prompt_block(self) -> None:
        """빈 용어집은 구조 추출과 회의록 생성 프롬프트에 블록을 추가하지 않습니다."""
        extraction_prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14", glossary_terms=[])
        minutes_prompt = summarize.build_minutes_prompt("회의 내용", empty_track_b_structure(), glossary_terms=[])

        self.assertNotIn("아래 용어집", extraction_prompt)
        self.assertNotIn("아래 용어집", minutes_prompt)

    def test_summary_glossary_normalizes_dedupes_and_truncates(self) -> None:
        """요약 용어집은 대소문자 무시 중복 제거와 결정적 truncation을 수행합니다."""
        terms = [
            "  BigQuery  ",
            "bigquery",
            "Graph   RAG",
            "",
            "x" * (summarize.MAX_GLOSSARY_TERM_LENGTH + 1),
            "Tableau",
        ]

        self.assertEqual(summarize.normalize_glossary_terms(terms), ["BigQuery", "Graph RAG", "Tableau"])
        self.assertEqual(summarize.truncate_glossary_terms(terms, max_chars=22, max_terms=10), ["BigQuery"])
        self.assertEqual(summarize.truncate_glossary_terms(terms, max_chars=1200, max_terms=2), ["BigQuery", "Graph RAG"])

    def test_load_summary_glossary_supports_yaml_terms_and_missing_file(self) -> None:
        """요약 용어집 로더는 terms YAML과 missing file fallback을 지원합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            glossary_path = Path(temp_dir) / "summary_glossary.yaml"
            glossary_path.write_text(
                """
terms:
  - BigQuery
  - bigquery
  - Graph RAG
""".strip(),
                encoding="utf-8",
            )

            self.assertEqual(summarize.load_summary_glossary(glossary_path), ["BigQuery", "Graph RAG"])
            self.assertEqual(summarize.load_summary_glossary(Path(temp_dir) / "missing.yaml"), [])

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

    def test_meeting_structure_schema_matches_strict_json_schema_subset(self) -> None:
        """OpenAI strict Structured Output에 넘길 schema의 object 필수 조건을 확인합니다."""
        schema = summarize.MEETING_STRUCTURE_SCHEMA

        for object_schema in collect_schema_objects(schema):
            self.assertIs(object_schema.get("additionalProperties"), False)
            self.assertEqual(set(object_schema["required"]), set(object_schema["properties"]))
        self.assertFalse(schema_contains_key(schema, "default"))

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
Speaker 1: 오늘 회의는 네 가지 안건입니다.
Speaker 2: 배포 확인은 제가 진행하겠습니다.
""".strip()
        )

        self.assertEqual(summarize.find_quote_in_utterances("배포 확인은 제가 진행하겠습니다.", normalized), ["u_0002"])

    def test_find_quote_in_utterances_matches_whitespace_normalized_quote(self) -> None:
        """공백 차이가 있어도 source_quote가 포함된 발화를 찾습니다."""
        normalized = summarize.normalize_transcript("Speaker 1: 배포 확인은 제가 진행하겠습니다.")

        self.assertEqual(summarize.find_quote_in_utterances("배포   확인은 제가 진행하겠습니다.", normalized), ["u_0001"])

    def test_find_quote_in_utterances_strips_utterance_and_speaker_prefix(self) -> None:
        """quote에 발화 ID와 speaker prefix가 섞여도 실제 발화 텍스트로 매칭합니다."""
        normalized = summarize.normalize_transcript("영업담당자: 제가 고객 공유를 진행하겠습니다.")

        self.assertEqual(
            summarize.find_quote_in_utterances("[u_0001] 영업담당자: 제가 고객 공유를 진행하겠습니다.", normalized),
            ["u_0001"],
        )

    def test_find_quote_in_utterances_returns_empty_list_when_missing(self) -> None:
        """source_quote가 어떤 발화에도 없으면 빈 목록을 반환합니다."""
        normalized = summarize.normalize_transcript("Speaker 1: 배포 확인은 제가 진행하겠습니다.")

        self.assertEqual(summarize.find_quote_in_utterances("원문에 없는 문장입니다.", normalized), [])

    def test_validate_structure_can_use_normalized_transcript_for_source_quote(self) -> None:
        """선택적으로 받은 normalized transcript에서 quote를 찾으면 원문 근거 warning을 만들지 않습니다."""
        normalized = summarize.normalize_transcript("Speaker 2: 배포 확인은 제가 진행하겠습니다.")
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "Speaker 2",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "[u_0001] Speaker 2: 배포 확인은 제가 진행하겠습니다.",
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
Speaker 1: 배포 확인은 제가 진행하겠습니다.
Speaker 2: 자료 정리는 제가 진행하겠습니다.
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
                    "owner": "Speaker 1",
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

    def test_validate_structure_keeps_speaker_label_owner_without_owner_warning(self) -> None:
        """speaker label owner는 담당자 미정으로 보지 않습니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "배포 확인",
                    "owner": "Speaker 2",
                    "due_date": "2026-05-20",
                    "confidence": "high",
                    "source_quote": "제가 배포 확인을 2026-05-20까지 하겠습니다.",
                },
                {
                    "task": "자료 정리",
                    "owner": "Unknown",
                    "due_date": "2026-05-21",
                    "confidence": "high",
                    "source_quote": "제가 자료 정리를 2026-05-21까지 하겠습니다.",
                },
                {
                    "task": "고객 공유",
                    "owner": "영업담당자",
                    "due_date": "2026-05-22",
                    "confidence": "high",
                    "source_quote": "제가 고객 공유를 2026-05-22까지 하겠습니다.",
                },
            ],
            "speaker_highlights": [],
            "warnings": [],
        }
        transcript = "\n".join(
            [
                "[u_0001] Speaker 2: 제가 배포 확인을 2026-05-20까지 하겠습니다.",
                "[u_0002] Unknown: 제가 자료 정리를 2026-05-21까지 하겠습니다.",
                "[u_0003] 영업담당자: 제가 고객 공유를 2026-05-22까지 하겠습니다.",
            ]
        )

        result = summarize.validate_structure(structure, transcript)

        self.assertEqual([item["owner"] for item in result["action_items"]], ["Speaker 2", "Unknown", "영업담당자"])
        self.assertFalse(any("담당자 확인 필요" in warning for warning in result["warnings"]))
        self.assertFalse(any("담당자 확인이 필요한 액션 아이템" in warning for warning in result["warnings"]))

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

    def test_validate_structure_removes_stale_owner_warning_for_resolved_speaker_owner(self) -> None:
        """resolved speaker owner를 가리키는 오래된 담당자 warning은 제거합니다."""
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
                    "owner": "Speaker 2",
                    "due_date": "미정",
                    "confidence": "high",
                    "source_quote": "배포 확인은 제가 하겠습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": ["배포 확인: 담당자 확인 필요"],
        }

        result = summarize.validate_structure(structure, "Speaker 2: 배포 확인은 제가 하겠습니다.")

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

        result = summarize.validate_structure(structure, "Speaker 2: 배포 확인은 저희가 하겠습니다.")

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

    def test_render_output_formats_raw_internal_warnings(self) -> None:
        """Markdown 확인 필요 섹션도 내부 필드명을 노출하지 않습니다."""
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

        self.assertIn("- 담당자 확인이 필요한 액션 아이템이 있습니다.", output)
        self.assertIn("- 기한 확인이 필요한 액션 아이템이 있습니다.", output)
        self.assertIn("- 내용 확인이 필요한 항목이 있습니다.", output)
        self.assertIn("- 원문 근거 확인이 필요한 항목이 있습니다.", output)
        self.assertFalse(any(internal_name in output for internal_name in ("owner", "due_date", "confidence", "source_quote")))

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
        self.assertIn("액션 아이템 담당자는 검증 JSON의 owner를 따르고", prompt)
        self.assertIn("1인칭 표현(저, 제가) 자체를 담당자명으로 쓰지 마세요", prompt)
        self.assertIn("회의록 작성 초점", prompt)
        self.assertIn("JSON 내용을 그대로 나열하지 말고", prompt)
        self.assertIn("회의 요약", prompt)
        self.assertIn("주요 결정사항", prompt)
        self.assertIn("액션 아이템", prompt)
        self.assertIn("주요 발언 요약", prompt)

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

    def test_render_output_softens_non_execution_warnings(self) -> None:
        """비운영 회의의 owner/due warning은 렌더링에서 부드럽게 표시합니다."""
        structure = {
            "summary_facts": ["요구사항을 검토했습니다."],
            "decisions": [],
            "action_items": [],
            "speaker_highlights": [],
            "warnings": ["요구사항 후속 논의: 담당자 및 기한 확인 필요"],
        }

        output = summarize.render_output(structure, "## 회의 요약\n고객 논의", meeting_type="customer_meeting")

        self.assertIn("## 검토 메모", output)
        self.assertIn("요구사항 후속 논의: 추가 확인이 필요할 수 있습니다", output)
        self.assertNotIn("담당자 및 기한 확인 필요", output)

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
