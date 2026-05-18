"""chunk별 구조화 결과를 단순 병합하는 파이썬 전용 helper입니다."""

from __future__ import annotations

import re
from typing import Any


def merge_structures(structures: list[dict[str, Any]]) -> dict[str, Any]:
    """여러 structure dict를 기존 structure shape로 병합합니다."""
    summary_facts: list[Any] = []
    decisions: list[dict[str, Any]] = []
    action_items: list[dict[str, Any]] = []
    speaker_highlights: list[Any] = []
    warnings: list[Any] = []

    for structure in structures:
        if not isinstance(structure, dict):
            continue
        summary_facts.extend(as_list(structure.get("summary_facts")))
        decisions.extend(item for item in as_list(structure.get("decisions")) if isinstance(item, dict))
        action_items.extend(item for item in as_list(structure.get("action_items")) if isinstance(item, dict))
        speaker_highlights.extend(as_list(structure.get("speaker_highlights")))
        warnings.extend(as_list(structure.get("warnings")))

    return {
        "summary_facts": unique_text_list(summary_facts),
        "decisions": merge_decisions(decisions),
        "action_items": merge_action_items(action_items),
        "speaker_highlights": unique_text_list(speaker_highlights),
        "warnings": unique_text_list(warnings),
    }


def merge_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """decision과 status 기준으로 결정사항 중복을 제거합니다."""
    merged_decisions: list[dict[str, Any]] = []
    key_indexes: dict[tuple[str, str], int] = {}

    for decision_item in decisions:
        decision = as_text(decision_item.get("decision"))
        if not decision:
            continue
        status = as_text(decision_item.get("status"))
        merge_key = (normalize_merge_key(decision), normalize_merge_key(status))
        candidate = dict(decision_item)
        candidate["decision"] = decision
        candidate["status"] = status
        candidate["source_quote"] = as_text(candidate.get("source_quote"))

        if merge_key not in key_indexes:
            key_indexes[merge_key] = len(merged_decisions)
            merged_decisions.append(candidate)
            continue

        existing_index = key_indexes[merge_key]
        merged_decisions[existing_index] = prefer_item_with_source_quote(merged_decisions[existing_index], candidate)

    return merged_decisions


def merge_action_items(action_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """task, owner, due_date와 보수적인 업무 도메인 기준으로 실행 항목 중복을 제거합니다."""
    merged_action_items: list[dict[str, Any]] = []

    for action_item in action_items:
        task = as_text(action_item.get("task"))
        if not task:
            continue
        owner = as_text(action_item.get("owner"))
        source_quote = as_text(action_item.get("source_quote"))
        due_date = normalize_due_date_for_merge(as_text(action_item.get("due_date")), source_quote)
        merge_key = (
            normalize_merge_key(task),
            normalize_merge_key(owner),
            normalize_merge_key(due_date),
        )
        candidate = dict(action_item)
        candidate["task"] = task
        candidate["owner"] = owner
        candidate["due_date"] = due_date
        candidate["confidence"] = merge_confidence(as_text(candidate.get("confidence")), "")
        candidate["source_quote"] = source_quote

        existing_index = find_mergeable_action_item_index(merged_action_items, candidate, merge_key)
        if existing_index is None:
            merged_action_items.append(candidate)
        else:
            merged_action_items[existing_index] = merge_action_item_pair(merged_action_items[existing_index], candidate)

    return merged_action_items


def find_mergeable_action_item_index(
    action_items: list[dict[str, Any]],
    candidate: dict[str, Any],
    candidate_key: tuple[str, str, str],
) -> int | None:
    """기존 action_items 중 candidate와 병합 가능한 항목 위치를 반환합니다."""
    for index, existing in enumerate(action_items):
        existing_key = (
            normalize_merge_key(existing.get("task")),
            normalize_merge_key(existing.get("owner")),
            normalize_merge_key(existing.get("due_date")),
        )
        if existing_key == candidate_key or should_merge_action_items(existing, candidate):
            return index
    return None


def should_merge_action_items(existing: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """표현이 달라도 같은 업무로 볼 수 있는 보수적인 action item인지 반환합니다."""
    if normalize_merge_key(existing.get("owner")) != normalize_merge_key(candidate.get("owner")):
        return False
    if not due_dates_are_mergeable(existing.get("due_date"), candidate.get("due_date")):
        return False

    existing_domain = action_domain_key(existing)
    candidate_domain = action_domain_key(candidate)
    if existing_domain and existing_domain == candidate_domain:
        return True

    existing_task = normalize_compact_key(existing.get("task"))
    candidate_task = normalize_compact_key(candidate.get("task"))
    return bool(existing_task and candidate_task and (existing_task in candidate_task or candidate_task in existing_task))


def merge_action_item_pair(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """두 중복 action item의 더 구체적인 필드를 보존해 하나로 합칩니다."""
    preferred = prefer_item_with_source_quote(existing, candidate)
    other = candidate if preferred is existing else existing
    merged = dict(preferred)
    merged["confidence"] = merge_confidence(existing.get("confidence"), candidate.get("confidence"))
    merged["due_date"] = prefer_specific_due_date(existing.get("due_date"), candidate.get("due_date"))
    if not as_text(merged.get("source_quote")):
        merged["source_quote"] = as_text(other.get("source_quote"))
    source_utterance_ids = merge_source_utterance_ids(existing.get("source_utterance_ids"), candidate.get("source_utterance_ids"))
    if source_utterance_ids or "source_utterance_ids" in existing or "source_utterance_ids" in candidate:
        merged["source_utterance_ids"] = source_utterance_ids
    return merged


def prefer_item_with_source_quote(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """source_quote가 있는 항목을 우선하되 기존 순서는 유지합니다."""
    existing_quote = as_text(existing.get("source_quote"))
    candidate_quote = as_text(candidate.get("source_quote"))
    if not existing_quote and candidate_quote:
        return candidate
    return existing


def merge_confidence(left: Any, right: Any) -> str:
    """중복 실행 항목 중 하나라도 high이면 high로 병합합니다."""
    if as_text(left) == "high" or as_text(right) == "high":
        return "high"
    if as_text(left) == "low" or as_text(right) == "low":
        return "low"
    return as_text(left) or as_text(right)


def due_dates_are_mergeable(left: Any, right: Any) -> bool:
    """같거나 한쪽이 더 구체적인 기한이면 병합 가능하다고 봅니다."""
    left_key = normalize_compact_key(left)
    right_key = normalize_compact_key(right)
    if left_key == right_key:
        return True
    if left_key in {"", "미정"} or right_key in {"", "미정"}:
        return True
    return left_key in right_key or right_key in left_key


def prefer_specific_due_date(left: Any, right: Any) -> str:
    """두 기한 중 더 구체적인 원문 표현을 고릅니다."""
    left_text = as_text(left)
    right_text = as_text(right)
    left_key = normalize_compact_key(left_text)
    right_key = normalize_compact_key(right_text)
    if left_key in {"", "미정"}:
        return right_text
    if right_key in {"", "미정"}:
        return left_text
    if left_key != right_key and left_key in right_key:
        return right_text
    return left_text


def normalize_due_date_for_merge(due_date: str, source_quote: str) -> str:
    """병합 전 ISO로 변환된 기한보다 원문 상대 기한을 우선합니다."""
    due_date_text = as_text(due_date)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?", due_date_text):
        return due_date_text
    return extract_relative_due_date(source_quote) or due_date_text


def extract_relative_due_date(source_quote: str) -> str:
    """원문 근거 문장에서 상대 기한 표현을 추출합니다."""
    weekdays = "월요일|화요일|수요일|목요일|금요일|토요일|일요일"
    pattern = re.compile(
        rf"(?P<due>"
        rf"(?:오늘|내일)(?:\s*(?:중|오전|오후))?(?:\s*\d{{1,2}}시)?"
        rf"|다음\s*주\s*(?:{weekdays})(?:\s*(?:오전|오후))?(?:\s*\d{{1,2}}시)?"
        rf"|(?:{weekdays})(?:\s*(?:오전|오후))?(?:\s*\d{{1,2}}시)?"
        rf")\s*(?:까지|까지입니다|로|에)?"
    )
    match = pattern.search(as_text(source_quote))
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group("due")).strip()


def merge_source_utterance_ids(left: Any, right: Any) -> list[str]:
    """중복 action item의 내부 utterance 근거 ID를 순서대로 합칩니다."""
    utterance_ids: list[str] = []
    seen_ids: set[str] = set()
    for value in (left, right):
        if not isinstance(value, list):
            continue
        for item in value:
            utterance_id = as_text(item)
            if not utterance_id or utterance_id in seen_ids:
                continue
            seen_ids.add(utterance_id)
            utterance_ids.append(utterance_id)
    return utterance_ids


def unique_text_list(values: list[Any]) -> list[str]:
    """정규화한 텍스트 기준으로 중복을 제거하고 원래 순서를 유지합니다."""
    unique_values: list[str] = []
    seen_keys: set[str] = set()

    for value in values:
        text = as_text(value)
        if not text:
            continue
        merge_key = normalize_merge_key(text)
        if merge_key in seen_keys:
            continue
        seen_keys.add(merge_key)
        unique_values.append(text)

    return unique_values


def normalize_merge_key(value: Any) -> str:
    """병합용 key를 만들기 위해 공백과 대소문자만 보수적으로 정규화합니다."""
    return re.sub(r"\s+", " ", as_text(value)).strip().casefold()


def normalize_compact_key(value: Any) -> str:
    """업무 도메인 비교를 위해 공백과 일부 기호를 제거한 key를 반환합니다."""
    return re.sub(r"[\s'\"“”‘’`.,:：/\\()\[\]{}_-]+", "", as_text(value).lower())


def action_domain_key(action_item: dict[str, Any]) -> str:
    """긴 PoC 회의에서 반복 표현이 잦은 업무 도메인을 보수적으로 분류합니다."""
    text = normalize_compact_key(f"{as_text(action_item.get('task'))} {as_text(action_item.get('source_quote'))}")
    if "재시도" in text and ("2회" in text or "이티엘" in text or "etl" in text):
        return "etl_retry_count"
    if ("campaignid" in text or "캠페인" in text) and ("null" in text or "기타캠페인" in text or "매핑" in text):
        return "campaign_id_null_mapping"
    if "api" in text and ("필드매핑표" in text or "샘플응답" in text or "샘플재확인" in text):
        return "api_field_mapping_and_sample"
    if "데이터정합성" in text and ("답변문구" in text or "쿼리" in text):
        return "data_consistency_answer"
    return ""


def as_list(value: Any) -> list[Any]:
    """list 값만 병합 대상으로 사용합니다."""
    return value if isinstance(value, list) else []


def as_text(value: Any) -> str:
    """빈 값일 수 있는 단일 값을 표시 가능한 문자열로 변환합니다."""
    if value is None:
        return ""
    return str(value).strip()
