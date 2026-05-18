"""합성 transcript fixture 기반 Python-only 회귀 테스트입니다."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "transcripts"
FIXTURE_NAMES = (
    "ambiguous_owner_due_date_meeting.txt",
    "decision_action_overlap_meeting.txt",
    "long_action_heavy_meeting.txt",
    "medium_project_meeting.txt",
    "no_action_items_meeting.txt",
    "short_clear_meeting.txt",
)
EXPECTED_SPEAKER_COUNTS = {
    "ambiguous_owner_due_date_meeting.txt": 4,
    "decision_action_overlap_meeting.txt": 4,
    "long_action_heavy_meeting.txt": 6,
    "medium_project_meeting.txt": 5,
    "no_action_items_meeting.txt": 3,
    "short_clear_meeting.txt": 3,
}


def load_fixture_transcript(filename: str) -> str:
    """tests/fixtures/transcripts 아래의 fixture transcript를 읽습니다."""
    return (FIXTURE_DIR / filename).read_text(encoding="utf-8")


def normalize_fixture(filename: str):
    """fixture transcript를 정규화합니다."""
    from summarization.normalization import normalize_transcript

    return normalize_transcript(load_fixture_transcript(filename))


def analyze_fixture(filename: str):
    """fixture transcript의 profile을 계산합니다."""
    from summarization.profiling import analyze_transcript_profile

    return analyze_transcript_profile(normalize_fixture(filename))


def find_fixture_utterance(normalized, text: str):
    """fixture 발화 중 특정 문장을 포함한 첫 발화를 반환합니다."""
    for utterance in normalized.utterances:
        if text in utterance.text:
            return utterance
    raise AssertionError(f"fixture utterance not found: {text}")


class TranscriptFixtureTests(unittest.TestCase):
    """fixture 기반 normalization, profiling, warning cleanup을 확인합니다."""

    def test_fixture_strategy_profiles_match_expectations(self) -> None:
        """대표 fixture의 strategy와 cue 밀도가 기대 범위에 들어옵니다."""
        from summarization.profiling import choose_processing_strategy

        short_profile = analyze_fixture("short_clear_meeting.txt")
        long_profile = analyze_fixture("long_action_heavy_meeting.txt")
        no_action_profile = analyze_fixture("no_action_items_meeting.txt")
        ambiguous_profile = analyze_fixture("ambiguous_owner_due_date_meeting.txt")

        self.assertEqual(choose_processing_strategy(short_profile), "direct")
        self.assertEqual(choose_processing_strategy(long_profile), "chunk")
        self.assertLessEqual(no_action_profile.action_cue_count, 12)
        self.assertEqual(choose_processing_strategy(no_action_profile), "direct")
        self.assertGreaterEqual(ambiguous_profile.action_cue_count, 30)
        self.assertGreaterEqual(ambiguous_profile.risk_cue_count, 5)
        ambiguous_text = load_fixture_transcript("ambiguous_owner_due_date_meeting.txt")
        self.assertIn("제가 한번 볼게요", ambiguous_text)
        self.assertIn("다음에", ambiguous_text)
        self.assertIn("이번 주 안에는", ambiguous_text)

    def test_all_fixtures_normalize_to_stable_utterances_and_expected_speaker_counts(self) -> None:
        """모든 fixture가 안정적인 utterance_id와 README 기준 speaker 수를 가집니다."""
        for fixture_name in FIXTURE_NAMES:
            with self.subTest(fixture=fixture_name):
                normalized = normalize_fixture(fixture_name)
                profile = analyze_fixture(fixture_name)

                self.assertGreater(len(normalized.utterances), 0)
                self.assertEqual(normalized.utterances[0].utterance_id, "u_0001")
                self.assertEqual(
                    [utterance.utterance_id for utterance in normalized.utterances],
                    [f"u_{index + 1:04d}" for index in range(len(normalized.utterances))],
                )
                self.assertEqual(profile.speaker_count, EXPECTED_SPEAKER_COUNTS[fixture_name])

    def test_raw_internal_warnings_are_formatted_for_public_display(self) -> None:
        """public warning에는 내부 필드명이 남지 않고 표준 문장으로 변환됩니다."""
        from summarization.validation import format_display_warnings

        warnings = format_display_warnings(
            [
                "owner가 없음",
                "due_date가 '미정'인 항목이 있음",
                "confidence가 'low'인 항목이 있음",
                "source_quote가 없음",
            ]
        )

        self.assertEqual(
            warnings,
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
                for warning in warnings
                for internal_name in ("owner", "due_date", "confidence", "source_quote")
            )
        )

    def test_ambiguous_fixture_preserves_speakers_and_utterance_ids_for_llm(self) -> None:
        """speaker-labeled fixture의 발화 ID와 화자 라벨이 LLM 렌더링에 보존됩니다."""
        normalized = normalize_fixture("ambiguous_owner_due_date_meeting.txt")
        target_text = "큐 지연 쪽을 확인해보겠습니다."
        target_utterance = find_fixture_utterance(normalized, target_text)
        rendered = normalized.render_for_llm()

        self.assertGreater(len(normalized.utterances), 0)
        self.assertEqual(normalized.utterances[0].utterance_id, "u_0001")
        self.assertEqual(normalized.utterances[0].speaker, "김하준")
        self.assertEqual(target_utterance.speaker, "이서연")
        self.assertIn(f"[{normalized.utterances[0].utterance_id}] 김하준:", rendered)
        self.assertIn(f"[{target_utterance.utterance_id}] 이서연:", rendered)
        self.assertIn(target_text, rendered)

    def test_ambiguous_fixture_validation_backfills_source_utterance_ids(self) -> None:
        """fixture source_quote가 발화에서 매칭되면 빈 source_utterance_ids를 내부 보완합니다."""
        from summarization.validation import validate_structure

        transcript = load_fixture_transcript("ambiguous_owner_due_date_meeting.txt")
        normalized = normalize_fixture("ambiguous_owner_due_date_meeting.txt")
        quote = "큐 지연 쪽을 확인해보겠습니다."
        target_utterance = find_fixture_utterance(normalized, quote)
        structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [
                {
                    "task": "큐 지연 확인",
                    "owner": "이서연",
                    "due_date": "금요일 오후",
                    "confidence": "high",
                    "source_quote": quote,
                    "source_utterance_ids": [],
                }
            ],
            "speaker_highlights": [],
            "warnings": [],
        }

        result = validate_structure(structure, transcript, normalized)

        self.assertEqual(result["action_items"][0]["source_utterance_ids"], [target_utterance.utterance_id])
        self.assertFalse(any("원문 근거 확인" in warning for warning in result["warnings"]))

    def test_ambiguous_fixture_speaker_owner_does_not_create_owner_warning(self) -> None:
        """fixture의 실제 speaker label owner는 담당자 확인 warning으로 처리하지 않습니다."""
        from summarization.validation import validate_structure

        transcript = load_fixture_transcript("ambiguous_owner_due_date_meeting.txt")
        normalized = normalize_fixture("ambiguous_owner_due_date_meeting.txt")
        base_action = {
            "task": "큐 지연 확인",
            "due_date": "금요일 오후",
            "confidence": "high",
            "source_quote": "큐 지연 쪽을 확인해보겠습니다.",
        }
        speaker_owner_structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [{**base_action, "owner": "이서연"}],
            "speaker_highlights": [],
            "warnings": [],
        }
        unknown_owner_structure = {
            "summary_facts": [],
            "decisions": [],
            "action_items": [{**base_action, "owner": "미정"}],
            "speaker_highlights": [],
            "warnings": [],
        }

        speaker_owner_result = validate_structure(speaker_owner_structure, transcript, normalized)
        unknown_owner_result = validate_structure(unknown_owner_structure, transcript, normalized)

        self.assertFalse(any("담당자 확인" in warning for warning in speaker_owner_result["warnings"]))
        self.assertIn("큐 지연 확인: 담당자 확인 필요", unknown_owner_result["warnings"])

    def test_ambiguous_fixture_public_result_hides_internal_grounding_fields(self) -> None:
        """public result에는 source_quote와 source_utterance_ids를 노출하지 않습니다."""
        from summarization.rendering import build_summary_result
        from summarization.validation import validate_structure

        transcript = load_fixture_transcript("ambiguous_owner_due_date_meeting.txt")
        normalized = normalize_fixture("ambiguous_owner_due_date_meeting.txt")
        structure = {
            "summary_facts": ["알림 실패 원인을 운영 로그 기준으로 분석하기로 했습니다."],
            "decisions": [
                {
                    "decision": "최종 실패 기준으로 리포트한다",
                    "status": "확정",
                    "source_quote": "최종 실패 기준으로 결정하겠습니다.",
                }
            ],
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
            "warnings": [],
        }

        validated = validate_structure(structure, transcript, normalized)
        public_result = build_summary_result(validated, "최종 회의록")

        self.assertNotIn("source_quote", public_result["action_items"][0])
        self.assertNotIn("source_utterance_ids", public_result["action_items"][0])
        self.assertNotIn("source_quote", public_result["decisions"][0])
        self.assertNotIn("source_utterance_ids", public_result["decisions"][0])

    def test_long_action_heavy_fixture_merges_repeated_actions_and_filters_decision_only_action(self) -> None:
        """긴 action-heavy fixture에서 중복 action과 decision-only 오분류를 보수적으로 정리합니다."""
        from summarization.merge import merge_structures
        from summarization.validation import validate_structure

        transcript = load_fixture_transcript("long_action_heavy_meeting.txt")
        normalized = normalize_fixture("long_action_heavy_meeting.txt")
        merged = merge_structures(
            [
                {
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
                            "task": "이티엘 재시도 설정",
                            "owner": "박민재",
                            "due_date": "금요일 오후",
                            "confidence": "low",
                            "source_quote": "제가 배치 설정에 재시도 2회를 반영하겠습니다.",
                        },
                        {
                            "task": "API 캐싱 제외",
                            "owner": "미정",
                            "due_date": "미정",
                            "confidence": "low",
                            "source_quote": "이번 PoC에서는 API 응답 캐싱을 적용하지 않기로 결정합니다.",
                        },
                    ],
                    "speaker_highlights": [],
                    "warnings": ["박민재: 담당자 확인 필요"],
                },
                {
                    "summary_facts": [],
                    "decisions": [],
                    "action_items": [
                        {
                            "task": "재시도 2회 설정",
                            "owner": "박민재",
                            "due_date": "2026-05-22",
                            "confidence": "high",
                            "source_quote": "박민재님 재시도 2회 설정은 금요일 오후 6시까지입니다.",
                        }
                    ],
                    "speaker_highlights": [],
                    "warnings": [],
                },
            ]
        )

        result = validate_structure(merged, transcript, normalized)

        self.assertEqual(len(result["action_items"]), 1)
        self.assertEqual(result["action_items"][0]["owner"], "박민재")
        self.assertEqual(result["action_items"][0]["due_date"], "금요일 오후 6시")
        self.assertIn(result["action_items"][0]["source_utterance_ids"][0], [utterance.utterance_id for utterance in normalized.utterances])
        self.assertFalse(any("API 캐싱 제외" in item["task"] for item in result["action_items"]))
        self.assertFalse(any("담당자 확인" in warning for warning in result["warnings"]))
        self.assertFalse(any("원문 근거 확인" in warning for warning in result["warnings"]))

    def test_decision_action_overlap_fixture_warnings_are_deduplicated_and_formatted(self) -> None:
        """decision/action overlap 구조의 warning이 중복 없이 표준 문장으로 정리됩니다."""
        from summarization.validation import validate_structure

        transcript = load_fixture_transcript("decision_action_overlap_meeting.txt")
        structure = {
            "summary_facts": [],
            "decisions": [
                {
                    "decision": "발표자료를 6월 10일까지 준비하기로 했다",
                    "status": "확정",
                    "source_quote": "발표자료를 6월 10일까지 준비하기로 하겠습니다.",
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
                    "source_quote": "발표자료를 6월 10일까지 준비하기로 하겠습니다.",
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

        result = validate_structure(structure, transcript)

        self.assertIn("발표자료를 6월 10일까지 준비하기: 담당자 확인 필요", result["warnings"])
        self.assertIn("데이터 정제 작업을 이번 주 안으로 완료하기: 담당자 및 기한 확인 필요", result["warnings"])
        self.assertEqual(result["warnings"].count("발표자료를 6월 10일까지 준비하기: 담당자 확인 필요"), 1)
        self.assertEqual(result["warnings"].count("데이터 정제 작업을 이번 주 안으로 완료하기: 담당자 및 기한 확인 필요"), 1)
        self.assertFalse(any("확정되었지만" in warning for warning in result["warnings"]))
        self.assertFalse(
            any(
                internal_name in warning
                for warning in result["warnings"]
                for internal_name in ("owner", "due_date", "confidence", "source_quote")
            )
        )


if __name__ == "__main__":
    unittest.main()
