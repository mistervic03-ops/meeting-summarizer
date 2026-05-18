"""회의 요약 엔진의 구조화 출력 스키마입니다."""

from __future__ import annotations

from typing import Any


MEETING_STRUCTURE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary_facts", "decisions", "action_items", "speaker_highlights", "warnings"],
    "properties": {
        "summary_facts": {
            "type": "array",
            "items": {"type": "string"},
        },
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["decision", "status", "source_quote", "source_utterance_ids"],
                "properties": {
                    "decision": {"type": "string"},
                    "status": {"type": "string", "enum": ["확정", "미확정"]},
                    "source_quote": {"type": "string"},
                    "source_utterance_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["task", "owner", "due_date", "confidence", "source_quote", "source_utterance_ids"],
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "due_date": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "low"]},
                    "source_quote": {"type": "string"},
                    "source_utterance_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "speaker_highlights": {
            "type": "array",
            "items": {"type": "string"},
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}
