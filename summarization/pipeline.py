"""회의 요약 파이프라인 orchestration을 담당합니다."""

from __future__ import annotations

import logging
import json
import sys
import time
from collections.abc import Sequence
from typing import Any

from openai import OpenAI

from summarization.chunk_pipeline import extract_structure_by_chunks
from summarization.extraction import extract_structure
from summarization.glossary import get_summary_glossary_terms
from summarization.llm_provider import (
    get_claude_structure_model,
    get_claude_summary_model,
    get_summarization_provider,
    request_claude_minutes_generation,
)
from summarization.models import CHUNK_STRATEGY, DEEP_STRATEGY, NormalizedTranscript, PreprocessedTranscript, SummaryResult
from summarization.normalization import extract_meeting_date, normalize_transcript, preprocess_transcript
from summarization.openai_utils import create_openai_client, extract_response_text, get_structure_model, get_summary_model
from summarization.policies import apply_extraction_policy, get_extraction_policy
from summarization.profiling import analyze_transcript_profile, choose_processing_strategy, log_transcript_profile
from summarization.prompts import MINUTES_SYSTEM_PROMPT, build_minutes_prompt, normalize_meeting_type
from summarization.rendering import build_summary_result, render_output
from summarization.validation import validate_structure


logger = logging.getLogger("summarize")
_compat_facade: Any | None = None


def summarize_meeting(transcript: str) -> str:
    """전사문을 요약하고 렌더링된 회의록 텍스트를 반환합니다."""
    return summarize_transcript(transcript)["minutes"]


def summarize_transcript(
    transcript: str,
    context: str = "",
    normalized_transcript: NormalizedTranscript | None = None,
    meeting_type: str = "general",
) -> SummaryResult:
    """전처리, 구조 추출, 회의록 생성을 실행하고 구조화 결과를 반환합니다."""
    try:
        resolved_meeting_type = resolve_compat_name("normalize_meeting_type", normalize_meeting_type)(meeting_type)
        extraction_policy = resolve_compat_name("get_extraction_policy", get_extraction_policy)(resolved_meeting_type)
        logger.info(
            "[SUMMARY_POLICY] meeting_type=%s action_threshold=%s decision_threshold=%s",
            extraction_policy.meeting_type,
            extraction_policy.action_threshold,
            extraction_policy.decision_threshold,
        )
        source_text = normalized_transcript.text if normalized_transcript is not None else transcript
        if not source_text.strip():
            raise ValueError("Transcript is empty.")

        total_started_at = time.perf_counter()
        run_stage = resolve_compat_name("run_timed_stage", run_timed_stage)
        glossary_terms = resolve_compat_name("get_summary_glossary_terms", get_summary_glossary_terms)()

        if normalized_transcript is None:
            preprocessed, elapsed = run_stage(
                "preprocess_transcript",
                resolve_compat_name("preprocess_transcript", preprocess_transcript),
                transcript,
            )
            logger.info("preprocess_transcript completed in %.3fs", elapsed)

            normalized_transcript = resolve_compat_name("normalize_transcript", normalize_transcript)(preprocessed.text)
        else:
            meeting_date = normalized_transcript.meeting_date or resolve_compat_name("extract_meeting_date", extract_meeting_date)(
                normalized_transcript.text
            )
            preprocessed = PreprocessedTranscript(normalized_transcript.text, meeting_date)
            logger.info("summarize_transcript using provided normalized_transcript")

        profile = resolve_compat_name("analyze_transcript_profile", analyze_transcript_profile)(normalized_transcript)
        selected_strategy = resolve_compat_name("choose_processing_strategy", choose_processing_strategy)(profile)
        resolve_compat_name("log_transcript_profile", log_transcript_profile)(profile, selected_strategy)
        logger.info("summarize_transcript selected_strategy=%s", selected_strategy)
        provider = resolve_compat_name("get_summarization_provider", get_summarization_provider)()
        structure_model = get_structure_model_for_provider(provider)
        summary_model = get_summary_model_for_provider(provider)
        transcript_chars = len(normalized_transcript.text)
        logger.info(
            "[SUMMARY_TIMING] provider=%s strategy=%s structure_model=%s summary_model=%s transcript_chars=%s",
            provider,
            selected_strategy,
            structure_model,
            summary_model,
            transcript_chars,
        )

        if selected_strategy in {CHUNK_STRATEGY, DEEP_STRATEGY}:
            if selected_strategy == DEEP_STRATEGY:
                logger.info("deep strategy currently uses chunk pipeline")
            logger.info("summarize_transcript using chunk extraction path")
            structure, elapsed = run_stage(
                "extract_structure_by_chunks",
                resolve_compat_name("extract_structure_by_chunks", extract_structure_by_chunks),
                normalized_transcript,
                preprocessed.meeting_date,
                context,
                meeting_type=resolved_meeting_type,
                glossary_terms=glossary_terms,
            )
            extraction_stage = "chunk_extraction"
        else:
            logger.info("summarize_transcript using direct extraction path")
            structure, elapsed = run_stage(
                "extract_structure",
                resolve_compat_name("extract_structure", extract_structure),
                normalized_transcript.render_for_llm(),
                preprocessed.meeting_date,
                context,
                resolved_meeting_type,
                glossary_terms=glossary_terms,
            )
            extraction_stage = "extraction"
        logger.info("extract_structure completed in %.3fs", elapsed)
        logger.info(
            "[SUMMARY_TIMING] provider=%s stage=%s model=%s transcript_chars=%s output_chars=%s elapsed_seconds=%.3f",
            provider,
            extraction_stage,
            structure_model,
            transcript_chars,
            structure_output_length(structure),
            elapsed,
        )

        policy_result = resolve_compat_name("apply_extraction_policy", apply_extraction_policy)(structure, resolved_meeting_type)
        structure = policy_result.structure
        logger.info(
            "[SUMMARY_POLICY] downgraded_actions=%s downgraded_decisions=%s",
            policy_result.downgraded_action_count,
            policy_result.downgraded_decision_count,
        )

        structure, elapsed = run_stage(
            "validate_structure",
            resolve_compat_name("validate_structure", validate_structure),
            structure,
            preprocessed.text,
            normalized_transcript,
        )
        logger.info("validate_structure completed in %.3fs", elapsed)

        minutes, elapsed = run_stage(
            "generate_minutes",
            resolve_compat_name("generate_minutes", generate_minutes),
            preprocessed.text,
            structure,
            context,
            resolved_meeting_type,
            glossary_terms=glossary_terms,
        )
        logger.info("generate_minutes completed in %.3fs", elapsed)
        logger.info(
            "[SUMMARY_TIMING] provider=%s stage=minutes_generation model=%s transcript_chars=%s output_chars=%s elapsed_seconds=%.3f",
            provider,
            summary_model,
            transcript_chars,
            len(minutes),
            elapsed,
        )

        markdown, elapsed = run_stage(
            "render_output",
            resolve_compat_name("render_output", render_output),
            structure,
            minutes,
            resolved_meeting_type,
        )
        logger.info("render_output completed in %.3fs", elapsed)
        logger.info("[SUMMARY_TIMING] stage=render_output output_chars=%s elapsed_seconds=%.3f", len(markdown), elapsed)
        logger.info("summarize_transcript completed in %.3fs", time.perf_counter() - total_started_at)
        return resolve_compat_name("build_summary_result", build_summary_result)(structure, markdown)
    except Exception as exc:
        raise RuntimeError(f"Meeting summarization failed: {exc}") from exc


def run_timed_stage(stage_name: str, func: Any, *args: Any, **kwargs: Any) -> tuple[Any, float]:
    """파이프라인 한 단계를 실행하고 결과와 소요 시간을 반환합니다."""
    started_at = time.perf_counter()
    try:
        return func(*args, **kwargs), time.perf_counter() - started_at
    except Exception as exc:
        raise RuntimeError(f"{stage_name} failed: {exc}") from exc


def get_structure_model_for_provider(provider: str) -> str:
    """요약 provider별 구조 추출 모델명을 반환합니다."""
    if provider == "claude":
        return resolve_compat_name("get_claude_structure_model", get_claude_structure_model)()
    return resolve_compat_name("get_structure_model", get_structure_model)()


def get_summary_model_for_provider(provider: str) -> str:
    """요약 provider별 회의록 생성 모델명을 반환합니다."""
    if provider == "claude":
        return resolve_compat_name("get_claude_summary_model", get_claude_summary_model)()
    return resolve_compat_name("get_summary_model", get_summary_model)()


def structure_output_length(structure: dict[str, Any]) -> int:
    """구조화 추출 결과의 대략적인 출력 길이를 반환합니다."""
    try:
        return len(json.dumps(structure, ensure_ascii=False))
    except TypeError:
        return len(str(structure))


def generate_minutes(
    preprocessed_text: str | PreprocessedTranscript,
    structure: dict[str, Any],
    context: str = "",
    meeting_type: str = "general",
    glossary_terms: Sequence[str] | None = None,
) -> str:
    """정리된 전사문과 검증된 JSON으로 자연스러운 한국어 회의록을 생성합니다."""
    transcript_text = preprocessed_text.text if isinstance(preprocessed_text, PreprocessedTranscript) else preprocessed_text
    prompt = resolve_compat_name("build_minutes_prompt", build_minutes_prompt)(
        transcript_text,
        structure,
        context,
        meeting_type,
        glossary_terms,
    )
    if resolve_compat_name("get_summarization_provider", get_summarization_provider)() == "claude":
        return resolve_compat_name("request_claude_minutes_generation", request_claude_minutes_generation)(prompt)

    client = resolve_compat_name("create_openai_client", create_openai_client)()
    return resolve_compat_name("request_minutes_generation", request_minutes_generation)(client, prompt)


def request_minutes_generation(client: OpenAI, prompt: str) -> str:
    """OpenAI Responses API에 자연어 회의록 생성을 요청합니다."""
    try:
        response = client.responses.create(
            model=resolve_compat_name("get_summary_model", get_summary_model)(),
            input=[
                {"role": "system", "content": MINUTES_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        return resolve_compat_name("extract_response_text", extract_response_text)(response)
    except Exception as exc:
        raise RuntimeError(f"OpenAI minutes generation request failed: {exc}") from exc


def resolve_compat_name(name: str, default: Any) -> Any:
    """기존 summarize.* patch 호환성을 위해 facade의 현재 이름을 우선 사용합니다."""
    if _compat_facade is not None:
        return getattr(_compat_facade, name, default)

    summarize_module = sys.modules.get("summarize")
    if summarize_module is None:
        return default
    return getattr(summarize_module, name, default)


def set_compat_facade(facade_module: Any) -> None:
    """테스트와 기존 호출자가 patch하는 summarize facade 모듈을 등록합니다."""
    global _compat_facade
    _compat_facade = facade_module
