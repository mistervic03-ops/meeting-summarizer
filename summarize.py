"""Meeting summary skeleton using an OpenAI text model."""

from __future__ import annotations


SUMMARY_MODEL = "gpt-5.4"
MAP_REDUCE_THRESHOLD_CHARS = 40_000


def summarize_meeting(transcript: str) -> str:
    """Summarize a transcript using either a single-pass or map-reduce flow."""
    try:
        if should_use_map_reduce(transcript):
            return summarize_with_map_reduce(transcript)
        return summarize_single_pass(transcript)
    except Exception as exc:
        raise RuntimeError(f"Meeting summarization failed: {exc}") from exc


def should_use_map_reduce(transcript: str) -> bool:
    """Return whether a transcript is long enough to require map-reduce summarization."""
    return len(transcript) > MAP_REDUCE_THRESHOLD_CHARS


def summarize_single_pass(transcript: str) -> str:
    """Summarize a transcript in one model request."""
    try:
        raise NotImplementedError("Single-pass summarization will be added later.")
    except Exception as exc:
        raise RuntimeError(f"Single-pass summarization failed: {exc}") from exc


def summarize_with_map_reduce(transcript: str) -> str:
    """Summarize a long transcript with a map-reduce workflow."""
    try:
        raise NotImplementedError("Map-reduce summarization will be added later.")
    except Exception as exc:
        raise RuntimeError(f"Map-reduce summarization failed: {exc}") from exc
