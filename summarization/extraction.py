"""구조화 회의 정보 추출 요청을 담당합니다."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from openai import OpenAI

from summarization.llm_provider import get_summarization_provider, request_claude_structured_structure
from summarization.openai_utils import create_openai_client, extract_response_json, get_structure_model
from summarization.prompts import STRUCTURE_SYSTEM_PROMPT, build_extraction_prompt
from summarization.schemas import MEETING_STRUCTURE_SCHEMA
from summarization.validation import ensure_structure_shape


def extract_structure(
    transcript: str,
    meeting_date: str,
    context: str = "",
    meeting_type: str = "general",
    glossary_terms: Sequence[str] | None = None,
) -> dict[str, Any]:
    """전처리된 전사문에서 구조화된 회의 사실을 추출합니다."""
    prompt = build_extraction_prompt(transcript, meeting_date, context, meeting_type, glossary_terms)
    if get_summarization_provider() == "claude":
        return request_claude_structured_structure(prompt)

    client = create_openai_client()
    return request_structured_structure(client, prompt)


def request_structured_structure(client: OpenAI, prompt: str) -> dict[str, Any]:
    """OpenAI Responses API에 schema-constrained 구조 추출을 요청합니다."""
    try:
        response = client.responses.create(
            model=get_structure_model(),
            input=[
                {"role": "system", "content": STRUCTURE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "meeting_structure",
                    "schema": MEETING_STRUCTURE_SCHEMA,
                    "strict": True,
                }
            },
        )
        structure = ensure_structure_shape(extract_response_json(response))
        return {
            "summary_facts": structure.summary_facts,
            "decisions": structure.decisions,
            "action_items": structure.action_items,
            "speaker_highlights": structure.speaker_highlights,
            "warnings": structure.warnings,
        }
    except Exception as exc:
        raise RuntimeError(f"OpenAI structure extraction request failed: {exc}") from exc
