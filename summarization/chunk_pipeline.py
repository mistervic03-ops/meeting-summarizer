"""chunk 단위 구조 추출을 실행하는 내부 helper입니다."""

from __future__ import annotations

import logging
import time
from typing import Any

from summarization.chunking import segment_transcript
from summarization.extraction import extract_structure
from summarization.merge import merge_structures
from summarization.models import NormalizedTranscript


logger = logging.getLogger("summarize")


def extract_structure_by_chunks(
    normalized: NormalizedTranscript,
    meeting_date: str,
    context: str = "",
    max_utterances: int = 80,
    overlap_utterances: int = 8,
    meeting_type: str = "general",
) -> dict[str, Any]:
    """정규화된 전사문을 chunk별로 구조 추출한 뒤 단순 병합합니다."""
    chunks = segment_transcript(
        normalized,
        max_utterances=max_utterances,
        overlap_utterances=overlap_utterances,
    )
    logger.info("chunk_extraction chunk_count=%s", len(chunks))

    if not chunks:
        return empty_structure()

    structures: list[dict[str, Any]] = []
    for chunk in chunks:
        logger.info(
            "chunk_extraction chunk_id=%s start_utterance_id=%s end_utterance_id=%s",
            chunk.chunk_id,
            chunk.start_utterance_id,
            chunk.end_utterance_id,
        )
        started_at = time.perf_counter()
        structures.append(extract_structure(chunk.text, meeting_date, context, meeting_type=meeting_type))
        logger.info(
            "chunk_extraction chunk_id=%s completed in %.3fs",
            chunk.chunk_id,
            time.perf_counter() - started_at,
        )

    return merge_structures(structures)


def empty_structure() -> dict[str, Any]:
    """기존 structure shape의 빈 값을 반환합니다."""
    return {
        "summary_facts": [],
        "decisions": [],
        "action_items": [],
        "speaker_highlights": [],
        "warnings": [],
    }
