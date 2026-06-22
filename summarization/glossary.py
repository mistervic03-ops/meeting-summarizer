"""회의 요약 단계에서만 사용하는 용어집 로딩 helper입니다."""

from __future__ import annotations

import ast
import os
import re
from collections.abc import Iterable
from pathlib import Path


DEFAULT_SUMMARY_GLOSSARY_PATH = "config/summary_glossary.yaml"
MAX_GLOSSARY_TERM_LENGTH = 80


def load_summary_glossary(path: str | Path | None = None) -> list[str]:
    """요약용 용어집 파일을 읽어 정규화된 용어 목록을 반환합니다."""
    glossary_path = Path(path) if path is not None else Path(os.getenv("SUMMARY_GLOSSARY_PATH", DEFAULT_SUMMARY_GLOSSARY_PATH))
    try:
        content = glossary_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []

    return normalize_glossary_terms(parse_summary_glossary_terms(content))


def get_summary_glossary_terms(path: str | Path | None = None) -> list[str]:
    """프롬프트에 넣을 요약용 용어 목록을 로드하고 길이 제한을 적용합니다."""
    return truncate_glossary_terms(load_summary_glossary(path))


def normalize_glossary_terms(terms: Iterable[str]) -> list[str]:
    """용어 목록의 공백을 정리하고 대소문자 무시 중복을 제거합니다."""
    normalized_terms: list[str] = []
    seen_keys: set[str] = set()
    for term in terms:
        if not isinstance(term, str):
            continue
        cleaned = re.sub(r"\s+", " ", term).strip()
        if not cleaned or len(cleaned) > MAX_GLOSSARY_TERM_LENGTH:
            continue
        dedupe_key = cleaned.casefold()
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        normalized_terms.append(cleaned)
    return normalized_terms


def truncate_glossary_terms(terms: Iterable[str], max_chars: int = 1200, max_terms: int = 80) -> list[str]:
    """용어 목록을 순서대로 유지하면서 프롬프트 크기 제한 안에 맞춥니다."""
    if max_chars <= 0 or max_terms <= 0:
        return []

    selected_terms: list[str] = []
    used_chars = 0
    for term in normalize_glossary_terms(terms):
        if len(selected_terms) >= max_terms:
            break
        term_chars = len(f"- {term}\n")
        if used_chars + term_chars > max_chars:
            break
        selected_terms.append(term)
        used_chars += term_chars
    return selected_terms


def parse_summary_glossary_terms(content: str) -> list[str]:
    """지원하는 간단한 YAML terms 섹션에서 용어를 추출합니다."""
    lines = content.splitlines()
    terms: list[str] = []
    in_terms_section = False

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("terms:"):
            in_terms_section = True
            inline_value = stripped.removeprefix("terms:").strip()
            if inline_value:
                terms.extend(parse_inline_terms(inline_value))
            continue

        if not in_terms_section:
            continue
        if not line.startswith((" ", "\t")) and stripped.endswith(":"):
            in_terms_section = False
            continue
        if stripped.startswith("-"):
            term = parse_yaml_list_item(stripped)
            if term:
                terms.append(term)

    return terms


def parse_inline_terms(value: str) -> list[str]:
    """terms: [a, b] 형태의 간단한 inline list를 파싱합니다."""
    if not value.startswith("[") or not value.endswith("]"):
        return []
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError):
        inner_value = value[1:-1].strip()
        if not inner_value:
            return []
        return [item.strip().strip("\"'") for item in inner_value.split(",")]
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, str)]


def parse_yaml_list_item(value: str) -> str:
    """간단한 YAML list item에서 따옴표와 inline comment를 정리합니다."""
    item = value[1:].strip()
    if " #" in item:
        item = item.split(" #", 1)[0].strip()
    return item.strip("\"'")
