import { useEffect, useMemo, useState } from "react";
import { Download, Loader2, LogOut, RotateCcw, Send } from "lucide-react";
import ProgressPanel from "../components/ProgressPanel";
import ThemeToggle from "../components/ThemeToggle";
import { useMeetingJob } from "../hooks/useMeetingJob";
import type { PrecomputedSummaryState } from "../hooks/usePrecomputedSummary";
import type { JobResult, MeetingType } from "../api/types";
import ResultPage from "./ResultPage";

interface TranscriptPageProps {
  context?: string;
  filename: string;
  meetingType?: MeetingType;
  onBack?: () => void;
  onLogout?: () => void;
  precomputedSummary?: PrecomputedSummaryState;
  transcript: string;
}

interface TranscriptStats {
  characters: number;
  lines: number;
}

/**
 * Lets users review and edit STT text before generating meeting minutes.
 */
const SUMMARY_PROGRESS_STEPS = [
  { label: "검토 완료", progress: 15 },
  { label: "회의 요약 생성", progress: 88 },
  { label: "결과 정리", progress: 100 }
];

export default function TranscriptPage({
  context = "",
  filename,
  meetingType = "execution",
  onBack,
  onLogout,
  precomputedSummary,
  transcript
}: TranscriptPageProps) {
  const [acceptedPrecomputedResult, setAcceptedPrecomputedResult] = useState<JobResult | null>(null);
  const [isTranscriptManuallyEdited, setIsTranscriptManuallyEdited] = useState(false);
  const [editedTranscript, setEditedTranscript] = useState(transcript);
  const [showUploadResetConfirm, setShowUploadResetConfirm] = useState(false);
  const { error, jobStatus, result, startTranscriptJob, status } = useMeetingJob();
  const isGenerating = status === "pending" || status === "processing";
  const hasChanges = isTranscriptManuallyEdited;
  const isPrecomputedSummaryStale = Boolean(precomputedSummary?.isStale || editedTranscript !== transcript);
  const stats = useMemo(() => getTranscriptStats(editedTranscript), [editedTranscript]);
  const warnings = useMemo(() => getTranscriptWarnings(editedTranscript), [editedTranscript]);

  useEffect(() => {
    setAcceptedPrecomputedResult(null);
    setIsTranscriptManuallyEdited(false);
    setEditedTranscript(transcript);
  }, [transcript]);

  useEffect(() => {
    if (!isTranscriptManuallyEdited) {
      setEditedTranscript(transcript);
    }
  }, [isTranscriptManuallyEdited, transcript]);

  const completedResult = acceptedPrecomputedResult ?? result;

  if (completedResult) {
    return (
      <ResultPage
        filename={completedResult.filename}
        meetingType={completedResult.meeting_type ?? meetingType}
        onLogout={onLogout}
        result={completedResult}
      />
    );
  }

  /**
   * Starts meeting minutes generation using the edited transcript.
   */
  function handleGenerate() {
    const nextPrecomputedResult = isPrecomputedSummaryStale ? null : precomputedSummary?.getPrecomputedResult();
    if (nextPrecomputedResult) {
      setAcceptedPrecomputedResult(nextPrecomputedResult);
      return;
    }

    startTranscriptJob({
      context,
      filename,
      meeting_type: meetingType,
      transcript: editedTranscript
    });
  }

  /**
   * Restores transcript text to the current reviewed source.
   */
  function handleResetTranscript() {
    setIsTranscriptManuallyEdited(false);
    setEditedTranscript(transcript);
  }

  /**
   * Shows a confirmation before leaving the current transcript review.
   */
  function handleRequestOtherUpload() {
    setShowUploadResetConfirm(true);
  }

  /**
   * Leaves the current transcript review after the user confirms.
   */
  function handleConfirmOtherUpload() {
    onBack?.();
  }

  return (
    <main className="min-h-screen bg-white px-4 py-6 text-slate-950 dark:bg-app-bg sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-5xl">
        <header className="flex flex-col gap-3.5 border-b border-slate-300 pb-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="text-[10px] font-medium tracking-[0.04em] text-brand-700 dark:text-app-accent">BIGXDATA · 회의 내용 검토</p>
            <h1 className="mt-1.5 break-words text-[30px] font-semibold leading-[1.12] tracking-normal text-slate-950">{filename}</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2 sm:mt-1">
            <ThemeToggle />
            {onLogout ? (
              <button
                className="inline-flex h-7 shrink-0 items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-2 text-[11px] font-medium text-slate-500 transition-colors duration-150 ease-out hover:border-slate-300 hover:bg-slate-50 hover:text-slate-800 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 dark:border-app-border dark:bg-app-surface dark:text-app-muted dark:hover:bg-app-hover dark:hover:text-app-text"
                type="button"
                onClick={onLogout}
              >
                <LogOut size={13} />
                로그아웃
              </button>
            ) : null}
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-[11px] font-medium text-slate-500">
              <span>{stats.characters.toLocaleString()}자</span>
              <span aria-hidden="true" className="text-slate-300">·</span>
              <span>{stats.lines.toLocaleString()}줄</span>
              {hasChanges ? (
                <>
                  <span aria-hidden="true" className="text-slate-300">·</span>
                  <span className="font-medium text-amber-700">수정됨</span>
                </>
              ) : null}
            </div>
          </div>
        </header>

        <section className="grid items-start gap-6 py-5 lg:grid-cols-[minmax(0,1fr)_248px]">
          <div className="space-y-5">
            <section className="border-b border-slate-300 pb-5">
              <div className="mb-2">
                <p className="text-[11px] font-semibold text-slate-500">원본</p>
                <h2 className="mt-0.5 text-[14px] font-semibold text-slate-950">원본 내용</h2>
              </div>
              <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-words rounded-md border border-slate-200 bg-slate-50 px-3 py-2.5 font-sans text-[12px] leading-5 text-slate-700">
                {transcript.trim() || "표시할 내용이 없습니다."}
              </pre>
            </section>

            <section className="space-y-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-[11px] font-semibold text-slate-500">편집</p>
                  <h2 className="mt-0.5 text-[14px] font-semibold text-slate-950">회의록 작성 기준</h2>
                </div>
                <button
                  className="inline-flex h-8 w-fit items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-600 transition-colors duration-150 ease-out hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:text-slate-300 disabled:opacity-80 dark:bg-app-surface"
                  disabled={!hasChanges || isGenerating}
                  type="button"
                  onClick={handleResetTranscript}
                >
                  <RotateCcw size={14} />
                  원본으로 되돌리기
                </button>
              </div>

              <textarea
                className="min-h-[480px] w-full resize-y rounded-md border border-slate-300 bg-white p-3 font-sans text-[13px] leading-6 text-slate-800 outline-none transition-colors duration-150 ease-out placeholder:text-slate-400 focus-visible:border-brand-300 focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500 disabled:opacity-90 dark:bg-app-field"
                disabled={isGenerating}
                value={editedTranscript}
                onChange={(event) => {
                  setIsTranscriptManuallyEdited(true);
                  setEditedTranscript(event.target.value);
                }}
              />
            </section>
          </div>

          <aside className="space-y-3.5 lg:pt-6">
            <ProgressPanel
              idleMessage="내용을 확인한 뒤 회의록 작성을 시작하세요."
              idleStage="검토 대기"
              jobStatus={jobStatus}
              pendingMessage="회의록 작성을 준비하고 있습니다."
              pendingStage="회의록 작성 준비"
              status={status}
              steps={SUMMARY_PROGRESS_STEPS}
            />

            <section className="border-y border-slate-300 py-3">
              <h2 className="text-[12px] font-semibold text-slate-950">검토 메모</h2>
              {warnings.length ? (
                <ul className="mt-2 space-y-1.5 text-[11px] leading-4 text-amber-800">
                  {warnings.map((warning) => (
                    <li key={warning} className="break-words border-l border-amber-300 pl-3">
                      {warning}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-[11px] leading-4 text-emerald-700">검토 메모가 없습니다.</p>
              )}
            </section>

            <section className="border-y border-slate-300 py-3">
              <h2 className="text-[12px] font-semibold text-slate-950">다운로드</h2>
              <div className="mt-2 grid gap-1.5">
                <button
                  className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-700 transition-colors duration-150 ease-out hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 dark:bg-app-surface"
                  type="button"
                  onClick={() => downloadTranscriptFile(filename, editedTranscript, "txt")}
                >
                  <Download size={14} />
                  .txt 다운로드
                </button>
                <button
                  className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-700 transition-colors duration-150 ease-out hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 dark:bg-app-surface"
                  type="button"
                  onClick={() => downloadTranscriptFile(filename, editedTranscript, "md")}
                >
                  <Download size={14} />
                  .md 다운로드
                </button>
              </div>
            </section>

            <section className="space-y-2 border-y border-slate-300 py-3">
              <button
                className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-medium text-white transition-colors duration-150 ease-out hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:opacity-80 dark:h-9 dark:bg-app-accent-button dark:px-3.5 dark:text-[13px] dark:hover:bg-app-accent-button-hover dark:focus-visible:ring-app-accent-border"
                disabled={isGenerating || !editedTranscript.trim()}
                type="button"
                onClick={handleGenerate}
              >
                {isGenerating ? <Loader2 className="animate-spin" size={16} /> : <Send size={16} />}
                {isGenerating ? "회의록 작성 중" : "회의록 작성 시작"}
              </button>
              {error ? <p className="break-words text-xs font-medium leading-5 text-red-700">{error}</p> : null}
              {onBack ? (
                <>
                  <button
                    className="inline-flex h-8 w-full items-center justify-center rounded-md border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-600 transition-colors duration-150 ease-out hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:text-slate-300 disabled:opacity-80 dark:bg-app-surface"
                    disabled={isGenerating}
                    type="button"
                    onClick={handleRequestOtherUpload}
                  >
                    다른 파일 업로드
                  </button>
                  {showUploadResetConfirm ? (
                    <div className="space-y-2 border-l border-amber-300 pl-3">
                      <p className="break-words text-[11px] leading-4 text-amber-800">
                        다른 파일을 업로드하면 현재 파일의 진행 상황은 사라집니다.
                      </p>
                      <div className="flex gap-1.5">
                        <button
                          className="inline-flex h-7 items-center rounded-md bg-slate-900 px-2.5 text-[11px] font-medium text-white transition-colors duration-150 ease-out hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-200 dark:bg-app-inverse dark:text-app-bg"
                          type="button"
                          onClick={handleConfirmOtherUpload}
                        >
                          확인
                        </button>
                        <button
                          className="inline-flex h-7 items-center rounded-md border border-slate-200 bg-white px-2.5 text-[11px] font-medium text-slate-600 transition-colors duration-150 ease-out hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 dark:bg-app-surface"
                          type="button"
                          onClick={() => setShowUploadResetConfirm(false)}
                        >
                          취소
                        </button>
                      </div>
                    </div>
                  ) : null}
                </>
              ) : null}
            </section>
          </aside>
        </section>
      </div>
    </main>
  );
}

/**
 * Returns basic transcript size metrics for the review header.
 */
function getTranscriptStats(transcript: string): TranscriptStats {
  return {
    characters: transcript.length,
    lines: transcript.trim() ? transcript.split(/\r?\n/).length : 0
  };
}

/**
 * Returns simple quality warnings that help users decide whether to edit STT text.
 */
function getTranscriptWarnings(transcript: string): string[] {
  const trimmedTranscript = transcript.trim();
  const warnings: string[] = [];

  if (!trimmedTranscript) {
    return ["내용이 비어 있습니다."];
  }
  if (trimmedTranscript.length < 100) {
    warnings.push("내용이 짧아 회의록이 충분하지 않을 수 있습니다.");
  }
  if (!/[.!?。！？\n]/.test(trimmedTranscript)) {
    warnings.push("문장 구분이 적어 검토가 필요할 수 있습니다.");
  }
  if (/(\[inaudible\]|알 수 없음|인식 불가|잡음)/i.test(trimmedTranscript)) {
    warnings.push("인식 불가 또는 잡음 표시가 포함되어 있습니다.");
  }
  if (trimmedTranscript.split(/\s+/).filter((word) => word.length > 40).length > 0) {
    warnings.push("비정상적으로 긴 단어가 있어 음성 인식 오류가 섞였을 수 있습니다.");
  }

  return warnings;
}

/**
 * Downloads the edited transcript as a txt or Markdown file.
 */
function downloadTranscriptFile(filename: string, transcript: string, extension: "txt" | "md") {
  const baseName = filename.replace(/\.[^.]+$/, "") || "meeting_notes";
  const content = extension === "md" ? `# ${baseName} 회의 내용\n\n${transcript}` : transcript;
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = `${baseName}_meeting_notes.${extension}`;
  link.click();
  URL.revokeObjectURL(url);
}
