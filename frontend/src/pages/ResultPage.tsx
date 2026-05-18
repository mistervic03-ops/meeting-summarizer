import { useEffect, useMemo, useState } from "react";
import { CalendarDays, Check, ChevronDown, Copy, Download, Edit3 } from "lucide-react";
import ActionsTab from "../components/ActionsTab";
import MinutesTab from "../components/MinutesTab";
import SummaryTab from "../components/SummaryTab";
import ThemeToggle from "../components/ThemeToggle";
import { JobResult, MeetingType } from "../api/types";
import { ExportFormat, exportMeetingDocument, sanitizeExportFilename } from "../utils/exportDocument";
import { normalizeDisplayText, normalizeMarkdownForDisplay } from "../utils/displayText";
import { getMeetingTypeLabel } from "../utils/meetingTypes";
import { getDefaultResultTab, getDisplayWarnings, getMeetingFocusLabel, getResultTabs, ResultTab, resolveMeetingType, splitDiscussionNotes, usesQuietActionTone } from "../utils/resultView";

interface ResultPageProps {
  filename?: string;
  meetingDate?: string;
  meetingType?: MeetingType;
  result?: JobResult;
  onCopy?: (minutes: string) => void;
}

const EMPTY_RESULT: JobResult = {
  job_id: "preview",
  filename: "회의 녹음 파일",
  minutes: "",
  action_items: [],
  summary_facts: [],
  decisions: [],
  speaker_highlights: [],
  warnings: []
};

const EXPORT_OPTIONS: Array<{ format: ExportFormat; label: string }> = [
  { format: "markdown", label: "Markdown (.md)" },
  { format: "text", label: "Plain text (.txt)" },
  { format: "pdf", label: "PDF" },
  { format: "docx", label: "Word (.docx)" }
];

/**
 * Returns today's date as a compact Korean display label.
 */
function getDefaultMeetingDate(): string {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium"
  }).format(new Date());
}

/**
 * Copies text to the clipboard when browser permissions allow it.
 */
async function copyToClipboard(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}

/**
 * Renders the professional meeting result page with summary, action, and full-minutes tabs.
 */
export default function ResultPage({
  filename,
  meetingDate,
  meetingType,
  result = EMPTY_RESULT,
  onCopy
}: ResultPageProps) {
  const [activeTab, setActiveTab] = useState<ResultTab>("actions");
  const title = normalizeDisplayText(filename || result.filename || "회의록");
  const displayMinutes = normalizeMarkdownForDisplay(result.minutes);
  const [editedMinutes, setEditedMinutes] = useState(displayMinutes);
  const [isEditing, setIsEditing] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"copied" | "idle">("idle");
  const [isExportOpen, setIsExportOpen] = useState(false);
  const finalizedMinutes = normalizeMarkdownForDisplay(editedMinutes);
  const exportFilename = sanitizeExportFilename(title);
  const dateLabel = meetingDate || getDefaultMeetingDate();
  const resolvedMeetingType = resolveMeetingType(result.meeting_type ?? meetingType);
  const meetingTypeLabel = getMeetingTypeLabel(resolvedMeetingType);
  const meetingFocusLabel = getMeetingFocusLabel(resolvedMeetingType);
  const actionItems = result.action_items ?? [];
  const { discussionNotes, summaryFacts } = splitDiscussionNotes(result.summary_facts ?? []);
  const displayWarnings = getDisplayWarnings(result.warnings ?? [], resolvedMeetingType);
  const tabs = useMemo(() => getResultTabs(resolvedMeetingType), [resolvedMeetingType]);
  const factsCount = summaryFacts.length;
  const decisionsCount = result.decisions?.length ?? 0;
  const warningsCount = displayWarnings.length;

  const tabPanel = useMemo(() => {
    if (activeTab === "actions") {
      return <ActionsTab isQuiet={usesQuietActionTone(resolvedMeetingType)} items={actionItems} />;
    }

    if (activeTab === "minutes") {
      return <MinutesTab isEditing={isEditing} minutes={editedMinutes} onChange={setEditedMinutes} />;
    }

    return <SummaryTab discussionNotes={discussionNotes} displayWarnings={displayWarnings} meetingType={resolvedMeetingType} result={result} summaryFacts={summaryFacts} />;
  }, [activeTab, actionItems, discussionNotes, displayWarnings, editedMinutes, isEditing, resolvedMeetingType, result, summaryFacts]);

  useEffect(() => {
    setEditedMinutes(displayMinutes);
    setIsEditing(false);
    setCopyStatus("idle");
    setActiveTab(getDefaultResultTab(resolvedMeetingType));
  }, [displayMinutes, result.job_id, resolvedMeetingType]);

  useEffect(() => {
    if (copyStatus !== "copied") {
      return undefined;
    }

    const timerId = window.setTimeout(() => setCopyStatus("idle"), 1600);
    return () => window.clearTimeout(timerId);
  }, [copyStatus]);

  /**
   * 읽기 화면과 일반 텍스트 편집 화면을 전환합니다.
   */
  function handleEditToggle() {
    setActiveTab("minutes");
    setIsEditing((current) => !current);
  }

  /**
   * Copies the full minutes text and allows callers to hook into the action.
   */
  async function handleCopy() {
    await copyToClipboard(finalizedMinutes);
    setCopyStatus("copied");
    onCopy?.(finalizedMinutes);
  }

  /**
   * 브라우저에서 가볍게 처리할 수 있는 방식으로 회의록을 내보냅니다.
   */
  function handleExport(format: ExportFormat) {
    exportMeetingDocument({
      filename: exportFilename,
      format,
      markdown: finalizedMinutes,
      title
    });
    setIsExportOpen(false);
  }

  return (
    <main className="min-h-screen bg-white px-4 py-6 text-slate-950 dark:bg-app-bg sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-5xl">
        <header className="border-b border-slate-300 pb-5">
          <div className="mb-1.5 flex items-center justify-between gap-3">
            <p className="min-w-0 text-[10px] font-medium tracking-[0.04em] text-brand-700 dark:text-app-accent">BIGXDATA · 회의록</p>
            <ThemeToggle compact />
          </div>
          <div className="flex flex-col gap-3.5 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <h1 className="mt-1.5 break-words text-[30px] font-semibold leading-[1.12] tracking-normal text-slate-950">{title}</h1>
              <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] font-medium text-slate-500">
                <span className="inline-flex items-center gap-1.5">
                  <CalendarDays className="shrink-0" size={12} />
                  {dateLabel}
                </span>
                <span aria-hidden="true">·</span>
                <span>유형 {meetingTypeLabel}</span>
                <span aria-hidden="true">·</span>
                <span>초점 {meetingFocusLabel}</span>
                <span aria-hidden="true">·</span>
                <span>액션 · {actionItems.length}</span>
                <span aria-hidden="true">·</span>
                <span>결정 · {decisionsCount}</span>
                <span aria-hidden="true">·</span>
                <span>요약 · {factsCount}</span>
                {discussionNotes.length ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <span>메모 · {discussionNotes.length}</span>
                  </>
                ) : null}
                {warningsCount ? (
                  <>
                    <span aria-hidden="true">·</span>
                    <span>검토 · {warningsCount}</span>
                  </>
                ) : null}
              </div>
            </div>

            <div className="flex flex-col gap-1.5 sm:flex-row lg:pt-1">
              <button
                className="inline-flex h-9 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition-colors duration-150 ease-out hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:text-slate-300 disabled:opacity-80 dark:bg-app-surface"
                disabled={!finalizedMinutes && !isEditing}
                type="button"
                onClick={handleEditToggle}
              >
                {isEditing ? <Check className="shrink-0" size={15} /> : <Edit3 className="shrink-0" size={15} />}
                {isEditing ? "완료" : "편집"}
              </button>
              <button
                className="inline-flex h-9 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition-colors duration-150 ease-out hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:text-slate-300 disabled:opacity-80 dark:bg-app-surface"
                disabled={!finalizedMinutes}
                type="button"
                onClick={handleCopy}
              >
                {copyStatus === "copied" ? <Check className="shrink-0" size={15} /> : <Copy className="shrink-0" size={15} />}
                {copyStatus === "copied" ? "복사됨" : "복사"}
              </button>
              <div className="relative">
                <button
                  aria-expanded={isExportOpen}
                  className="inline-flex h-9 w-full shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md bg-brand-600 px-3 text-sm font-medium text-white transition-colors duration-150 ease-out hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:opacity-80 dark:bg-app-accent-button dark:text-[13px] dark:hover:bg-app-accent-button-hover dark:focus-visible:ring-app-accent-border sm:w-auto"
                  disabled={!finalizedMinutes}
                  type="button"
                  onClick={() => setIsExportOpen((current) => !current)}
                >
                  <Download className="shrink-0" size={15} />
                  내보내기
                  <ChevronDown className={`shrink-0 transition-transform duration-150 ease-out ${isExportOpen ? "rotate-180" : ""}`} size={14} />
                </button>
                {isExportOpen ? (
                  <div className="absolute right-0 z-30 mt-1.5 w-44 overflow-hidden rounded-md border border-slate-200 bg-white py-1 shadow-sm dark:border-app-border dark:bg-app-popover">
                    {EXPORT_OPTIONS.map((option) => (
                      <button
                        key={option.format}
                        className="block w-full px-3 py-2 text-left text-[12px] font-medium text-slate-600 transition-colors duration-150 ease-out hover:bg-slate-50 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 dark:text-app-muted dark:hover:bg-app-hover dark:hover:text-app-text"
                        type="button"
                        onClick={() => handleExport(option.format)}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </header>

        <nav className="mt-4 overflow-x-auto border-b border-slate-300" aria-label="결과 탭">
          <div className="flex min-w-max gap-5">
            {tabs.map((tab) => {
              const isActive = activeTab === tab.id;

              return (
                <button
                  key={tab.id}
                  className={[
                    "h-9 whitespace-nowrap border-b-2 px-0.5 text-sm font-medium transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100",
                    isActive ? "border-brand-600 text-slate-950" : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-800"
                  ].join(" ")}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </nav>

        <section className="-mx-3 mt-5 bg-[#FBFAFC] px-3 py-5 pb-9 dark:bg-app-surface sm:-mx-5 sm:px-5">
          {tabPanel}
        </section>
      </div>
    </main>
  );
}
