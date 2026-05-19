"""구조화 추출과 자연어 생성을 포함한 회의록 생성 파이프라인입니다."""

from __future__ import annotations

import sys

from summarization import pipeline as _pipeline
from summarization.extraction import extract_structure, request_structured_structure
from summarization.models import (
    CHUNK_STRATEGY,
    DEEP_STRATEGY,
    DIRECT_STRATEGY,
    MeetingStructure,
    NormalizedTranscript,
    PreprocessedTranscript,
    ProcessingStrategy,
    SummaryResult,
    TranscriptProfile,
    TranscriptUtterance,
    Utterance,
)
from summarization.normalization import (
    DATE_PATTERNS,
    FILLER_TOKENS,
    KOREAN_MONTH_DAY_PATTERN,
    SPEAKER_LINE_PATTERN,
    build_iso_date,
    extract_meeting_date,
    normalize_transcript,
    preprocess_transcript,
    structured_transcript_payload_to_normalized_transcript,
)
from summarization.openai_utils import (
    DEFAULT_STRUCTURE_MODEL,
    DEFAULT_SUMMARY_MODEL,
    collect_text_parts,
    create_openai_client,
    extract_response_json,
    extract_response_text,
    get_structure_model,
    get_summary_model,
)
from summarization.glossary import (
    DEFAULT_SUMMARY_GLOSSARY_PATH,
    MAX_GLOSSARY_TERM_LENGTH,
    get_summary_glossary_terms,
    load_summary_glossary,
    normalize_glossary_terms,
    parse_summary_glossary_terms,
    truncate_glossary_terms,
)
from summarization.policies import (
    ExtractionPolicy,
    PolicyApplicationResult,
    apply_extraction_policy,
    build_policy_prompt_guidance,
    get_extraction_policy,
)
from summarization.profiling import (
    ACTION_CUES,
    DECISION_CUES,
    REQUIREMENT_CUES,
    RISK_CUES,
    analyze_transcript_profile,
    choose_processing_strategy,
    count_cues_in_text,
    estimate_transcript_complexity,
    log_transcript_profile,
)
from summarization.prompts import (
    MINUTES_SYSTEM_PROMPT,
    MEETING_TYPE_POLICIES,
    MEETING_TYPES,
    STRUCTURE_SYSTEM_PROMPT,
    build_glossary_prompt_prefix,
    build_meeting_type_policy,
    build_context_prompt_prefix,
    build_extraction_prompt,
    build_minutes_focus_guidance,
    build_minutes_prompt,
    normalize_meeting_type,
)
from summarization.pipeline import (
    generate_minutes,
    logger,
    request_minutes_generation,
    run_timed_stage,
    summarize_meeting,
    summarize_transcript,
)
from summarization.rendering import build_summary_result, render_output
from summarization.schemas import MEETING_STRUCTURE_SCHEMA
from summarization.validation import (
    as_text,
    clean_text_list,
    ensure_structure_shape,
    find_quote_in_utterances,
    format_display_warnings,
    format_general_display_warning,
    filter_model_warnings,
    has_action_uncertainty_terms,
    has_decision_uncertainty_terms,
    is_generic_action_warning_subject,
    is_stale_action_warning,
    is_stale_decision_warning,
    normalize_action_owner,
    normalize_quote_for_matching,
    normalize_quote_text,
    normalize_source_quote,
    normalize_source_utterance_ids,
    normalize_warning_text,
    source_quote_is_valid,
    source_quote_in_transcript,
    unique_text_list,
    validate_source_quote_reference,
    validate_structure,
    warning_mentions_item,
)


_pipeline.set_compat_facade(sys.modules[__name__])
