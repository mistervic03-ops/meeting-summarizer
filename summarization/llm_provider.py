"""요약 LLM provider 선택과 Claude API 호출 보조 함수입니다."""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

from summarization.prompts import MINUTES_SYSTEM_PROMPT, STRUCTURE_SYSTEM_PROMPT
from summarization.schemas import MEETING_STRUCTURE_SCHEMA
from summarization.validation import ensure_structure_shape


DEFAULT_SUMMARIZATION_PROVIDER = "openai"
DEFAULT_CLAUDE_STRUCTURE_MODEL = "claude-sonnet-4-6"
DEFAULT_CLAUDE_SUMMARY_MODEL = "claude-sonnet-4-6"
CLAUDE_MAX_TOKENS = 8192


def get_summarization_provider() -> str:
    """환경 변수에서 요약 LLM provider를 읽고 지원 여부를 확인합니다."""
    load_dotenv()
    provider = os.getenv("SUMMARIZATION_PROVIDER", DEFAULT_SUMMARIZATION_PROVIDER).strip().lower()
    if provider in {"openai", "claude"}:
        return provider
    raise ValueError("Unsupported SUMMARIZATION_PROVIDER. Use 'openai' or 'claude'.")


def create_anthropic_client() -> Any:
    """환경 변수의 API 키를 사용해 Anthropic API client를 만듭니다."""
    try:
        load_dotenv()
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError("ANTHROPIC_API_KEY is missing. Add it to your .env file.")

        from anthropic import Anthropic

        return Anthropic()
    except Exception as exc:
        raise RuntimeError(f"Anthropic client initialization failed: {exc}") from exc


def get_claude_structure_model() -> str:
    """Claude 구조화 추출에 사용할 모델명을 반환합니다."""
    return os.getenv("CLAUDE_STRUCTURE_MODEL", DEFAULT_CLAUDE_STRUCTURE_MODEL)


def get_claude_summary_model() -> str:
    """Claude 자연어 회의록 생성에 사용할 모델명을 반환합니다."""
    return os.getenv("CLAUDE_SUMMARY_MODEL", DEFAULT_CLAUDE_SUMMARY_MODEL)


def request_claude_structured_structure(prompt: str) -> dict[str, Any]:
    """Claude API에 JSON 전용 구조 추출을 요청하고 기존 shape로 정규화합니다."""
    client = create_anthropic_client()
    try:
        response = client.messages.create(
            model=get_claude_structure_model(),
            max_tokens=CLAUDE_MAX_TOKENS,
            system=STRUCTURE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_claude_json_prompt(prompt)}],
        )
        structure = ensure_structure_shape(parse_claude_json_response(response))
        return {
            "summary_facts": structure.summary_facts,
            "decisions": structure.decisions,
            "action_items": structure.action_items,
            "speaker_highlights": structure.speaker_highlights,
            "warnings": structure.warnings,
        }
    except Exception as exc:
        raise RuntimeError(f"Claude structure extraction request failed: {exc}") from exc


def request_claude_minutes_generation(prompt: str) -> str:
    """Claude API에 자연어 회의록 생성을 요청합니다."""
    client = create_anthropic_client()
    try:
        response = client.messages.create(
            model=get_claude_summary_model(),
            max_tokens=CLAUDE_MAX_TOKENS,
            system=MINUTES_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return extract_claude_response_text(response)
    except Exception as exc:
        raise RuntimeError(f"Claude minutes generation request failed: {exc}") from exc


def build_claude_json_prompt(prompt: str) -> str:
    """Claude 구조 추출 요청에 schema와 JSON-only 지침을 덧붙입니다."""
    schema_json = json.dumps(MEETING_STRUCTURE_SCHEMA, ensure_ascii=False, indent=2)
    return f"""
{prompt}

<OUTPUT_SCHEMA>
{schema_json}
</OUTPUT_SCHEMA>

반드시 위 OUTPUT_SCHEMA와 같은 top-level key를 가진 JSON object 하나만 반환하세요.
Markdown, 코드블록, 설명 문장, 주석을 붙이지 마세요.
JSON 문자열 밖에는 어떤 텍스트도 출력하지 마세요.
""".strip()


def parse_claude_json_response(response: object) -> dict[str, Any]:
    """Claude 응답 텍스트를 JSON object로 파싱합니다."""
    text = extract_claude_response_text(response)
    try:
        parsed_json = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude response was not valid JSON: {exc}") from exc

    if not isinstance(parsed_json, dict):
        raise ValueError("Claude structured response must be a JSON object.")
    return parsed_json


def extract_claude_response_text(response: object) -> str:
    """Anthropic message 응답 또는 테스트 mock에서 텍스트를 추출합니다."""
    if isinstance(response, dict):
        content = response.get("content", [])
    else:
        content = getattr(response, "content", [])

    text_parts = collect_claude_text_parts(content)
    if text_parts:
        return "\n".join(text_parts).strip()

    raise ValueError("Claude response did not include text.")


def collect_claude_text_parts(value: object) -> list[str]:
    """Claude 응답 content block에서 text 값을 모읍니다."""
    text_parts: list[str] = []

    if isinstance(value, str):
        if value.strip():
            text_parts.append(value.strip())
        return text_parts

    if isinstance(value, list):
        for item in value:
            text_parts.extend(collect_claude_text_parts(item))
        return text_parts

    if isinstance(value, dict):
        value_text = value.get("text")
        if isinstance(value_text, str) and value_text.strip():
            text_parts.append(value_text.strip())
        return text_parts

    text_value = getattr(value, "text", None)
    if isinstance(text_value, str) and text_value.strip():
        text_parts.append(text_value.strip())

    return text_parts
