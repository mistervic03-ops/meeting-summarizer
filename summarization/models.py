"""회의 요약 엔진에서 공유하는 데이터 모델입니다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, NamedTuple, TypedDict


ProcessingStrategy = Literal["direct", "chunk", "deep"]
DIRECT_STRATEGY: ProcessingStrategy = "direct"
CHUNK_STRATEGY: ProcessingStrategy = "chunk"
DEEP_STRATEGY: ProcessingStrategy = "deep"


@dataclass(frozen=True)
class Utterance:
    """화자 정보가 있을 수 있는 파싱된 transcript 발화입니다."""

    speaker: str | None
    text: str


@dataclass(frozen=True)
class TranscriptUtterance:
    """안정적인 원문 메타데이터를 가진 정규화된 transcript 발화입니다."""

    utterance_id: str
    speaker: str | None
    text: str
    index: int
    raw_line: str
    start_ms: int | None = None
    end_ms: int | None = None

    def render_for_llm(self) -> str:
        """LLM 입력에서 발화 ID와 화자 정보를 보존한 한 줄 문자열을 반환합니다."""
        speaker_label = self.speaker or "Unknown"
        return f"[{self.utterance_id}] {speaker_label}: {self.text}"


@dataclass(frozen=True)
class PreprocessedTranscript:
    """파이썬 전처리 후 전사문 텍스트와 감지된 회의 날짜입니다."""

    text: str
    meeting_date: str


@dataclass(frozen=True)
class NormalizedTranscript:
    """향후 분할 처리와 원문 추적을 위해 정규화한 전사문입니다."""

    utterances: list[TranscriptUtterance]
    text: str
    meeting_date: str

    def render_for_llm(self) -> str:
        """LLM 입력에서 발화 ID와 화자 정보를 보존한 transcript 문자열을 반환합니다."""
        return "\n".join(utterance.render_for_llm() for utterance in self.utterances).strip()


@dataclass(frozen=True)
class TranscriptChunk:
    """긴 전사문을 발화 단위로 나눈 내부 처리용 chunk입니다."""

    chunk_id: str
    utterances: list[TranscriptUtterance]
    start_utterance_id: str
    end_utterance_id: str
    text: str
    overlap_before_ids: list[str]
    overlap_after_ids: list[str]


@dataclass(frozen=True)
class TranscriptProfile:
    """향후 전략 선택에 사용할 파이썬 전용 전사문 복잡도 프로필입니다."""

    char_count: int
    utterance_count: int
    speaker_count: int
    action_cue_count: int
    decision_cue_count: int
    risk_cue_count: int
    requirement_cue_count: int
    estimated_complexity: str


class MeetingStructure(NamedTuple):
    """렌더링과 회의록 생성에 사용하는 정규화된 구조화 사실입니다."""

    summary_facts: list[str]
    decisions: list[dict[str, Any]]
    action_items: list[dict[str, Any]]
    speaker_highlights: list[str]
    warnings: list[str]


class SummaryResult(TypedDict):
    """외부 호출자에게 반환하는 구조화된 회의 요약입니다."""

    minutes: str
    action_items: list[dict[str, Any]]
    summary_facts: list[str]
    decisions: list[dict[str, Any]]
    speaker_highlights: list[str]
    warnings: list[str]
