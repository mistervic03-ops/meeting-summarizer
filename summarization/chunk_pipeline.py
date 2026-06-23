"""chunk 단위 구조 추출을 실행하는 내부 helper입니다."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from summarization.chunking import segment_transcript
from summarization.extraction import extract_structure
from summarization.merge import merge_structures
from summarization.models import NormalizedTranscript


logger = logging.getLogger("summarize")
DEFAULT_CHUNK_CONCURRENCY = 4
MAX_CHUNK_CONCURRENCY = 8


def extract_structure_by_chunks(
    normalized: NormalizedTranscript,
    meeting_date: str,
    context: str = "",
    max_utterances: int = 80,
    overlap_utterances: int = 8,
    meeting_type: str = "general",
    glossary_terms: Sequence[str] | None = None,
    progress_callback: Any | None = None,
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

    if len(chunks) == 1:
        structures = [
            extract_chunk_structure(
                chunks[0],
                meeting_date,
                context,
                meeting_type,
                glossary_terms,
            )
        ]
        notify_chunk_progress(progress_callback, completed_chunks=1, total_chunks=1)
        return merge_structures(structures)

    max_workers = min(get_summary_chunk_concurrency(), len(chunks))
    structures: list[dict[str, Any] | None] = [None] * len(chunks)
    completed_chunks = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(
                extract_chunk_structure,
                    chunk,
                    meeting_date,
                    context,
                    meeting_type,
                    glossary_terms,
            ): index
            for index, chunk in enumerate(chunks)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            structures[index] = future.result()
            completed_chunks += 1
            notify_chunk_progress(progress_callback, completed_chunks=completed_chunks, total_chunks=len(chunks))

    ordered_structures: list[dict[str, Any]] = []
    for structure in structures:
        if structure is None:
            raise RuntimeError("Chunk extraction did not produce a structure.")
        ordered_structures.append(structure)
    return merge_structures(ordered_structures)


def notify_chunk_progress(progress_callback: Any | None, completed_chunks: int, total_chunks: int) -> None:
    """선택적 chunk 진행률 callback을 호출합니다."""
    if progress_callback is None:
        return
    progress_callback(completed_chunks, total_chunks)


def get_summary_chunk_concurrency() -> int:
    """SUMMARY_CHUNK_CONCURRENCY 값을 읽고 허용 범위로 제한합니다."""
    raw_value = os.getenv("SUMMARY_CHUNK_CONCURRENCY")
    if raw_value is None:
        return DEFAULT_CHUNK_CONCURRENCY

    try:
        configured_value = int(raw_value)
    except ValueError:
        return DEFAULT_CHUNK_CONCURRENCY

    return max(1, min(configured_value, MAX_CHUNK_CONCURRENCY))


def extract_chunk_structure(
    chunk: Any,
    meeting_date: str,
    context: str,
    meeting_type: str,
    glossary_terms: Sequence[str] | None,
) -> dict[str, Any]:
    """단일 chunk 구조 추출을 실행하고 timing log를 남깁니다."""
    logger.info(
        "chunk_extraction chunk_id=%s start_utterance_id=%s end_utterance_id=%s",
        chunk.chunk_id,
        chunk.start_utterance_id,
        chunk.end_utterance_id,
    )
    started_at = time.perf_counter()
    structure = extract_structure(
        chunk.text,
        meeting_date,
        context,
        meeting_type=meeting_type,
        glossary_terms=glossary_terms,
    )
    logger.info(
        "chunk_extraction chunk_id=%s completed in %.3fs",
        chunk.chunk_id,
        time.perf_counter() - started_at,
    )
    return structure


def empty_structure() -> dict[str, Any]:
    """기존 structure shape의 빈 값을 반환합니다."""
    return {
        "summary_facts": [],
        "decisions": [],
        "action_items": [],
        "speaker_highlights": [],
        "warnings": [],
    }
