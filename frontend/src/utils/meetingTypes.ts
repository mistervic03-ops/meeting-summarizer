import type { MeetingType } from "../api/types";

export const DEFAULT_MEETING_TYPE: MeetingType = "execution";

export const MEETING_TYPE_OPTIONS: Array<{
  description: string;
  label: string;
  value: MeetingType;
}> = [
  {
    description: "업무 진행 상황, 일정, 담당자, 후속 작업을 정리하는 회의",
    label: "실행 회의",
    value: "execution"
  },
  {
    description: "요구사항, 협력 방향, 후속 논의를 중심으로 하는 회의",
    label: "고객 / 협업 미팅",
    value: "customer_meeting"
  },
  {
    description: "제품, 기술 구조, 아키텍처, 데모 등을 설명하고 질의응답하는 회의",
    label: "기술 설명 / 리뷰",
    value: "technical_review"
  },
  {
    description: "아이디어, 개선점, 회고 내용을 자유롭게 논의하는 회의",
    label: "아이디어 / 회고",
    value: "brainstorming"
  }
];

export function getMeetingTypeLabel(meetingType?: MeetingType | null): string {
  const option = MEETING_TYPE_OPTIONS.find((item) => item.value === meetingType);
  return option?.label ?? "일반 회의";
}
