"""OpenAI client 생성, 모델 선택, 응답 파싱 보조 함수입니다."""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


# 회의 구조 추출은 비용과 속도를 고려해 경량 모델을 기본값으로 사용합니다.
DEFAULT_STRUCTURE_MODEL = "gpt-4o-mini"

# 자연스러운 최종 회의록 문장은 기존 요약 모델명을 유지해 생성합니다.
DEFAULT_SUMMARY_MODEL = "gpt-5.4"


def create_openai_client() -> OpenAI:
    """환경 변수의 API 키를 사용해 OpenAI API client를 만듭니다."""
    try:
        # API 키는 코드에 하드코딩하지 않고 .env 또는 서버 환경 변수에서만 읽습니다.
        load_dotenv()
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY is missing. Add it to your .env file.")
        return OpenAI()
    except Exception as exc:
        raise RuntimeError(f"OpenAI client initialization failed: {exc}") from exc


def get_structure_model() -> str:
    """구조화 추출에 사용할 모델명을 반환합니다."""
    return os.getenv("OPENAI_STRUCTURE_MODEL", DEFAULT_STRUCTURE_MODEL)


def get_summary_model() -> str:
    """자연어 회의록 생성에 사용할 모델명을 반환합니다."""
    return os.getenv("OPENAI_SUMMARY_MODEL", DEFAULT_SUMMARY_MODEL)


def extract_response_json(response: object) -> dict[str, Any]:
    """Responses API 또는 테스트 mock 응답에서 구조화 JSON을 추출합니다."""
    parsed = getattr(response, "output_parsed", None)
    if isinstance(parsed, dict):
        return parsed

    if isinstance(response, dict):
        parsed_dict = response.get("output_parsed")
        if isinstance(parsed_dict, dict):
            return parsed_dict

    text = extract_response_text(response)
    try:
        parsed_json = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenAI response was not valid JSON: {exc}") from exc

    if not isinstance(parsed_json, dict):
        raise ValueError("OpenAI structured response must be a JSON object.")
    return parsed_json


def extract_response_text(response: object) -> str:
    """OpenAI Responses API 응답에서 일반 텍스트를 추출합니다."""
    # SDK 버전이나 테스트 mock 형태에 따라 output_text 또는 중첩 output을 지원합니다.
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    if isinstance(response, dict):
        dict_output_text = response.get("output_text")
        if isinstance(dict_output_text, str) and dict_output_text.strip():
            return dict_output_text.strip()
        output = response.get("output", [])
    else:
        output = getattr(response, "output", [])

    text_parts = collect_text_parts(output)
    if text_parts:
        return "\n".join(text_parts).strip()

    raise ValueError("OpenAI summary response did not include text.")


def collect_text_parts(value: object) -> list[str]:
    """중첩된 OpenAI 응답 content에서 텍스트 값을 모읍니다."""
    text_parts: list[str] = []

    if isinstance(value, str):
        if value.strip():
            text_parts.append(value.strip())
        return text_parts

    if isinstance(value, list):
        for item in value:
            text_parts.extend(collect_text_parts(item))
        return text_parts

    if isinstance(value, dict):
        for key in ("text", "json"):
            value_text = value.get(key)
            if isinstance(value_text, str) and value_text.strip():
                text_parts.append(value_text.strip())
        for key in ("content", "output"):
            if key in value:
                text_parts.extend(collect_text_parts(value[key]))
        return text_parts

    text_value = getattr(value, "text", None)
    if isinstance(text_value, str) and text_value.strip():
        text_parts.append(text_value.strip())

    for attr_name in ("content", "output"):
        attr_value = getattr(value, attr_name, None)
        if attr_value is not None:
            text_parts.extend(collect_text_parts(attr_value))

    return text_parts
