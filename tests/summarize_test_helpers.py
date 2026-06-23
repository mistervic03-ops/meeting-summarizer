"""Shared helpers for summarize.py tests."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def import_summarize_with_fakes():
    """fake OpenAI/dotenv 모듈로 summarize.py를 import합니다."""
    fake_dotenv = types.SimpleNamespace(load_dotenv=lambda: None)
    fake_openai = types.SimpleNamespace(OpenAI=Mock)

    with patch.dict(sys.modules, {"dotenv": fake_dotenv, "openai": fake_openai}):
        sys.modules.pop("summarize", None)
        return importlib.import_module("summarize")


summarize = import_summarize_with_fakes()


def empty_track_b_structure() -> dict[str, list]:
    """summarize.py에서 사용하는 최소 구조화 추출 형태를 반환합니다."""
    return {
        "summary_facts": [],
        "decisions": [],
        "action_items": [],
        "speaker_highlights": [],
        "warnings": [],
    }


def collect_schema_objects(schema: dict) -> list[dict]:
    """JSON schema 안의 object schema를 모두 수집합니다."""
    objects: list[dict] = []
    if schema.get("type") == "object":
        objects.append(schema)
    for value in schema.get("properties", {}).values():
        if isinstance(value, dict):
            objects.extend(collect_schema_objects(value))
    items = schema.get("items")
    if isinstance(items, dict):
        objects.extend(collect_schema_objects(items))
    return objects


def schema_contains_key(schema: object, key: str) -> bool:
    """JSON schema 안에 특정 key가 남아 있는지 확인합니다."""
    if isinstance(schema, dict):
        return key in schema or any(schema_contains_key(value, key) for value in schema.values())
    if isinstance(schema, list):
        return any(schema_contains_key(value, key) for value in schema)
    return False
