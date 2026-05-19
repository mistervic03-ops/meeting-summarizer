import type { MeetingType } from "../api/types";

export type ResultTab = "summary" | "actions" | "minutes";

export interface ResultTabConfig {
  id: ResultTab;
  label: string;
}

const DISCUSSION_NOTE_PREFIX = "논의 메모:";
const MEETING_TYPES: MeetingType[] = ["execution", "customer_meeting", "technical_review", "brainstorming", "general"];

export function resolveMeetingType(meetingType?: MeetingType | null): MeetingType {
  return meetingType && MEETING_TYPES.includes(meetingType) ? meetingType : "general";
}

export function getResultTabs(_meetingType?: MeetingType | null): ResultTabConfig[] {
  return [
    { id: "summary", label: "요약 및 결정사항" },
    { id: "actions", label: "액션 아이템" },
    { id: "minutes", label: "회의록" }
  ];
}

export function getDefaultResultTab(_meetingType?: MeetingType | null): ResultTab {
  return "summary";
}

export function splitDiscussionNotes(summaryFacts: string[] = []): { discussionNotes: string[]; summaryFacts: string[] } {
  return summaryFacts.reduce(
    (result, fact) => {
      const trimmedFact = fact.trim();
      if (trimmedFact.startsWith(DISCUSSION_NOTE_PREFIX)) {
        const note = trimmedFact.replace(DISCUSSION_NOTE_PREFIX, "").trim();
        if (note) {
          result.discussionNotes.push(note);
        }
        return result;
      }

      if (trimmedFact) {
        result.summaryFacts.push(trimmedFact);
      }
      return result;
    },
    { discussionNotes: [] as string[], summaryFacts: [] as string[] }
  );
}

export function getDisplayWarnings(warnings: string[] = [], meetingType?: MeetingType | null): string[] {
  const resolvedType = resolveMeetingType(meetingType);
  if (resolvedType === "execution" || resolvedType === "general") {
    return warnings;
  }

  const seen = new Set<string>();
  return warnings.reduce<string[]>((result, warning) => {
    if (warning.includes("논의 메모로 분류")) {
      return result;
    }

    const softened = softenWarning(warning);
    const key = softened.replace(/\s+/g, "");
    if (softened && !seen.has(key)) {
      seen.add(key);
      result.push(softened);
    }
    return result;
  }, []);
}

export function getSummaryLabels(meetingType?: MeetingType | null): {
  discussionTitle: string;
  summaryTitle: string;
  warningTitle: string;
  warningHelp: string;
  warningMeta: string;
  speakerTitle: string;
} {
  const resolvedType = resolveMeetingType(meetingType);
  if (resolvedType === "technical_review") {
    return {
      discussionTitle: "논의 메모",
      summaryTitle: "주요 논의",
      warningTitle: "검토 메모",
      warningHelp: "추가 확인이 필요할 수 있는 맥락입니다.\n운영 액션으로 확정된 항목은 별도로 표시됩니다.",
      warningMeta: "맥락 확인 ·",
      speakerTitle: "기술 설명 / 질문 응답"
    };
  }
  if (resolvedType === "customer_meeting") {
    return {
      discussionTitle: "후속 논의",
      summaryTitle: "고객 관심사 및 검토 포인트",
      warningTitle: "검토 메모",
      warningHelp: "요구사항이나 후속 논의 맥락에서 추가 확인이 필요할 수 있는 항목입니다.",
      warningMeta: "맥락 확인 ·",
      speakerTitle: "주요 논의"
    };
  }
  if (resolvedType === "brainstorming") {
    return {
      discussionTitle: "논의 메모",
      summaryTitle: "아이디어 및 논점",
      warningTitle: "검토 메모",
      warningHelp: "아이디어나 논점 중 추가 확인이 필요할 수 있는 항목입니다.",
      warningMeta: "맥락 확인 ·",
      speakerTitle: "논의 내용"
    };
  }

  return {
    discussionTitle: "논의 메모",
    summaryTitle: "요약",
    warningTitle: "검토 필요",
    warningHelp: "담당자·기한·근거가 불명확한 항목입니다.\n회의록 생성은 계속 진행할 수 있습니다.",
    warningMeta: "추가 확인 권장 ·",
    speakerTitle: "주요 발언 요약"
  };
}

export function getMeetingFocusLabel(meetingType?: MeetingType | null): string {
  const resolvedType = resolveMeetingType(meetingType);
  if (resolvedType === "execution") {
    return "운영 정렬";
  }
  if (resolvedType === "technical_review") {
    return "기술 논의";
  }
  if (resolvedType === "customer_meeting") {
    return "고객 맥락";
  }
  if (resolvedType === "brainstorming") {
    return "아이디어 탐색";
  }
  return "균형 정리";
}

export function usesQuietActionTone(meetingType?: MeetingType | null): boolean {
  const resolvedType = resolveMeetingType(meetingType);
  return resolvedType === "technical_review" || resolvedType === "customer_meeting" || resolvedType === "brainstorming";
}

function softenWarning(warning: string): string {
  if (warning.includes("담당자 및 기한 확인 필요")) {
    return warning.replace("담당자 및 기한 확인 필요", "추가 확인이 필요할 수 있습니다");
  }
  if (warning.includes("담당자 확인 필요")) {
    return warning.replace("담당자 확인 필요", "추가 확인이 필요할 수 있습니다");
  }
  if (warning.includes("기한 확인 필요")) {
    return warning.replace("기한 확인 필요", "추가 확인이 필요할 수 있습니다");
  }
  if (warning === "담당자 확인이 필요한 액션 아이템이 있습니다.") {
    return "일부 후속 항목은 추가 확인이 필요할 수 있습니다.";
  }
  if (warning === "기한 확인이 필요한 액션 아이템이 있습니다.") {
    return "일부 후속 항목은 일정 확인이 필요할 수 있습니다.";
  }
  if (warning === "담당자 및 기한 확인이 필요한 액션 아이템이 있습니다.") {
    return "일부 후속 항목은 추가 확인이 필요할 수 있습니다.";
  }
  return warning;
}
