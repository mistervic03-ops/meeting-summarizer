"""전사문 정규화와 전처리를 담당하는 파이썬 전용 모듈입니다."""

from __future__ import annotations

import re
from datetime import date

from summarization.models import NormalizedTranscript, PreprocessedTranscript, TranscriptUtterance


FILLER_TOKENS = {"아", "음", "네네", "어"}
MAX_SPEAKERLESS_UTTERANCE_CHARS = 500
SENTENCE_BOUNDARY_CHARS = ".?!。？！"
PLAIN_HEADING_LABEL_KEYS = {
    "회의목적",
    "목적",
    "안건",
    "이슈",
    "결론",
    "참석자",
    "참여자",
    "todo",
    "api",
    "q",
    "a",
}

SPEAKER_LINE_PATTERN = re.compile(
    r"^\s*(?:\[(?P<bracket_speaker>[^\]]{1,40})\]|(?P<speaker>[^:：\n]{1,40}))\s*[:：]\s*(?P<text>.*)$"
)
DATE_PATTERNS = (
    re.compile(r"(?P<year>20\d{2})\s*년\s*(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일"),
    re.compile(r"(?P<year>20\d{2})[-./](?P<month>\d{1,2})[-./](?P<day>\d{1,2})"),
)
KOREAN_MONTH_DAY_PATTERN = re.compile(r"(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일")


def preprocess_transcript(transcript: str) -> PreprocessedTranscript:
    """단독 추임새 제거, 연속 화자 병합, 회의 날짜 추출을 수행합니다."""
    normalized_transcript = normalize_transcript(transcript)
    return PreprocessedTranscript(normalized_transcript.text, normalized_transcript.meeting_date)


def normalize_transcript(transcript: str) -> NormalizedTranscript:
    """렌더링 텍스트를 바꾸지 않고 전사문을 안정적인 발화 목록으로 정규화합니다."""
    meeting_date = extract_meeting_date(transcript)
    parsed_utterances: list[tuple[str | None, str, str]] = []

    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = SPEAKER_LINE_PATTERN.match(line)
        if match:
            speaker = (match.group("bracket_speaker") or match.group("speaker") or "").strip()
            text = match.group("text").strip()

            # 날짜나 시간처럼 보이는 값이 speaker로 오인되면 일반 문장으로 되돌립니다.
            if not re.fullmatch(r"[\d\s./:-]+", speaker) and not is_plain_heading_label(speaker):
                parsed_utterances.append((speaker, text, raw_line))
                continue

        # speaker가 없는 줄은 직전 발화의 줄바꿈 continuation으로 취급합니다.
        if parsed_utterances and parsed_utterances[-1][0] is not None:
            previous_speaker, previous_text, previous_raw_line = parsed_utterances.pop()
            parsed_utterances.append(
                (
                    previous_speaker,
                    f"{previous_text} {line}".strip(),
                    f"{previous_raw_line}\n{raw_line}",
                )
            )
        else:
            parsed_utterances.extend(split_speakerless_line(line))

    merged_utterances: list[tuple[str | None, str, str]] = []

    for speaker, text, raw_line in parsed_utterances:
        normalized_text = re.sub(r"[,.!?。！？…~\s]+", "", text.strip())
        if normalized_text in FILLER_TOKENS:
            continue

        if merged_utterances and speaker and merged_utterances[-1][0] == speaker:
            previous_speaker, previous_text, previous_raw_line = merged_utterances.pop()
            merged_utterances.append(
                (
                    previous_speaker,
                    f"{previous_text} {text}".strip(),
                    f"{previous_raw_line}\n{raw_line}",
                )
            )
        else:
            merged_utterances.append((speaker, text, raw_line))

    normalized_utterances = [
        TranscriptUtterance(
            utterance_id=f"u_{index + 1:04d}",
            speaker=speaker,
            text=text,
            index=index,
            raw_line=raw_line,
        )
        for index, (speaker, text, raw_line) in enumerate(merged_utterances)
    ]
    lines = [
        f"{utterance.speaker}: {utterance.text}" if utterance.speaker else utterance.text
        for utterance in normalized_utterances
    ]
    return NormalizedTranscript(normalized_utterances, "\n".join(lines).strip(), meeting_date)


def is_plain_heading_label(label: str) -> bool:
    """plain transcript heading/key label로 알려진 값인지 반환합니다."""
    label_key = re.sub(r"\s+", "", label.strip()).casefold()
    return label_key in PLAIN_HEADING_LABEL_KEYS


def split_speakerless_line(line: str) -> list[tuple[None, str, str]]:
    """긴 speakerless plain STT 줄을 LLM 근거 추적에 적당한 창으로 나눕니다."""
    text = line.strip()
    if len(text) <= MAX_SPEAKERLESS_UTTERANCE_CHARS:
        return [(None, text, text)]

    utterances: list[tuple[None, str, str]] = []
    remaining = text
    while len(remaining) > MAX_SPEAKERLESS_UTTERANCE_CHARS:
        window = remaining[:MAX_SPEAKERLESS_UTTERANCE_CHARS]
        split_at = max(window.rfind(boundary) for boundary in SENTENCE_BOUNDARY_CHARS) + 1
        if split_at <= 0:
            split_at = MAX_SPEAKERLESS_UTTERANCE_CHARS

        chunk = remaining[:split_at].strip()
        if chunk:
            utterances.append((None, chunk, chunk))
        remaining = remaining[split_at:].strip()

    if remaining:
        utterances.append((None, remaining, remaining))
    return utterances


def structured_transcript_payload_to_normalized_transcript(payload: object) -> NormalizedTranscript:
    """API structured transcript payload를 내부 NormalizedTranscript로 변환합니다."""
    raw_utterances = get_payload_value(payload, "utterances")
    if not isinstance(raw_utterances, list):
        raise ValueError("Structured transcript payload must include utterances.")

    utterances: list[TranscriptUtterance] = []
    for raw_utterance in raw_utterances:
        text = str(get_payload_value(raw_utterance, "text") or "").strip()
        if not text:
            continue

        speaker = str(get_payload_value(raw_utterance, "speaker") or "").strip() or "Unknown"
        utterance_id = str(get_payload_value(raw_utterance, "utterance_id") or "").strip()
        if not utterance_id:
            utterance_id = f"u_{len(utterances) + 1:04d}"

        raw_line = f"{speaker}: {text}"
        utterances.append(
            TranscriptUtterance(
                utterance_id=utterance_id,
                speaker=speaker,
                text=text,
                index=len(utterances),
                raw_line=raw_line,
                start_ms=optional_int(get_payload_value(raw_utterance, "start_ms")),
                end_ms=optional_int(get_payload_value(raw_utterance, "end_ms")),
            )
        )

    if not utterances:
        raise ValueError("Structured transcript payload did not include usable utterances.")

    text = "\n".join(utterance.raw_line for utterance in utterances).strip()
    return NormalizedTranscript(utterances=utterances, text=text, meeting_date=extract_meeting_date(text))


def get_payload_value(payload: object, key: str) -> object:
    """dict와 Pydantic 객체 양쪽에서 payload 값을 안전하게 읽습니다."""
    if isinstance(payload, dict):
        return payload.get(key)
    return getattr(payload, key, None)


def optional_int(value: object) -> int | None:
    """timestamp 같은 optional 숫자 값을 int 또는 None으로 정리합니다."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
