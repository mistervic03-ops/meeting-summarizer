"""전사문을 발화 경계 기준으로 나누는 파이썬 전용 helper입니다."""

from __future__ import annotations

from summarization.models import NormalizedTranscript, TranscriptChunk, TranscriptUtterance


def build_chunk_text(utterances: list[TranscriptUtterance]) -> str:
    """발화 목록을 LLM 입력용 ID/화자 보존 텍스트로 변환합니다."""
    lines = [utterance.render_for_llm() for utterance in utterances]
    return "\n".join(lines).strip()


def segment_transcript(
    normalized: NormalizedTranscript,
    max_utterances: int = 80,
    overlap_utterances: int = 8,
) -> list[TranscriptChunk]:
    """정규화된 전사문을 발화 단위 chunk 목록으로 나눕니다."""
    validate_chunk_parameters(max_utterances, overlap_utterances)

    if not normalized.utterances:
        return []

    if len(normalized.utterances) <= max_utterances:
        return [build_transcript_chunk("c_0001", normalized.utterances, [], [])]

    chunks: list[TranscriptChunk] = []
    stride = max_utterances - overlap_utterances
    start_index = 0

    while start_index < len(normalized.utterances):
        end_index = min(start_index + max_utterances, len(normalized.utterances))
        chunk_utterances = normalized.utterances[start_index:end_index]
        overlap_before_ids = [
            utterance.utterance_id
            for utterance in chunk_utterances[:overlap_utterances]
            if start_index > 0
        ]
        overlap_after_ids = []
        if overlap_utterances > 0 and end_index < len(normalized.utterances):
            overlap_after_ids = [utterance.utterance_id for utterance in chunk_utterances[-overlap_utterances:]]
        chunks.append(
            build_transcript_chunk(
                f"c_{len(chunks) + 1:04d}",
                chunk_utterances,
                overlap_before_ids,
                overlap_after_ids,
            )
        )

        if end_index == len(normalized.utterances):
            break
        start_index += stride

    return chunks


def validate_chunk_parameters(max_utterances: int, overlap_utterances: int) -> None:
    """chunk 크기와 overlap 값이 유효한지 확인합니다."""
    if max_utterances <= 0:
        raise ValueError("max_utterances must be greater than 0.")
    if overlap_utterances < 0:
        raise ValueError("overlap_utterances must be greater than or equal to 0.")
    if overlap_utterances >= max_utterances:
        raise ValueError("overlap_utterances must be smaller than max_utterances.")


def build_transcript_chunk(
    chunk_id: str,
    utterances: list[TranscriptUtterance],
    overlap_before_ids: list[str],
    overlap_after_ids: list[str],
) -> TranscriptChunk:
    """발화 목록과 overlap 메타데이터로 TranscriptChunk를 만듭니다."""
    return TranscriptChunk(
        chunk_id=chunk_id,
        utterances=utterances,
        start_utterance_id=utterances[0].utterance_id,
        end_utterance_id=utterances[-1].utterance_id,
        text=build_chunk_text(utterances),
        overlap_before_ids=overlap_before_ids,
        overlap_after_ids=overlap_after_ids,
    )
