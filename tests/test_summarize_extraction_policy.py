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

class SummarizeExtractionPolicyTests(unittest.TestCase):
    """기존 summarize.py 테스트를 도메인별로 분리한 테스트입니다."""

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
        self.assertIn("summary_facts는 SummaryTab의 빠른 개요에 쓰는 3~6개의 상위 수준 bullet", prompt)
        self.assertIn("summary_facts에는 회의 전체를 이해하는 데 필요한 핵심 맥락과 결과", prompt)
        self.assertIn("언급된 모든 사실, 예시, 수치, 질문, 고객 관심사, 기술 세부사항, 운영 조건", prompt)
        self.assertIn("summary_facts를 늘리지 말고 speaker_highlights에 남기세요", prompt)
        self.assertIn("삭제하지 말고 speaker_highlights나 전체 회의록 맥락에서 보존", prompt)
        self.assertIn("사람이 검토하고 판단하기 쉽게 논의 구조를 정리", prompt)
        self.assertIn("decisions에는 명확한 결정", prompt)
        self.assertIn("확정된 결정과 논의된 방향성을 구분", prompt)
        self.assertIn("명시적 합의, 승인, 결정 표현이 있는 확정 결정", prompt)
        self.assertIn("결정 후보로 명확히 다룬 미확정 decision candidate", prompt)
        self.assertIn("기술 방향, 제품 설명, 협력 가능성, 고객 관심사, 기술적 가능성", prompt)
        self.assertIn("decisions에 넣지 말고 summary_facts나 speaker_highlights", prompt)
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
        self.assertIn("action_items는 명시적 요청, 실행 약속, 담당 지정, 기한, 구체적인 다음 단계 합의", prompt)
        self.assertIn("약한 관심 표현, 탐색적 후속 논의, 제품 사용 사례, 아키텍처 논의", prompt)
        self.assertIn("action_item으로 단정하지 말고 논의 포인트나 follow-up 후보로 speaker_highlights", prompt)
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
        self.assertIn("발화 텍스트 안에 명시된 사람/팀 이름만 owner로 사용", prompt)
        self.assertIn("이름 근거가 없으면 owner는 \"미정\"", prompt)
        self.assertIn("owner가 실제로 \"미정\"일 때만 담당자 확인 warning", prompt)
        self.assertIn("confidence가 low인 항목은 warnings에 추가", prompt)
        self.assertIn("due_date는 \"미정\"으로 두고 warnings에 추가", prompt)
        self.assertIn("owner에 \"저\", \"제가\", \"저희\" 같은 1인칭 표현 자체를 쓰지 마세요", prompt)
        self.assertIn("owner와 due_date가 둘 다 명확할 때만 \"high\"", prompt)
        self.assertNotIn("영업담당자: 제가 하고 있는데요", prompt)
        self.assertNotIn("\"Speaker 1\", \"Speaker 2\" 같은 speaker label", prompt)
        self.assertIn("주요 발언/논의 포인트", prompt)
        self.assertIn("speaker_highlights에는 주요 발언 또는 논의 포인트", prompt)
        self.assertIn("summary_facts에 넣기에는 세부적인 기술 설명, 고객 관심사, 열린 질문, 리스크, 예시, 수치, follow-up 후보", prompt)
        self.assertIn("speaker_highlights는 화자별 발언이 아니라 주요 논의/source highlight", prompt)
        self.assertIn("transcript에 없는 화자나 참석자 이름을 만들지 말고", prompt)
        self.assertIn("speaker_highlights만으로 새로운 사실, 결정, action_item을 만들지 마세요", prompt)

    def test_build_extraction_prompt_includes_meeting_type_policy(self) -> None:
        """회의 유형별 정책이 구조 추출 프롬프트에 삽입됩니다."""
        technical_prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14", meeting_type="technical_review")
        execution_prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14", meeting_type="execution")
        customer_prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14", meeting_type="customer_meeting")
        brainstorming_prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14", meeting_type="brainstorming")
        general_prompt = summarize.build_extraction_prompt("회의 내용", "2026-05-14", meeting_type="general")

        self.assertIn("회의 유형: technical_review", technical_prompt)
        self.assertIn("제약 조건, 설계 tradeoff, 리스크", technical_prompt)
        self.assertIn('"가능해 보인다", "검토 대상", "대안으로 언급", "고려해볼 수 있다"', technical_prompt)
        self.assertIn("회의 유형: execution", execution_prompt)
        self.assertIn("진행 상황, 담당자, 일정, 후속 작업을 원문 근거", execution_prompt)
        self.assertIn("회의 유형: customer_meeting", customer_prompt)
        self.assertIn("고객 요구, 우려사항, 요구사항, 리스크", customer_prompt)
        self.assertIn("고객 요구사항, 이의제기, 열린 질문, 검증 포인트", customer_prompt)
        self.assertIn("회의 유형: brainstorming", brainstorming_prompt)
        self.assertIn("아이디어, 선택지, 질문, 우려사항", brainstorming_prompt)
        self.assertIn("명시적 수렴, 선택, 채택 표현", brainstorming_prompt)
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
        self.assertIn("논의 메모: 도입 가능성 검토", result.structure["summary_facts"])
        self.assertNotIn("논의 메모: 도입 가능성을 검토해볼 수 있습니다.", result.structure["summary_facts"])
        self.assertTrue(any("실행 약속이 불명확" in warning for warning in result.structure["warnings"]))

    def test_apply_extraction_policy_preserves_execution_actions_aggressively(self) -> None:
        """실행 회의는 근거가 갖춰진 운영 후속 작업 후보를 약화시키지 않습니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "도입 가능성 검토",
                    "owner": "데이터팀",
                    "due_date": "내일 오전",
                    "confidence": "low",
                    "source_quote": "도입 가능성은 데이터팀이 내일 오전까지 검토해볼 수 있습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.apply_extraction_policy(structure, "execution")

        self.assertEqual(result.downgraded_action_count, 0)
        self.assertEqual(result.structure["action_items"], structure["action_items"])
        self.assertEqual(result.structure["summary_facts"], [])

    def test_execution_policy_downgrades_low_confidence_action_without_owner_due_date_or_strong_signal(self) -> None:
        """실행 회의도 근거가 약한 저신뢰 action 후보는 논의 메모로 낮춥니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "상태 업데이트 검토",
                    "owner": "미정",
                    "due_date": "미정",
                    "confidence": "low",
                    "source_quote": "현재 상태는 조금 더 봐야 할 것 같습니다.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.apply_extraction_policy(structure, "execution")

        self.assertEqual(result.downgraded_action_count, 1)
        self.assertEqual(result.structure["action_items"], [])
        self.assertIn("논의 메모: 상태 업데이트 검토", result.structure["summary_facts"])
        self.assertTrue(any("실행 약속이 불명확" in warning for warning in result.structure["warnings"]))

    def test_execution_policy_keeps_low_confidence_action_with_strong_signal(self) -> None:
        """실행 회의는 강한 실행 신호가 있으면 high-recall 동작을 유지합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "상태 업데이트 공유",
                    "owner": "미정",
                    "due_date": "미정",
                    "confidence": "low",
                    "source_quote": "상태 업데이트는 공유해주세요.",
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = summarize.apply_extraction_policy(structure, "execution")

        self.assertEqual(result.downgraded_action_count, 0)
        self.assertEqual(result.structure["action_items"], structure["action_items"])

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
        self.assertIn("논의 메모: 아키텍처 구조 검토", result.structure["summary_facts"])

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
        self.assertIn("논의 메모: 요구사항 후속 논의", result.structure["summary_facts"])

    def test_downgraded_action_note_falls_back_to_source_quote_without_task(self) -> None:
        """task가 비어 있으면 낮춘 action 후보는 source_quote를 fallback으로 사용합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "",
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
        self.assertIn("논의 메모: 신규 구조 적용 가능성이 언급되었다", result.structure["summary_facts"])
        self.assertNotIn("논의 메모: 신규 구조 적용 가능성이 언급되었습니다.", result.structure["summary_facts"])
        self.assertTrue(any("확정 근거가 약" in warning for warning in result.structure["warnings"]))

    def test_downgraded_decision_note_falls_back_to_source_quote_without_decision(self) -> None:
        """decision이 비어 있으면 낮춘 결정 후보는 source_quote를 fallback으로 사용합니다."""
        structure = {
            "summary_facts": [],
            "decisions": [
                {
                    "decision": "",
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
        self.assertIn("논의 메모: 신규 구조 적용 가능성이 언급되었습니다.", result.structure["summary_facts"])

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

    def test_meeting_structure_schema_matches_strict_json_schema_subset(self) -> None:
        """OpenAI strict Structured Output에 넘길 schema의 object 필수 조건을 확인합니다."""
        schema = summarize.MEETING_STRUCTURE_SCHEMA

        for object_schema in collect_schema_objects(schema):
            self.assertIs(object_schema.get("additionalProperties"), False)
            self.assertEqual(set(object_schema["required"]), set(object_schema["properties"]))
        self.assertFalse(schema_contains_key(schema, "default"))


if __name__ == "__main__":
    unittest.main()
