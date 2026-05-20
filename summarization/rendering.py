"""회의록 Markdown 렌더링과 공개 요약 결과 매핑을 담당합니다."""

from __future__ import annotations

import re
from typing import Any

from summarization.models import SummaryResult
from summarization.policies import normalize_meeting_type
from summarization.validation import (
    as_text,
    clean_text_list,
    ensure_structure_shape,
    format_display_warnings,
    normalize_action_owner,
)


DISCUSSION_NOTE_PREFIX = "논의 메모:"
GENERATED_MINUTES_TITLE_PATTERN = re.compile(r"^\s*#{1,2}\s*(?:전체\s+)?회의록\s*$")
MARKDOWN_HORIZONTAL_RULE_PATTERN = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
MARKDOWN_STRIKETHROUGH_PATTERN = re.compile(r"~~.*?~~")


def render_output(structure: dict[str, Any], minutes_text: str, meeting_type: str = "general") -> str:
    """구조화 사실과 자연어 회의록을 결합한 최종 Markdown을 만듭니다."""
    normalized_structure = ensure_structure_shape(structure)
    resolved_meeting_type = normalize_meeting_type(meeting_type)
    summary_facts, discussion_notes = split_discussion_notes(normalized_structure.summary_facts)
    kept_lines: list[str] = []
    skipping_action_items = False

    for line in minutes_text.splitlines():
        if re.match(rf"^\s*#+\s*(?:[^\w\s]+\s*)?{re.escape('액션 아이템')}\s*$", line.strip()):
            skipping_action_items = True
            continue
        if skipping_action_items and re.match(r"^\s*#+\s+\S+", line.strip()):
            skipping_action_items = False
        if not skipping_action_items:
            kept_lines.append(line)

    deduplicated_minutes = normalize_generated_minutes_markdown("\n".join(kept_lines))
    sections = []

    summary_title = get_summary_section_title(resolved_meeting_type)
    action_title = get_action_section_title(resolved_meeting_type)

    summary_lines = [f"- {fact}" for fact in clean_text_list(summary_facts)[:3]]
    sections.append(f"{summary_title}\n" + ("\n".join(summary_lines) if summary_lines else "요약 없음"))

    note_lines = [f"- {note}" for note in clean_text_list(discussion_notes)]
    if note_lines:
        sections.append("## 논의 메모\n" + "\n".join(note_lines))

    action_item_lines = [action_title]
    if normalized_structure.action_items:
        for item in normalized_structure.action_items:
            action_item_lines.append(format_action_item_for_markdown(item))
    else:
        action_item_lines.append("- 없음")
    sections.append("\n".join(action_item_lines))

    sections.append(f"## 📝 전체 회의록\n{deduplicated_minutes.strip() or '회의록 없음'}")
    return "\n\n".join(section for section in sections if section.strip()).strip()


def normalize_generated_minutes_markdown(minutes_text: str) -> str:
    """모델이 생성한 회의록 Markdown의 제목/구분선/수정 artifact를 보수적으로 정리합니다."""
    lines = as_text(minutes_text).splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and GENERATED_MINUTES_TITLE_PATTERN.match(lines[0]):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)

    cleaned_lines = [line.rstrip() for line in lines if not MARKDOWN_HORIZONTAL_RULE_PATTERN.match(line)]
    cleaned_text = "\n".join(cleaned_lines).strip()
    cleaned_text = remove_markdown_strikethrough_artifacts(cleaned_text)
    return re.sub(r"\n{3,}", "\n\n", cleaned_text)


def remove_markdown_strikethrough_artifacts(markdown_text: str) -> str:
    """정상 범위 표기 물결표는 보존하고 Markdown 취소선 span만 제거합니다."""
    return MARKDOWN_STRIKETHROUGH_PATTERN.sub("", markdown_text)


def format_action_item_for_markdown(item: dict[str, Any]) -> str:
    """Markdown 액션 아이템을 task-first 형식으로 표시합니다."""
    task = as_text(item.get("task")) or "내용 미정"
    metadata = []
    owner = meaningful_action_owner(as_text(item.get("owner")))
    due_date = meaningful_action_due_date(as_text(item.get("due_date")))

    if owner:
        metadata.append(f"담당자: {owner}")
    if due_date:
        metadata.append(f"기한: {due_date}")
    if metadata:
        return f"- {task} ({' / '.join(metadata)})"
    return f"- {task}"


def meaningful_action_owner(owner: str) -> str:
    """Markdown에 표시할 의미 있는 담당자만 반환합니다."""
    normalized_owner = normalize_action_owner(owner)
    if is_unresolved_action_metadata(normalized_owner):
        return ""
    return normalized_owner


def meaningful_action_due_date(due_date: str) -> str:
    """Markdown에 표시할 의미 있는 기한만 반환합니다."""
    due_date_text = as_text(due_date)
    if is_unresolved_action_metadata(due_date_text):
        return ""
    return due_date_text


def is_unresolved_action_metadata(value: str) -> bool:
    """담당자/기한 metadata가 미해결 표시값인지 확인합니다."""
    metadata_key = re.sub(r"\s+", "", as_text(value)).lower()
    return metadata_key in {"", "미정", "확인필요", "검토필요"}


def build_summary_result(structure: dict[str, Any], minutes_text: str) -> SummaryResult:
    """내부 구조화 결과를 공개 요약 응답 형태로 변환합니다."""
    normalized_structure = ensure_structure_shape(structure)
    action_items: list[dict[str, Any]] = []
    for item in normalized_structure.action_items:
        task = as_text(item.get("task"))
        if not task:
            continue

        confidence = as_text(item.get("confidence"))
        action_items.append(
            {
                "task": task,
                "owner": normalize_action_owner(as_text(item.get("owner"))),
                "due_date": as_text(item.get("due_date")) or "미정",
                "confidence": confidence if confidence in {"high", "low"} else "low",
            }
        )

    decisions: list[dict[str, Any]] = []
    for item in normalized_structure.decisions:
        decision = as_text(item.get("decision"))
        if not decision:
            continue

        status = as_text(item.get("status"))
        decisions.append(
            {
                "decision": decision,
                "status": status if status in {"확정", "미확정"} else "미확정",
            }
        )

    return {
        "minutes": minutes_text,
        "action_items": action_items,
        "summary_facts": clean_text_list(normalized_structure.summary_facts),
        "decisions": decisions,
        "speaker_highlights": clean_text_list(normalized_structure.speaker_highlights),
        "warnings": format_display_warnings(
            normalized_structure.warnings,
            normalized_structure.action_items,
            normalized_structure.decisions,
        ),
    }


def split_discussion_notes(summary_facts: list[str]) -> tuple[list[str], list[str]]:
    """summary_facts에서 downgrade된 논의 메모를 분리합니다."""
    facts: list[str] = []
    notes: list[str] = []
    for fact in clean_text_list(summary_facts):
        if fact.startswith(DISCUSSION_NOTE_PREFIX):
            note = fact.removeprefix(DISCUSSION_NOTE_PREFIX).strip()
            if note:
                notes.append(note)
            continue
        facts.append(fact)
    return facts, notes


def get_summary_section_title(meeting_type: str) -> str:
    """회의 유형에 맞는 요약 섹션 제목을 반환합니다."""
    if meeting_type == "technical_review":
        return "## 주요 논의"
    if meeting_type == "customer_meeting":
        return "## 고객 관심사 및 검토 포인트"
    if meeting_type == "brainstorming":
        return "## 아이디어 및 논점"
    return "## 📋 빠른 요약"


def get_action_section_title(meeting_type: str) -> str:
    """회의 유형에 맞는 액션 섹션 제목을 반환합니다."""
    if meeting_type in {"technical_review", "customer_meeting", "brainstorming"}:
        return "## 액션 아이템"
    return "## ✅ 액션 아이템"
