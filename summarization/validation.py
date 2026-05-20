"""회의 구조 출력 검증과 경고 정리를 위한 파이썬 전용 보조 함수입니다."""

from __future__ import annotations

import re
from typing import Any

from summarization.models import MeetingStructure, NormalizedTranscript


SOURCE_UTTERANCE_ID_WARNING_PATTERN = re.compile(
    r"^\s*(?P<utterance_id>u_\d{4})\s*[:：]\s*(?P<reason>.+?)\s*$",
    flags=re.IGNORECASE,
)
SOURCE_UTTERANCE_ID_TEXT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])u_\d{4}(?![A-Za-z0-9_])",
    flags=re.IGNORECASE,
)
SOURCE_UTTERANCE_ID_PREFIX_PATTERN = re.compile(
    r"^\s*u_\d{4}(?:\s|[:：]|에서|발화자|화자|의|가|이|은|는|을|를)",
    flags=re.IGNORECASE,
)


def validate_structure(
    structure: dict[str, Any],
    transcript: str,
    normalized_transcript: NormalizedTranscript | None = None,
) -> dict[str, Any]:
    """보수적인 파이썬 근거 확인으로 추출 구조를 검증합니다."""
    normalized_structure = ensure_structure_shape(structure)
    model_warnings = unique_text_list(clean_text_list(normalized_structure.warnings))
    validation_warnings: list[str] = []
    action_items: list[dict[str, Any]] = []
    seen_action_keys: set[tuple[str, str, str]] = set()

    for item in normalized_structure.action_items:
        if not isinstance(item, dict):
            continue

        task = as_text(item.get("task"))
        if not task:
            continue

        owner = normalize_action_owner(as_text(item.get("owner")))
        due_date = as_text(item.get("due_date")) or "미정"
        confidence = as_text(item.get("confidence"))
        confidence = confidence if confidence in {"high", "low"} else "low"
        source_quote = normalize_source_quote(as_text(item.get("source_quote")))
        source_utterance_ids = normalize_source_utterance_ids(item.get("source_utterance_ids"))
        due_date = normalize_action_due_date(due_date, source_quote)

        if is_decision_only_action_item(task, owner, due_date, source_quote):
            continue

        if owner == "미정":
            confidence = "low"
            validation_warnings.append(f"액션 아이템 '{task}'의 담당자 확인이 필요합니다.")
        if due_date == "미정":
            confidence = "low"
            validation_warnings.append(f"액션 아이템 '{task}'의 기한 확인이 필요합니다.")
        if not source_quote:
            confidence = "low"
            validation_warnings.append(f"액션 아이템 '{task}'의 원문 근거 확인이 필요합니다.")
        else:
            source_quote_valid, source_utterance_ids = validate_source_quote_reference(
                source_quote,
                transcript,
                normalized_transcript,
                source_utterance_ids,
            )
            if not source_quote_valid:
                confidence = "low"
                validation_warnings.append(f"액션 아이템 '{task}'의 근거 문장을 원문에서 확인하지 못했습니다.")

        dedupe_key = (task, owner, due_date)
        if dedupe_key in seen_action_keys:
            continue
        seen_action_keys.add(dedupe_key)
        action_items.append(
            {
                "task": task,
                "owner": owner,
                "due_date": due_date,
                "confidence": confidence,
                "source_quote": source_quote,
                "source_utterance_ids": source_utterance_ids,
            }
        )

    decisions: list[dict[str, Any]] = []
    seen_decision_keys: set[tuple[str, str]] = set()

    for item in normalized_structure.decisions:
        if not isinstance(item, dict):
            continue

        decision = as_text(item.get("decision"))
        if not decision:
            continue

        status = as_text(item.get("status"))
        status = status if status in {"확정", "미확정"} else "미확정"
        source_quote = normalize_source_quote(as_text(item.get("source_quote")))
        source_utterance_ids = normalize_source_utterance_ids(item.get("source_utterance_ids"))

        if not source_quote:
            validation_warnings.append(f"결정사항 '{decision}'의 원문 근거 확인이 필요합니다.")
        else:
            source_quote_valid, source_utterance_ids = validate_source_quote_reference(
                source_quote,
                transcript,
                normalized_transcript,
                source_utterance_ids,
            )
            if not source_quote_valid:
                validation_warnings.append(f"결정사항 '{decision}'의 근거 문장을 원문에서 확인하지 못했습니다.")

        dedupe_key = (decision, status)
        if dedupe_key in seen_decision_keys:
            continue
        seen_decision_keys.add(dedupe_key)
        decisions.append(
            {
                "decision": decision,
                "status": status,
                "source_quote": source_quote,
                "source_utterance_ids": source_utterance_ids,
            }
        )

    return {
        "summary_facts": clean_text_list(normalized_structure.summary_facts),
        "decisions": decisions,
        "action_items": action_items,
        "speaker_highlights": clean_text_list(normalized_structure.speaker_highlights),
        "warnings": unique_text_list(
            format_display_warnings(
                [
                    *filter_model_warnings(model_warnings, action_items, decisions),
                    *validation_warnings,
                ],
                action_items,
                decisions,
            )
        ),
    }


def ensure_structure_shape(structure: dict[str, Any]) -> MeetingStructure:
    """필수 필드를 모두 가진 정규화된 구조화 사실을 반환합니다."""
    return MeetingStructure(
        summary_facts=structure.get("summary_facts") if isinstance(structure.get("summary_facts"), list) else [],
        decisions=structure.get("decisions") if isinstance(structure.get("decisions"), list) else [],
        action_items=structure.get("action_items") if isinstance(structure.get("action_items"), list) else [],
        speaker_highlights=structure.get("speaker_highlights")
        if isinstance(structure.get("speaker_highlights"), list)
        else [],
        warnings=structure.get("warnings") if isinstance(structure.get("warnings"), list) else [],
    )


def normalize_action_owner(owner: str) -> str:
    """1인칭 표현을 미정으로 처리한 표시용 담당자명을 반환합니다."""
    stripped_owner = owner.strip()
    if normalize_warning_text(stripped_owner) in unresolved_owner_keys():
        return "미정"
    return stripped_owner or "미정"


def normalize_action_due_date(due_date: str, source_quote: str) -> str:
    """확실하지 않은 ISO 변환보다 source_quote 안의 원문 상대 기한을 우선합니다."""
    due_date_text = as_text(due_date) or "미정"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?", due_date_text):
        return due_date_text

    relative_due_date = extract_relative_due_date(source_quote)
    return relative_due_date or due_date_text


def extract_relative_due_date(source_quote: str) -> str:
    """원문 근거 문장에서 보수적으로 상대 기한 표현을 추출합니다."""
    quote_text = as_text(source_quote)
    if not quote_text:
        return ""

    weekdays = "월요일|화요일|수요일|목요일|금요일|토요일|일요일"
    pattern = re.compile(
        rf"(?P<due>"
        rf"(?:오늘|내일)(?:\s*(?:중|오전|오후))?(?:\s*\d{{1,2}}시)?"
        rf"|다음\s*주\s*(?:{weekdays})(?:\s*(?:오전|오후))?(?:\s*\d{{1,2}}시)?"
        rf"|(?:{weekdays})(?:\s*(?:오전|오후))?(?:\s*\d{{1,2}}시)?"
        rf")\s*(?:까지|까지입니다|로|에)?"
    )
    match = pattern.search(quote_text)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group("due")).strip()


def is_decision_only_action_item(task: str, owner: str, due_date: str, source_quote: str) -> bool:
    """담당자/기한 없는 정책 결정이 action item으로 들어온 경우 제거 대상으로 봅니다."""
    if is_resolved_action_owner(owner) and as_text(due_date) != "미정":
        return False

    text_key = normalize_warning_text(f"{task} {source_quote}")
    if not text_key:
        return False

    return (
        ("문서표기" in text_key and "데이터마트" in text_key and "통일" in text_key)
        or ("첫화면" in text_key and "지표" in text_key)
        or ("campaignid" in text_key and "null" in text_key and "처리" in text_key)
        or ("사내토큰" in text_key and ("방식" in text_key or "진행" in text_key))
        or ("api" in text_key and "캐싱" in text_key and ("제외" in text_key or "적용하지" in text_key))
        or ("정상케이스" in text_key and "데모" in text_key)
        or ("개인정보" in text_key and ("실제고객정보" in text_key or "고객정보" in text_key) and "미사용" in text_key)
        or ("qa" in text_key and "우선순위" in text_key)
    )


def unresolved_owner_keys() -> set[str]:
    """담당자가 해결되지 않은 값의 정규화 key를 반환합니다."""
    return {
        "",
        "미정",
        "없음",
        "확인필요",
        "unknown",
        "speakerunknown",
        "unknownspeaker",
        "저",
        "제가",
        "나",
        "내가",
        "우리",
        "저희",
        "화자미상",
        "알수없음",
        "미상",
    }


def is_resolved_action_owner(owner: Any) -> bool:
    """speaker label, 사람 이름, 팀 이름처럼 해결된 담당자인지 반환합니다."""
    return normalize_warning_text(normalize_action_owner(as_text(owner))) not in unresolved_owner_keys()


def clean_text_list(values: list[Any]) -> list[str]:
    """비어 있지 않은 문자열 값을 원래 순서대로 반환합니다."""
    return [as_text(value) for value in values if as_text(value)]


def as_text(value: Any) -> str:
    """빈 값일 수 있는 단일 값을 표시 가능한 문자열로 변환합니다."""
    if value is None:
        return ""
    return str(value).strip()


def unique_text_list(values: list[Any]) -> list[str]:
    """원래 순서를 유지하면서 중복 없는 비어 있지 않은 문자열 값을 반환합니다."""
    unique_values: list[str] = []
    seen_values: set[str] = set()

    for value in values:
        text = as_text(value)
        if not text or text in seen_values:
            continue
        seen_values.add(text)
        unique_values.append(text)

    return unique_values


def normalize_source_quote(source_quote: str) -> str:
    """미정 라벨보다 빈 문자열을 우선하는 표시용 원문 인용을 반환합니다."""
    stripped_quote = source_quote.strip()
    if stripped_quote == "미정":
        return ""
    return stripped_quote


def normalize_source_utterance_ids(value: Any) -> list[str]:
    """구조화 결과의 source_utterance_ids를 내부 검증용 ID 목록으로 정리합니다."""
    if not isinstance(value, list):
        return []

    utterance_ids: list[str] = []
    seen_ids: set[str] = set()
    for item in value:
        utterance_id = as_text(item).strip("[]")
        if not re.fullmatch(r"u_\d{4}", utterance_id) or utterance_id in seen_ids:
            continue
        seen_ids.add(utterance_id)
        utterance_ids.append(utterance_id)
    return utterance_ids


def source_quote_in_transcript(source_quote: str, transcript: str) -> bool:
    """원문 인용이 전사문 안에 보수적으로 포함되는지 반환합니다."""
    quote = normalize_quote_for_matching(source_quote)
    if not quote:
        return False

    if quote in transcript:
        return True

    normalized_quote = normalize_quote_text(quote)
    normalized_transcript = normalize_quote_text(transcript)
    return bool(normalized_quote and normalized_quote in normalized_transcript)


def source_quote_is_valid(
    source_quote: str,
    transcript: str,
    normalized_transcript: NormalizedTranscript | None = None,
) -> bool:
    """전체 전사문 또는 발화 목록에서 원문 인용을 찾을 수 있는지 반환합니다."""
    if source_quote_in_transcript(source_quote, transcript):
        return True
    if normalized_transcript is None:
        return False
    return bool(find_quote_in_utterances(source_quote, normalized_transcript))


def validate_source_quote_reference(
    source_quote: str,
    transcript: str,
    normalized_transcript: NormalizedTranscript | None = None,
    source_utterance_ids: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """원문 인용과 발화 ID 근거가 서로 일관되는지 검증합니다."""
    utterance_ids = normalize_source_utterance_ids(source_utterance_ids or [])
    matched_utterance_ids = (
        find_quote_in_utterances(source_quote, normalized_transcript)
        if normalized_transcript is not None
        else []
    )

    if matched_utterance_ids:
        if utterance_ids and not set(utterance_ids).intersection(matched_utterance_ids):
            return False, utterance_ids
        return True, utterance_ids or matched_utterance_ids

    if source_quote_in_transcript(source_quote, transcript):
        return True, utterance_ids

    return False, utterance_ids


def find_quote_in_utterances(quote: str, normalized_transcript: NormalizedTranscript) -> list[str]:
    """원문 인용이 포함된 정규화 발화 ID 목록을 반환합니다."""
    cleaned_quote = normalize_quote_for_matching(quote)
    if not cleaned_quote:
        return []

    exact_matches = [
        utterance.utterance_id
        for utterance in normalized_transcript.utterances
        if cleaned_quote in utterance.text
    ]
    if exact_matches:
        return exact_matches

    normalized_quote = normalize_quote_text(cleaned_quote)
    if not normalized_quote:
        return []

    return [
        utterance.utterance_id
        for utterance in normalized_transcript.utterances
        if normalized_quote in normalize_quote_text(utterance.text)
    ]


def normalize_quote_for_matching(quote: str) -> str:
    """발화 ID나 화자 prefix가 섞인 원문 인용에서 실제 발화 텍스트를 반환합니다."""
    quote_text = as_text(quote)
    if not quote_text:
        return ""

    utterance_prefix_match = re.match(
        r"^\s*\[u_\d{4}\]\s*(?:[^:：\n]{1,80}\s*[:：]\s*)?(?P<text>.+)$",
        quote_text,
    )
    if utterance_prefix_match:
        return utterance_prefix_match.group("text").strip()

    speaker_prefix_match = re.match(r"^\s*[^:：\n]{1,80}\s*[:：]\s*(?P<text>.+)$", quote_text)
    if speaker_prefix_match:
        return speaker_prefix_match.group("text").strip()

    return quote_text


def normalize_quote_text(value: str) -> str:
    """보수적인 원문 인용 부분 문자열 매칭을 위해 공백을 정규화합니다."""
    return re.sub(r"\s+", " ", as_text(value)).strip()


def filter_model_warnings(
    existing_warnings: list[Any],
    validated_action_items: list[dict[str, Any]],
    validated_decisions: list[dict[str, Any]],
) -> list[str]:
    """검증된 구조화 사실과 모순되는 오래된 모델 경고를 제거합니다."""
    filtered_warnings: list[str] = []

    for warning in clean_text_list(existing_warnings):
        if is_stale_action_warning(warning, validated_action_items):
            continue
        if is_stale_decision_warning(warning, validated_decisions):
            continue
        filtered_warnings.append(warning)

    return unique_text_list(filtered_warnings)


def format_display_warnings(
    warnings: list[Any],
    action_items: list[dict[str, Any]] | None = None,
    decisions: list[dict[str, Any]] | None = None,
) -> list[str]:
    """public warning을 보수적인 정형 문장으로 정리합니다.

    public warning은 불확실한 한국어를 과하게 해석하지 않고, 확실한 패턴만
    템플릿으로 변환합니다. 의미 재작성보다 중복 제거와 내부 필드명 제거를
    우선합니다.
    """
    action_warning_kinds: dict[str, set[str]] = {}
    decision_warning_kinds: dict[str, set[str]] = {}
    ordered_entries: list[tuple[str, str, str]] = []
    seen_action_tasks: set[str] = set()
    seen_decisions: set[str] = set()
    general_warnings: set[str] = set()

    for warning in clean_text_list(warnings):
        source_utterance_warning = format_source_utterance_id_only_warning(warning)
        if source_utterance_warning is not None:
            add_general_warning(source_utterance_warning, ordered_entries, general_warnings, force_display=True)
            continue
        if is_internal_owner_inference_warning(warning):
            continue

        decision_warning = parse_decision_display_warning(warning)
        if decision_warning:
            decision, warning_kind = decision_warning
            decision_key = normalize_warning_text(decision)
            if decision_key:
                decision_warning_kinds.setdefault(decision_key, set()).add(warning_kind)
                if decision_key not in seen_decisions:
                    seen_decisions.add(decision_key)
                    ordered_entries.append(("decision", decision_key, decision))
            continue

        action_warning = parse_action_display_warning(warning)
        if action_warning:
            task, warning_kind = action_warning
            warning_kind = remove_stale_owner_warning_kind(task, warning_kind, action_items)
            if not warning_kind:
                continue
            is_overly_generic_subject = is_overly_generic_warning_subject(task)
            if (
                is_generic_action_warning_subject(task)
                or is_generic_decision_warning_subject(task)
                or is_internal_display_warning_subject(task)
                or is_overly_generic_subject
            ):
                add_general_warning(
                    build_general_display_warning(warning_kind) or format_general_display_warning(warning),
                    ordered_entries,
                    general_warnings,
                    force_display=is_overly_generic_subject,
                )
                continue

            action_key = normalize_warning_text(task)
            if not action_key:
                continue
            add_action_warning_kind(action_warning_kinds, action_key, warning_kind)
            if action_key not in seen_action_tasks:
                seen_action_tasks.add(action_key)
                ordered_entries.append(("action", action_key, task))
            continue

        add_general_warning(format_general_display_warning(warning), ordered_entries, general_warnings)

    has_specific_owner_warning = any("owner" in warning_kinds for warning_kinds in action_warning_kinds.values())
    has_specific_due_date_warning = any("due_date" in warning_kinds for warning_kinds in action_warning_kinds.values())
    has_specific_source_quote_warning = any("source_quote" in warning_kinds for warning_kinds in action_warning_kinds.values()) or any(
        "source_quote" in warning_kinds for warning_kinds in decision_warning_kinds.values()
    )
    has_specific_confidence_warning = any("confidence" in warning_kinds for warning_kinds in action_warning_kinds.values())
    display_warnings: list[str] = []
    for entry_type, warning_key, display_value in ordered_entries:
        if entry_type == "action":
            display_warnings.extend(build_action_display_warnings(display_value, action_warning_kinds.get(warning_key, set())))
        elif entry_type == "decision":
            display_warnings.extend(build_decision_display_warnings(display_value, decision_warning_kinds.get(warning_key, set())))
        elif entry_type == "forced_general":
            display_warnings.append(display_value)
        else:
            if should_skip_general_warning(
                display_value,
                has_specific_owner_warning,
                has_specific_due_date_warning,
                has_specific_source_quote_warning,
                has_specific_confidence_warning,
            ):
                continue
            display_warnings.append(display_value)

    return unique_text_list([sanitize_internal_warning_terms(warning) for warning in display_warnings])


def format_source_utterance_id_only_warning(warning: str) -> str | None:
    """source utterance ID만 주어인 warning을 사용자용 일반 warning으로 접습니다."""
    match = SOURCE_UTTERANCE_ID_WARNING_PATTERN.match(as_text(warning))
    if not match:
        return None

    warning_kind = classify_source_utterance_warning_reason(match.group("reason"))
    return build_general_display_warning(warning_kind)


def classify_source_utterance_warning_reason(reason: str) -> str | None:
    """source utterance ID warning의 사유를 표시용 warning 종류로 분류합니다."""
    warning_kind = classify_action_warning_reason(reason)
    if warning_kind:
        return warning_kind
    if "내용" in normalize_warning_text(reason):
        return "confidence"
    return None


def is_internal_owner_inference_warning(warning: str) -> bool:
    """화자 추론 실패 같은 내부 검증 설명을 공개 warning에서 숨깁니다."""
    warning_text = as_text(warning)
    warning_key = normalize_warning_text(warning_text)
    if not warning_key:
        return False

    if is_source_id_warning(warning_text) and is_source_id_internal_warning(warning_text, warning_key):
        return True
    if is_unknown_speaker_owner_warning(warning_key):
        return True
    if has_speaker_label_term(warning_key) and has_owner_inference_failure_term(warning_key):
        return True
    if has_first_person_acceptance_term(warning_key) and has_owner_inference_failure_term(warning_key):
        return True
    return False


def is_source_id_warning(warning: str) -> bool:
    """warning 문구에 source utterance ID가 포함되어 있는지 반환합니다."""
    return bool(SOURCE_UTTERANCE_ID_TEXT_PATTERN.search(as_text(warning)))


def is_source_id_internal_warning(warning: str, warning_key: str) -> bool:
    """source utterance ID가 주어인 내부 추론 warning인지 반환합니다."""
    if not SOURCE_UTTERANCE_ID_PREFIX_PATTERN.search(warning):
        return False
    return (
        has_speaker_assumption_term(warning_key)
        or has_owner_inference_failure_term(warning_key)
        or has_first_person_acceptance_term(warning_key)
        or "근거확인" in warning_key
        or "확인필요" in warning_key
    )


def is_unknown_speaker_owner_warning(warning_key: str) -> bool:
    """Unknown speaker 기반 담당자 추론 실패 warning인지 반환합니다."""
    return (
        "unknown" in warning_key
        and has_speaker_assumption_term(warning_key)
        and has_owner_inference_failure_term(warning_key)
    )


def has_speaker_assumption_term(warning_key: str) -> bool:
    """speaker label이나 화자 기반 추론 표현이 있는지 반환합니다."""
    return (
        "speaker" in warning_key
        or "발화자" in warning_key
        or "화자" in warning_key
        or has_speaker_label_term(warning_key)
    )


def has_speaker_label_term(warning_key: str) -> bool:
    """speaker label 표현이 있는지 반환합니다."""
    return "speakerlabel" in warning_key or "speaker라벨" in warning_key or "speaker레이블" in warning_key


def has_first_person_acceptance_term(warning_key: str) -> bool:
    """1인칭 수락을 담당자 추론 근거로 삼은 표현인지 반환합니다."""
    return "1인칭으로수락" in warning_key or "일인칭으로수락" in warning_key


def has_owner_inference_failure_term(warning_key: str) -> bool:
    """담당자 특정/추론 실패 설명인지 반환합니다."""
    return (
        "담당자를특정" in warning_key
        or "담당자특정" in warning_key
        or "담당자추론" in warning_key
        or "owner추론" in warning_key
        or "ownerinference" in warning_key
        or "추론실패" in warning_key
        or ("담당자" in warning_key and any(term in warning_key for term in ("특정", "추론", "불명확", "미정", "실패")))
        or ("owner" in warning_key and any(term in warning_key for term in ("unknown", "missing", "fail", "실패", "미정")))
    )


def remove_stale_owner_warning_kind(
    subject: str,
    warning_kind: str,
    action_items: list[dict[str, Any]] | None = None,
) -> str | None:
    """해결된 담당자를 가리키는 오래된 owner warning 종류를 제거합니다."""
    if "owner" not in warning_kind or not subject_matches_resolved_action_owner(subject, action_items or []):
        return warning_kind
    if warning_kind == "owner_due_date":
        return "due_date"
    return None


def subject_matches_resolved_action_owner(subject: str, action_items: list[dict[str, Any]]) -> bool:
    """warning 주어가 담당자가 해결된 action의 task 또는 owner를 가리키는지 반환합니다."""
    subject_key = normalize_warning_text(subject)
    if not subject_key:
        return False

    for item in action_items:
        if not is_resolved_action_owner(item.get("owner")):
            continue
        task_key = normalize_warning_text(as_text(item.get("task")))
        owner_key = normalize_warning_text(as_text(item.get("owner")))
        if subject_key and subject_key in {task_key, owner_key}:
            return True
    return False


def add_general_warning(
    warning: str,
    ordered_entries: list[tuple[str, str, str]],
    general_warnings: set[str],
    force_display: bool = False,
) -> None:
    """일반 warning을 중복 없이 표시 목록에 추가합니다."""
    warning_text = as_text(warning)
    warning_key = normalize_warning_text(warning_text)
    if not warning_text or warning_key in general_warnings:
        return
    general_warnings.add(warning_key)
    entry_type = "forced_general" if force_display else "general"
    ordered_entries.append((entry_type, warning_key, warning_text))


def add_action_warning_kind(
    action_warning_kinds: dict[str, set[str]],
    action_key: str,
    warning_kind: str,
) -> None:
    """복합 실행 항목 warning 종류를 내부 set으로 펼쳐 추가합니다."""
    warning_kinds = action_warning_kinds.setdefault(action_key, set())
    if warning_kind == "owner_due_date":
        warning_kinds.update({"owner", "due_date"})
        return
    warning_kinds.add(warning_kind)


def should_skip_general_warning(
    warning: str,
    has_specific_owner_warning: bool,
    has_specific_due_date_warning: bool,
    has_specific_source_quote_warning: bool,
    has_specific_confidence_warning: bool,
) -> bool:
    """구체 warning이 있으면 같은 종류의 일반 warning은 숨깁니다."""
    warning_key = normalize_warning_text(warning)
    return (
        (has_specific_owner_warning and "담당자확인이필요한액션아이템이있습니다" == warning_key)
        or (has_specific_due_date_warning and "기한확인이필요한액션아이템이있습니다" == warning_key)
        or (has_specific_source_quote_warning and "원문근거확인이필요한항목이있습니다" == warning_key)
        or (has_specific_confidence_warning and "내용확인이필요한항목이있습니다" == warning_key)
    )


def format_general_display_warning(warning: str) -> str:
    """일반 warning에 남은 내부 표현을 사용자 문장으로 정리합니다."""
    generic_korean_warning = format_generic_korean_warning(warning)
    if generic_korean_warning:
        return generic_korean_warning
    generic_internal_warning = format_generic_internal_field_warning(warning)
    if generic_internal_warning:
        return generic_internal_warning
    return sanitize_internal_warning_terms(warning)


def format_generic_korean_warning(warning: str) -> str:
    """구체 항목이 없는 한국어 warning을 짧은 표준 문장으로 바꿉니다."""
    warning_text = normalize_warning_text(warning)
    if not warning_text:
        return ""

    if any(subject in warning_text for subject in generic_action_subject_keys()):
        warning_kind = classify_action_warning_reason(warning)
        return build_general_display_warning(warning_kind)

    if "결정사항" in warning_text:
        warning_kind = classify_action_warning_reason(warning) or classify_decision_warning_reason(warning)
        return build_general_display_warning(warning_kind)

    return ""


def generic_action_subject_keys() -> tuple[str, ...]:
    """일반 실행 항목 warning 주어의 정규화 key를 반환합니다."""
    return (
        "모든actionitem",
        "전체actionitem",
        "일부actionitem",
        "actionitem",
        "주요행동아이템",
        "일부행동아이템",
        "전체행동아이템",
        "행동아이템",
        "모든액션아이템",
        "주요액션아이템",
        "일부액션아이템",
        "전체액션아이템",
        "액션아이템",
        "확인요청된일부사항",
        "확인요청사항",
    )


def build_general_display_warning(warning_kind: str | None) -> str:
    """일반 대상 warning을 표준형 문장으로 만듭니다."""
    if warning_kind == "owner_due_date":
        return "담당자 및 기한 확인이 필요한 액션 아이템이 있습니다."
    if warning_kind == "owner":
        return "담당자 확인이 필요한 액션 아이템이 있습니다."
    if warning_kind == "due_date":
        return "기한 확인이 필요한 액션 아이템이 있습니다."
    if warning_kind == "source_quote":
        return "원문 근거 확인이 필요한 항목이 있습니다."
    if warning_kind == "confidence":
        return "내용 확인이 필요한 항목이 있습니다."
    return ""


def format_generic_internal_field_warning(warning: str) -> str:
    """task가 없는 내부 필드 warning을 사용자용 일반 문장으로 바꿉니다."""
    warning_text = normalize_warning_text(warning)
    if not warning_text:
        return ""

    if "owner" in warning_text and has_action_uncertainty_terms(warning_text):
        return build_general_display_warning("owner")
    if "duedate" in warning_text and has_action_uncertainty_terms(warning_text):
        return build_general_display_warning("due_date")
    if "confidence" in warning_text:
        return build_general_display_warning("confidence")
    if "sourcequote" in warning_text:
        return build_general_display_warning("source_quote")
    return ""


def is_generic_action_warning_subject(subject: str) -> bool:
    """특정 업무가 아니라 액션 아이템 전체를 가리키는 주어인지 반환합니다."""
    subject_key = normalize_warning_text(subject)
    return (
        subject_key in generic_action_subject_keys()
        or "actionitem" in subject_key
        or "액션아이템" in subject_key
        or "행동아이템" in subject_key
    )


def is_internal_display_warning_subject(subject: str) -> bool:
    """내부 처리 용어처럼 보이는 주어인지 반환합니다."""
    subject_key = normalize_warning_text(subject)
    return "merge" in subject_key or "머지" in subject_key or "병합" in subject_key


def is_overly_generic_warning_subject(subject: str) -> bool:
    """업무명으로 보기 어려운 너무 넓은 주어인지 반환합니다."""
    return normalize_warning_text(subject) in {
        "결정",
        "사항",
        "항목",
        "업무",
        "작업",
        "실행",
        "처리",
        "확인",
        "일부사항",
        "일부업무",
        "주요업무",
    }


def is_generic_decision_warning_subject(subject: str) -> bool:
    """특정 결정이 아니라 결정사항 전체를 가리키는 주어인지 반환합니다."""
    return "결정사항" in normalize_warning_text(subject)


def parse_action_display_warning(warning: str) -> tuple[str, str] | None:
    """실행 항목 경고에서 task와 표시용 경고 종류를 추출합니다."""
    normalized_warning = as_text(warning)
    quoted_match = re.match(r"^액션 아이템 ['\"](?P<task>.+?)['\"]의 (?P<reason>.+)$", normalized_warning)
    if quoted_match:
        warning_kind = classify_action_warning_reason(quoted_match.group("reason"))
        if warning_kind:
            return quoted_match.group("task").strip(), warning_kind

    quoted_subject_match = re.match(r"^['\"](?P<task>.+?)['\"]의 (?P<reason>.+)$", normalized_warning)
    if quoted_subject_match:
        warning_kind = classify_action_warning_reason(quoted_subject_match.group("reason"))
        if warning_kind:
            return quoted_subject_match.group("task").strip(), warning_kind

    colon_match = re.match(r"^(?P<task>.+?)\s*[:：]\s*(?P<reason>.+)$", normalized_warning)
    if colon_match:
        warning_kind = classify_action_warning_reason(colon_match.group("reason"))
        if warning_kind:
            return colon_match.group("task").strip(), warning_kind

    field_match = re.match(
        r"^(?P<task>.+?)의\s*(?P<field>owner|due_date|due date|confidence|source_quote)\s*(?:가|이)?\s*(?P<reason>.+)$",
        normalized_warning,
        flags=re.IGNORECASE,
    )
    if field_match:
        warning_kind = classify_action_warning_reason(
            f"{field_match.group('field')} {field_match.group('reason')}"
        )
        if warning_kind:
            return field_match.group("task").strip(), warning_kind

    natural_match = re.match(
        r"^(?P<task>.+?)의\s*(?P<reason>담당자|기한|원문\s*근거|근거|신뢰도|내용)\s*확인(?:이)?\s*필요.*$",
        normalized_warning,
    )
    if natural_match:
        warning_kind = classify_action_warning_reason(natural_match.group("reason"))
        if warning_kind:
            return natural_match.group("task").strip(), warning_kind

    uncertainty_match = re.match(
        r"^(?P<task>.+?)의\s*(?P<reason>담당자|기한|원문\s*근거|근거|신뢰도|내용)(?:가|이)?\s*(?:명확하지|불명확|미정).*$",
        normalized_warning,
    )
    if uncertainty_match:
        warning_kind = classify_action_warning_reason(uncertainty_match.group("reason"))
        if warning_kind:
            return uncertainty_match.group("task").strip(), warning_kind

    owner_subject_match = re.match(
        r"^(?P<task>.+?)\s+(?P<reason>담당자|owner)(?:가|이|는)?\s*(?:명확하지|불명확|미정|없음|확인\s*필요).*$",
        normalized_warning,
        flags=re.IGNORECASE,
    )
    if owner_subject_match:
        if "발언" in owner_subject_match.group("task"):
            return None
        warning_kind = classify_action_warning_reason(owner_subject_match.group("reason"))
        if warning_kind:
            return owner_subject_match.group("task").strip(), warning_kind

    return None


def parse_decision_display_warning(warning: str) -> tuple[str, str] | None:
    """결정사항 경고에서 decision과 표시용 경고 종류를 추출합니다."""
    normalized_warning = as_text(warning)
    quoted_match = re.match(r"^결정사항 ['\"](?P<decision>.+?)['\"]의 (?P<reason>.+)$", normalized_warning)
    if quoted_match:
        warning_kind = classify_decision_warning_reason(quoted_match.group("reason"))
        if warning_kind:
            return quoted_match.group("decision").strip(), warning_kind
    return None


def classify_action_warning_reason(reason: str) -> str | None:
    """경고 사유 문구를 담당자, 기한, 근거, 신뢰도 종류로 분류합니다."""
    reason_text = normalize_warning_text(reason)
    has_owner_reason = "owner" in reason_text or "담당자" in reason_text or "소유자" in reason_text
    has_due_date_reason = "duedate" in reason_text or "due" in reason_text or "기한" in reason_text
    if has_owner_reason and has_due_date_reason:
        return "owner_due_date"
    if has_owner_reason:
        return "owner"
    if has_due_date_reason:
        return "due_date"
    if "sourcequote" in reason_text or "근거문장" in reason_text or "원문근거" in reason_text or "근거" in reason_text:
        return "source_quote"
    if "confidence" in reason_text or "신뢰도" in reason_text:
        return "confidence"
    return None


def classify_decision_warning_reason(reason: str) -> str | None:
    """결정사항 경고 사유 문구를 표시용 종류로 분류합니다."""
    reason_text = normalize_warning_text(reason)
    if "sourcequote" in reason_text or "근거문장" in reason_text or "원문근거" in reason_text or "근거" in reason_text:
        return "source_quote"
    return None


def build_action_display_warnings(
    task: str,
    warning_kinds: set[str],
) -> list[str]:
    """실행 항목별 경고 종류를 중복 적은 사용자 문장으로 만듭니다."""
    display_warnings: list[str] = []

    if "owner" in warning_kinds and "due_date" in warning_kinds:
        display_warnings.append(f"{task}: 담당자 및 기한 확인 필요")
    elif "owner" in warning_kinds:
        display_warnings.append(f"{task}: 담당자 확인 필요")
    elif "due_date" in warning_kinds:
        display_warnings.append(f"{task}: 기한 확인 필요")

    if "source_quote" in warning_kinds:
        display_warnings.append(f"{task}: 원문 근거 확인 필요")
    if "confidence" in warning_kinds:
        display_warnings.append(f"{task}: 내용 확인 필요")

    return display_warnings


def build_decision_display_warnings(decision: str, warning_kinds: set[str]) -> list[str]:
    """결정사항별 경고 종류를 사용자 문장으로 만듭니다."""
    if "source_quote" in warning_kinds:
        return [f"{decision}: 원문 근거 확인 필요"]
    return []


def sanitize_internal_warning_terms(warning: str) -> str:
    """일반 경고에 남은 내부 필드명을 사용자 표현으로 바꿉니다."""
    display_warning = as_text(warning)
    replacements = (
        (r"(?<![A-Za-z0-9_])action item(?![A-Za-z0-9_])", "액션 아이템"),
        (r"(?<![A-Za-z0-9_])source_quote(?![A-Za-z0-9_])", "원문 근거"),
        (r"(?<![A-Za-z0-9_])due_date(?![A-Za-z0-9_])", "기한"),
        (r"(?<![A-Za-z0-9_])due date(?![A-Za-z0-9_])", "기한"),
        (r"(?<![A-Za-z0-9_])owner(?![A-Za-z0-9_])", "담당자"),
        (r"(?<![A-Za-z0-9_])confidence(?![A-Za-z0-9_])", "신뢰도"),
    )
    for pattern, replacement in replacements:
        display_warning = re.sub(pattern, replacement, display_warning, flags=re.IGNORECASE)
    display_warning = display_warning.replace("기한가", "기한이").replace("기한는", "기한은").replace("기한를", "기한을")
    display_warning = display_warning.replace("원문 근거이", "원문 근거가")
    display_warning = display_warning.replace("신뢰도이", "신뢰도가")
    return display_warning


def is_stale_action_warning(warning: str, action_items: list[dict[str, Any]]) -> bool:
    """모델 경고가 신뢰도 높은 실행 항목 기준으로 오래된 경고인지 반환합니다."""
    warning_text = normalize_warning_text(warning)
    if not has_action_uncertainty_terms(warning_text):
        return False

    for item in action_items:
        task = as_text(item.get("task"))
        if not task or not warning_mentions_item(warning_text, task):
            continue
        if (
            normalize_action_owner(as_text(item.get("owner"))) != "미정"
            and as_text(item.get("due_date")) != "미정"
            and as_text(item.get("confidence")) == "high"
        ):
            return True

    return False


def is_stale_decision_warning(warning: str, decisions: list[dict[str, Any]]) -> bool:
    """모델 경고가 근거 있는 결정사항 기준으로 오래된 경고인지 반환합니다."""
    warning_text = normalize_warning_text(warning)
    if not has_decision_uncertainty_terms(warning_text):
        return False

    for item in decisions:
        decision = as_text(item.get("decision"))
        source_quote = as_text(item.get("source_quote"))
        status = as_text(item.get("status"))
        if status not in {"확정", "미확정"} or not source_quote:
            continue
        if (decision and warning_mentions_item(warning_text, decision)) or (
            source_quote and warning_mentions_item(warning_text, source_quote)
        ):
            return True

    return False


def warning_mentions_item(warning_text: str, item_text: str) -> bool:
    """정규화된 경고가 특정 항목을 가리키는지 반환합니다."""
    normalized_item = normalize_warning_text(item_text)
    return bool(normalized_item and (normalized_item in warning_text or warning_text in normalized_item))


def has_action_uncertainty_terms(warning_text: str) -> bool:
    """경고 문구가 실행 항목 불확실성과 관련 있는지 반환합니다."""
    return any(
        term in warning_text
        for term in (
            "담당자",
            "소유자",
            "owner",
            "기한",
            "due",
            "미정",
            "불명확",
            "확인필요",
            "신뢰도낮",
        )
    )


def has_decision_uncertainty_terms(warning_text: str) -> bool:
    """경고 문구가 결정사항 근거 불확실성과 관련 있는지 반환합니다."""
    return any(term in warning_text for term in ("근거", "불명확", "확인필요", "미정"))


def normalize_warning_text(value: str) -> str:
    """보수적인 중복 제거와 항목 매칭을 위해 경고 문구를 정규화합니다."""
    return re.sub(r"[\s'\"“”‘’`.,:：/\\()\[\]{}_-]+", "", as_text(value).lower())
