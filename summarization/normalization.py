"""전사문 정규화와 전처리를 담당하는 파이썬 전용 모듈입니다."""

from __future__ import annotations

import re
from datetime import date

from summarization.models import NormalizedTranscript, PreprocessedTranscript, TranscriptUtterance


FILLER_TOKENS = {"아", "음", "네네", "어"}
MAX_SPEAKERLESS_UTTERANCE_CHARS = 500
SENTENCE_BOUNDARY_CHARS = ".?!。？！"
DATE_PATTERNS = (
    re.compile(r"(?P<year>20\d{2})\s*년\s*(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일"),
    re.compile(r"(?P<year>20\d{2})[-./](?P<month>\d{1,2})[-./](?P<day>\d{1,2})"),
)
KOREAN_MONTH_DAY_PATTERN = re.compile(r"(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일")


def preprocess_transcript(transcript: str) -> PreprocessedTranscript:
    """단독 추임새 제거와 회의 날짜 추출을 수행합니다."""
    normalized_transcript = normalize_transcript(transcript)
    return PreprocessedTranscript(normalized_transcript.text, normalized_transcript.meeting_date)


def normalize_transcript(transcript: str) -> NormalizedTranscript:
    """렌더링 텍스트를 바꾸지 않고 전사문을 안정적인 발화 목록으로 정규화합니다."""
    meeting_date = extract_meeting_date(transcript)
    parsed_utterances: list[tuple[str, str]] = []

    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parsed_utterances.extend(split_speakerless_line(line))

    cleaned_utterances: list[tuple[str, str]] = []

    for text, raw_line in parsed_utterances:
        normalized_text = re.sub(r"[,.!?。！？…~\s]+", "", text.strip())
        if normalized_text in FILLER_TOKENS:
            continue

        cleaned_utterances.append((text, raw_line))

    normalized_utterances = [
        TranscriptUtterance(
            utterance_id=f"u_{index + 1:04d}",
            text=text,
            index=index,
            raw_line=raw_line,
        )
        for index, (text, raw_line) in enumerate(cleaned_utterances)
    ]
    lines = [utterance.text for utterance in normalized_utterances]
    return NormalizedTranscript(normalized_utterances, "\n".join(lines).strip(), meeting_date)


def split_speakerless_line(line: str) -> list[tuple[str, str]]:
    """긴 speakerless plain STT 줄을 LLM 근거 추적에 적당한 창으로 나눕니다."""
    text = line.strip()
    if len(text) <= MAX_SPEAKERLESS_UTTERANCE_CHARS:
        return [(text, text)]

    utterances: list[tuple[str, str]] = []
    remaining = text
    while len(remaining) > MAX_SPEAKERLESS_UTTERANCE_CHARS:
        window = remaining[:MAX_SPEAKERLESS_UTTERANCE_CHARS]
        split_at = max(window.rfind(boundary) for boundary in SENTENCE_BOUNDARY_CHARS) + 1
        if split_at <= 0:
            split_at = MAX_SPEAKERLESS_UTTERANCE_CHARS

        chunk = remaining[:split_at].strip()
        if chunk:
            utterances.append((chunk, chunk))
        remaining = remaining[split_at:].strip()

    if remaining:
        utterances.append((remaining, remaining))
    return utterances


def extract_meeting_date(transcript: str) -> str:
    """전사문에서 회의 날짜를 추출하고, 없으면 오늘 날짜를 반환합니다."""
    for pattern in DATE_PATTERNS:
        match = pattern.search(transcript)
        if match:
            return build_iso_date(match.group("year"), match.group("month"), match.group("day"))

    match = KOREAN_MONTH_DAY_PATTERN.search(transcript)
    if match:
        return build_iso_date(str(date.today().year), match.group("month"), match.group("day"))

    return date.today().isoformat()


def build_iso_date(year: str, month: str, day: str) -> str:
    """숫자 날짜 조각으로 ISO 날짜 문자열을 만듭니다."""
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return date.today().isoformat()
