"""전사문 프로필 분석과 향후 처리 전략 선택을 담당하는 파이썬 전용 모듈입니다."""

from __future__ import annotations

import logging

from summarization.models import (
    CHUNK_STRATEGY,
    DEEP_STRATEGY,
    DIRECT_STRATEGY,
    NormalizedTranscript,
    ProcessingStrategy,
    TranscriptProfile,
)


logger = logging.getLogger("summarize")

ACTION_CUES = ("해 주세요", "해주세요", "하겠습니다", "담당", "공유", "정리", "확인", "완료", "까지")
DECISION_CUES = ("확정", "하기로", "결정", "이걸로", "진행하지 않")
RISK_CUES = ("리스크", "이슈", "지연", "막힘", "안 됩니다", "어렵")
REQUIREMENT_CUES = ("필요", "요구", "조건", "must", "requirement")


def analyze_transcript_profile(normalized: NormalizedTranscript) -> TranscriptProfile:
    """외부 모델 호출 없이 전사문 크기와 cue 밀도를 분석합니다."""
    action_cue_count = sum(count_cues_in_text(utterance.text, ACTION_CUES) for utterance in normalized.utterances)
    decision_cue_count = sum(count_cues_in_text(utterance.text, DECISION_CUES) for utterance in normalized.utterances)
    risk_cue_count = sum(count_cues_in_text(utterance.text, RISK_CUES) for utterance in normalized.utterances)
    requirement_cue_count = sum(
        count_cues_in_text(utterance.text, REQUIREMENT_CUES) for utterance in normalized.utterances
    )
    cue_count = action_cue_count + decision_cue_count + risk_cue_count + requirement_cue_count
    complexity = estimate_transcript_complexity(
        char_count=len(normalized.text),
        utterance_count=len(normalized.utterances),
        cue_count=cue_count,
    )

    return TranscriptProfile(
        char_count=len(normalized.text),
        utterance_count=len(normalized.utterances),
        action_cue_count=action_cue_count,
        decision_cue_count=decision_cue_count,
        risk_cue_count=risk_cue_count,
        requirement_cue_count=requirement_cue_count,
        estimated_complexity=complexity,
    )


def count_cues_in_text(text: str, cues: tuple[str, ...]) -> int:
    """한 발화 안에서 보수적인 cue 문구 등장 횟수를 셉니다."""
    lowered_text = text.lower()
    return sum(lowered_text.count(cue.lower()) for cue in cues)


def estimate_transcript_complexity(
    char_count: int,
    utterance_count: int,
    cue_count: int,
) -> str:
    """의도적으로 단순한 기준으로 전사문 복잡도를 추정합니다."""
    if char_count >= 20000 or utterance_count >= 160 or cue_count >= 90:
        return "complex"
    if char_count >= 7000 or utterance_count >= 60 or cue_count >= 25:
        return "standard"
    return "simple"


def choose_processing_strategy(profile: TranscriptProfile) -> ProcessingStrategy:
    """Direct 모드를 기본값으로 유지하면서 향후 처리 전략을 고릅니다."""
    total_cue_count = (
        profile.action_cue_count
        + profile.decision_cue_count
        + profile.risk_cue_count
        + profile.requirement_cue_count
    )
    cue_density = total_cue_count / max(profile.char_count / 1000, 1)

    if profile.char_count >= 120000 or total_cue_count >= 120:
        return DEEP_STRATEGY
    if profile.char_count >= 60000 or total_cue_count >= 30:
        return CHUNK_STRATEGY
    return DIRECT_STRATEGY


def log_transcript_profile(profile: TranscriptProfile, selected_strategy: ProcessingStrategy) -> None:
    """실행 흐름을 바꾸지 않고 전사문 프로필과 선택된 향후 전략을 로그로 남깁니다."""
    logger.info(
        "transcript_profile char_count=%s utterance_count=%s "
        "action_cue_count=%s decision_cue_count=%s risk_cue_count=%s "
        "requirement_cue_count=%s estimated_complexity=%s selected_strategy=%s",
        profile.char_count,
        profile.utterance_count,
        profile.action_cue_count,
        profile.decision_cue_count,
        profile.risk_cue_count,
        profile.requirement_cue_count,
        profile.estimated_complexity,
        selected_strategy,
    )
