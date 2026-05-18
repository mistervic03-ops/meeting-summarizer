"""회의 유형별 구조 추출 정책과 경량 후처리를 담당합니다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExtractionPolicy:
    """회의 유형별 구조 추출 기준입니다."""

    meeting_type: str
    action_threshold: str
    decision_threshold: str
    discussion_emphasis: str
    followup_sensitivity: str


@dataclass(frozen=True)
class PolicyApplicationResult:
    """정책 후처리 결과와 downgrade 건수를 함께 담습니다."""

    structure: dict[str, Any]
    downgraded_action_count: int = 0
    downgraded_decision_count: int = 0


MEETING_TYPES = ("execution", "customer_meeting", "technical_review", "brainstorming", "general")
MEETING_TYPE_POLICIES: dict[str, ExtractionPolicy] = {
    "execution": ExtractionPolicy(
        meeting_type="execution",
        action_threshold="aggressive",
        decision_threshold="moderate",
        discussion_emphasis="operational",
        followup_sensitivity="aggressive",
    ),
    "customer_meeting": ExtractionPolicy(
        meeting_type="customer_meeting",
        action_threshold="strict",
        decision_threshold="strict",
        discussion_emphasis="customer",
        followup_sensitivity="moderate",
    ),
    "technical_review": ExtractionPolicy(
        meeting_type="technical_review",
        action_threshold="strict",
        decision_threshold="strict",
        discussion_emphasis="technical",
        followup_sensitivity="strict",
    ),
    "brainstorming": ExtractionPolicy(
        meeting_type="brainstorming",
        action_threshold="strict",
        decision_threshold="strict",
        discussion_emphasis="ideas",
        followup_sensitivity="strict",
    ),
    "general": ExtractionPolicy(
        meeting_type="general",
        action_threshold="moderate",
        decision_threshold="moderate",
        discussion_emphasis="balanced",
        followup_sensitivity="moderate",
    ),
}

WEAK_ACTION_PATTERNS = (
    "검토해볼수있다",
    "검토해볼수있습니다",
    "논의했다",
    "논의했습니다",
    "가능성이있다",
    "가능성이있습니다",
    "방향으로본다",
    "방향으로보고",
    "소개했다",
    "소개했습니다",
    "설명했다",
    "설명했습니다",
    "살펴볼수있다",
    "살펴볼수있습니다",
)
STRONG_ACTION_PATTERNS = (
    "하겠습니다",
    "할게요",
    "해주",
    "공유해주세요",
    "반영해주세요",
    "작성하겠습니다",
    "확인하겠습니다",
    "전달하겠습니다",
    "보내겠습니다",
    "진행하겠습니다",
    "담당",
    "까지",
    "완료",
)
WEAK_DECISION_PATTERNS = (
    "논의되었다",
    "논의되었습니다",
    "언급되었다",
    "언급되었습니다",
    "가능성이언급",
    "설명했다",
    "설명했습니다",
    "공감대가있었다",
    "공감대가있었습니다",
)
STRONG_DECISION_PATTERNS = (
    "확정",
    "결정",
    "하기로했다",
    "하기로했습니다",
    "진행하기로",
    "합의",
    "승인",
    "채택",
    "유지한다",
    "적용한다",
)


def normalize_meeting_type(meeting_type: str | None = None) -> str:
    """지원하는 meeting type만 허용하고 기본값은 general로 정규화합니다."""
    normalized = (meeting_type or "general").strip().lower()
    if normalized in MEETING_TYPES:
        return normalized
    return "general"


def get_extraction_policy(meeting_type: str | None = None) -> ExtractionPolicy:
    """회의 유형에 맞는 추출 정책을 반환합니다."""
    return MEETING_TYPE_POLICIES[normalize_meeting_type(meeting_type)]


def build_policy_prompt_guidance(meeting_type: str | None = None) -> str:
    """정책 값을 프롬프트 지침 문장으로 조립합니다."""
    policy = get_extraction_policy(meeting_type)
    return "\n".join(
        [
            f"회의 유형: {policy.meeting_type}",
            "회의 유형 정책:",
            *build_action_threshold_guidance(policy),
            *build_decision_threshold_guidance(policy),
            *build_discussion_emphasis_guidance(policy),
            *build_followup_sensitivity_guidance(policy),
        ]
    )


def build_action_threshold_guidance(policy: ExtractionPolicy) -> list[str]:
    """action_threshold 값에 맞는 프롬프트 지침을 만듭니다."""
    if policy.action_threshold == "aggressive":
        return [
            "- 실행 회의입니다.",
            "- action_threshold=aggressive: action_items, owner, due_date, decisions를 적극적으로 추출하세요.",
            "- 명시적으로 맡기거나 완료하기로 한 일은 누락하지 마세요.",
        ]
    if policy.action_threshold == "strict":
        return [
            "- action_threshold=strict: 담당자, 기한, 명시적 실행 약속이 약하면 action_item으로 올리지 마세요.",
            "- 설명, 소개, 가능성, 논의 흔적은 summary_facts나 speaker_highlights에 남기세요.",
        ]
    return [
        "- 일반 회의입니다.",
        "- action_threshold=moderate: 명확한 실행 약속은 추출하되 애매한 논의는 action_item으로 올리지 마세요.",
    ]


def build_decision_threshold_guidance(policy: ExtractionPolicy) -> list[str]:
    """decision_threshold 값에 맞는 프롬프트 지침을 만듭니다."""
    if policy.decision_threshold == "strict":
        return [
            "- decision_threshold=strict: 확정, 결정, 합의처럼 강한 확인 표현이 있을 때만 decisions에 넣으세요.",
            "- 논의되었다, 가능성이 언급되었다, 설명했다, 공감대가 있었다 수준은 결정사항이 아닙니다.",
        ]
    return [
        "- decision_threshold=moderate: 명확한 결정과 미확정 논의를 구분하되, 단순 설명은 결정으로 만들지 마세요.",
    ]


def build_discussion_emphasis_guidance(policy: ExtractionPolicy) -> list[str]:
    """discussion_emphasis 값에 맞는 프롬프트 지침을 만듭니다."""
    if policy.discussion_emphasis == "customer":
        return ["- 고객 관심사, 후속 논의 주제, 요구사항, 리스크를 더 중요하게 보세요."]
    if policy.discussion_emphasis == "technical":
        return [
            "- 기술 리뷰입니다.",
            "- 제품 설명, 가능성, 아키텍처 논의, 개념 설명을 명시적 합의 없이 action_item이나 decision으로 올리지 마세요.",
            "- 핵심 개념, 기술 논의, Q&A, 아키텍처 쟁점은 summary_facts와 speaker_highlights에 충실히 반영하세요.",
        ]
    if policy.discussion_emphasis == "ideas":
        return [
            "- 브레인스토밍입니다.",
            "- action_item 추출은 매우 보수적으로 수행하세요.",
            "- 아이디어, 논의 주제, 선택지, 우려사항을 summary_facts와 speaker_highlights에 우선 반영하세요.",
        ]
    if policy.discussion_emphasis == "operational":
        return ["- 업무 진행 상황, 일정, 담당자, 후속 작업을 중심으로 정리하세요."]
    return ["- 회의 요약에 필요한 핵심 논의 맥락을 균형 있게 반영하세요."]


def build_followup_sensitivity_guidance(policy: ExtractionPolicy) -> list[str]:
    """followup_sensitivity 값에 맞는 프롬프트 지침을 만듭니다."""
    if policy.followup_sensitivity == "strict":
        return ["- followup_sensitivity=strict: 명시적 follow-up 약속만 action_item으로 추출하세요."]
    if policy.followup_sensitivity == "aggressive":
        return ["- followup_sensitivity=aggressive: 운영상 필요한 후속 작업 후보를 적극적으로 검토하세요."]
    return ["- followup_sensitivity=moderate: 명시적 후속 논의는 남기되 약한 관심 표현은 action_item으로 만들지 마세요."]


def apply_extraction_policy(structure: dict[str, Any], meeting_type: str | None = None) -> PolicyApplicationResult:
    """정책에 따라 약한 action/decision 후보를 논의 메모로 낮춥니다."""
    policy = get_extraction_policy(meeting_type)
    summary_facts = list_if_present(structure.get("summary_facts"))
    decisions = [item for item in list_if_present(structure.get("decisions")) if isinstance(item, dict)]
    action_items = [item for item in list_if_present(structure.get("action_items")) if isinstance(item, dict)]
    speaker_highlights = list_if_present(structure.get("speaker_highlights"))
    warnings = list_if_present(structure.get("warnings"))

    kept_actions: list[dict[str, Any]] = []
    downgraded_action_count = 0
    for item in action_items:
        if should_downgrade_action_item(item, policy):
            downgraded_action_count += 1
            summary_facts.append(build_downgraded_action_note(item))
            warnings.append(build_downgraded_action_warning(item))
        else:
            kept_actions.append(item)

    kept_decisions: list[dict[str, Any]] = []
    downgraded_decision_count = 0
    for item in decisions:
        if should_downgrade_decision(item, policy):
            downgraded_decision_count += 1
            summary_facts.append(build_downgraded_decision_note(item))
            warnings.append(build_downgraded_decision_warning(item))
        else:
            kept_decisions.append(item)

    return PolicyApplicationResult(
        structure={
            "summary_facts": unique_text_list(summary_facts),
            "decisions": kept_decisions,
            "action_items": kept_actions,
            "speaker_highlights": speaker_highlights,
            "warnings": unique_text_list(warnings),
        },
        downgraded_action_count=downgraded_action_count,
        downgraded_decision_count=downgraded_decision_count,
    )


def should_downgrade_action_item(item: dict[str, Any], policy: ExtractionPolicy) -> bool:
    """정책상 action_item으로 보기 약한 후보인지 판단합니다."""
    if policy.action_threshold == "aggressive":
        return False
    if policy.action_threshold != "strict":
        return False

    task = as_text(item.get("task"))
    owner = as_text(item.get("owner"))
    due_date = as_text(item.get("due_date"))
    confidence = as_text(item.get("confidence"))
    source_quote = as_text(item.get("source_quote"))
    combined_key = compact_key(" ".join([task, owner, due_date, confidence, source_quote]))
    has_weak_signal = any(pattern in combined_key for pattern in WEAK_ACTION_PATTERNS)
    has_strong_signal = any(pattern in combined_key for pattern in STRONG_ACTION_PATTERNS)
    owner_missing = is_missing_value(owner)
    due_date_missing = is_missing_value(due_date)

    if has_weak_signal and not has_strong_signal:
        return True
    if has_weak_signal and (owner_missing or due_date_missing):
        return True
    if owner_missing and due_date_missing and not has_strong_signal:
        return True
    if confidence == "low" and (owner_missing or due_date_missing) and not has_strong_signal:
        return True
    return False


def should_downgrade_decision(item: dict[str, Any], policy: ExtractionPolicy) -> bool:
    """정책상 decision으로 보기 약한 후보인지 판단합니다."""
    if policy.decision_threshold != "strict":
        return False

    decision = as_text(item.get("decision"))
    status = as_text(item.get("status"))
    source_quote = as_text(item.get("source_quote"))
    combined_key = compact_key(" ".join([decision, status, source_quote]))
    has_weak_signal = any(pattern in combined_key for pattern in WEAK_DECISION_PATTERNS)
    has_strong_signal = any(pattern in combined_key for pattern in STRONG_DECISION_PATTERNS)

    if has_weak_signal and not has_strong_signal:
        return True
    if status == "미확정" and has_weak_signal:
        return True
    return False


def build_downgraded_action_note(item: dict[str, Any]) -> str:
    """낮춘 action 후보를 summary_facts에 남길 문장으로 만듭니다."""
    task = as_text(item.get("task")) or "후속 작업 후보"
    source_quote = as_text(item.get("source_quote"))
    if source_quote:
        return f"논의 메모: {source_quote}"
    return f"논의 메모: {task}"


def build_downgraded_decision_note(item: dict[str, Any]) -> str:
    """낮춘 decision 후보를 summary_facts에 남길 문장으로 만듭니다."""
    decision = as_text(item.get("decision")) or "결정 후보"
    source_quote = as_text(item.get("source_quote"))
    if source_quote:
        return f"논의 메모: {source_quote}"
    return f"논의 메모: {decision}"


def build_downgraded_action_warning(item: dict[str, Any]) -> str:
    """낮춘 action 후보에 대한 검토 경고를 만듭니다."""
    task = as_text(item.get("task")) or "후속 작업 후보"
    return f"액션 후보 '{task}'는 실행 약속이 불명확해 논의 메모로 분류했습니다."


def build_downgraded_decision_warning(item: dict[str, Any]) -> str:
    """낮춘 decision 후보에 대한 검토 경고를 만듭니다."""
    decision = as_text(item.get("decision")) or "결정 후보"
    return f"결정 후보 '{decision}'는 확정 근거가 약해 논의 메모로 분류했습니다."


def list_if_present(value: Any) -> list[Any]:
    """list 값만 반환하고 그 외에는 빈 list로 둡니다."""
    return value if isinstance(value, list) else []


def as_text(value: Any) -> str:
    """값을 안전한 문자열로 변환합니다."""
    return value.strip() if isinstance(value, str) else ""


def is_missing_value(value: str) -> bool:
    """owner/due_date가 실질적으로 비어 있는지 판단합니다."""
    return compact_key(value) in {"", "미정", "없음", "확인필요", "확인필요함"}


def compact_key(value: str) -> str:
    """간단한 한국어/영문 비교용 key를 만듭니다."""
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", as_text(value)).lower()


def unique_text_list(values: list[Any]) -> list[str]:
    """문자열 목록을 원래 순서대로 중복 제거합니다."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = as_text(value)
        key = compact_key(text)
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result
