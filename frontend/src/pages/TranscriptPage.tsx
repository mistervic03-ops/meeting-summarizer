import { useEffect, useMemo, useState } from "react";
import { Download, Info, Loader2, RotateCcw, Send } from "lucide-react";
import ProgressPanel from "../components/ProgressPanel";
import ThemeToggle from "../components/ThemeToggle";
import ContextHelp from "../components/ui/ContextHelp";
import { useMeetingJob } from "../hooks/useMeetingJob";
import type { MeetingType, StructuredTranscript } from "../api/types";
import ResultPage from "./ResultPage";

interface TranscriptPageProps {
  context?: string;
  filename: string;
  meetingType?: MeetingType;
  onBack?: () => void;
  structuredTranscript?: StructuredTranscript | null;
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
  { label: "검토 완료", progress: 55 },
  { label: "회의 요약 생성", progress: 90 },
  { label: "결과 정리", progress: 100 }
];
const SPEAKER_RENAME_HELP_TEXT = "화자 이름은 액션 아이템 담당자와 발언자 이름으로 표시됩니다.";
const TRANSCRIPT_EDIT_WARNING_TEXT = "Transcript 내용을 직접 수정하면\n화자 구분 정보는 요약에 반영되지 않습니다.";

export default function TranscriptPage({ context = "", filename, meetingType = "execution", onBack, structuredTranscript = null, transcript }: TranscriptPageProps) {
  const speakerInventory = useMemo(() => getSpeakerInventory(structuredTranscript), [structuredTranscript]);
  const speakerInventoryKey = speakerInventory.join("\u0000");
  const initialSpeakerNames = useMemo(() => buildInitialSpeakerNames(speakerInventory), [speakerInventoryKey]);
  const [speakerNames, setSpeakerNames] = useState<Record<string, string>>(() => initialSpeakerNames);
  const [appliedSpeakerNames, setAppliedSpeakerNames] = useState<Record<string, string>>(() => initialSpeakerNames);
  const [isTranscriptManuallyEdited, setIsTranscriptManuallyEdited] = useState(false);
  const [editedTranscript, setEditedTranscript] = useState(transcript);
  const [showUploadResetConfirm, setShowUploadResetConfirm] = useState(false);
  const { error, jobStatus, result, startTranscriptJob, status } = useMeetingJob();
  const isGenerating = status === "pending" || status === "processing";
  const speakerRenderedTranscript = useMemo(
    () => renderStructuredTranscriptForReview(structuredTranscript, speakerNames),
    [structuredTranscript, speakerNames]
  );
  const reviewTranscript = speakerRenderedTranscript || transcript;
  const hasSpeakerRenames = useMemo(
    () => speakerInventory.some((speaker) => (speakerNames[speaker]?.trim() || speaker) !== speaker),
    [speakerInventoryKey, speakerNames]
  );
  const hasPendingSpeakerApplication = useMemo(
    () =>
      isTranscriptManuallyEdited &&
      speakerInventory.some((speaker) => (speakerNames[speaker]?.trim() || speaker) !== (appliedSpeakerNames[speaker]?.trim() || speaker)),
    [appliedSpeakerNames, isTranscriptManuallyEdited, speakerInventoryKey, speakerNames]
  );
  const hasChanges = isTranscriptManuallyEdited || hasSpeakerRenames;
  const stats = useMemo(() => getTranscriptStats(editedTranscript), [editedTranscript]);
  const warnings = useMemo(() => getTranscriptWarnings(editedTranscript), [editedTranscript]);

  useEffect(() => {
    setSpeakerNames(initialSpeakerNames);
    setAppliedSpeakerNames(initialSpeakerNames);
    setIsTranscriptManuallyEdited(false);
  }, [initialSpeakerNames, structuredTranscript, transcript]);

  useEffect(() => {
    if (!isTranscriptManuallyEdited) {
      setEditedTranscript(reviewTranscript);
      setAppliedSpeakerNames(speakerNames);
    }
  }, [isTranscriptManuallyEdited, reviewTranscript, speakerNames]);

  if (result) {
    return <ResultPage filename={result.filename} meetingType={result.meeting_type ?? meetingType} result={result} />;
  }

  /**
   * Starts meeting minutes generation using the edited transcript.
   */
  function handleGenerate() {
    startTranscriptJob({
      context,
      filename,
      meeting_type: meetingType,
      structured_transcript: isTranscriptManuallyEdited ? null : renameStructuredTranscript(structuredTranscript, speakerNames),
      transcript: editedTranscript
    });
  }

  /**
   * Restores speaker names and transcript text to the current reviewed source.
   */
  function handleResetTranscript() {
    setSpeakerNames(initialSpeakerNames);
    setAppliedSpeakerNames(initialSpeakerNames);
    setIsTranscriptManuallyEdited(false);
    setEditedTranscript(renderStructuredTranscriptForReview(structuredTranscript, initialSpeakerNames) || transcript);
  }

  /**
   * Applies pending speaker display names to line-start speaker prefixes only.
   */
  function handleApplySpeakerNames() {
    setEditedTranscript((currentTranscript) => applySpeakerNamesToTranscript(currentTranscript, speakerInventory, appliedSpeakerNames, speakerNames));
    setAppliedSpeakerNames(speakerNames);
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

              {speakerInventory.length ? (
                <section className="border-y border-slate-300 py-3">
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <h3 className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-slate-950">
                        화자 이름
                        <ContextHelp text={SPEAKER_RENAME_HELP_TEXT} />
                      </h3>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-medium text-slate-500">{speakerInventory.length}명 감지</span>
                      {hasPendingSpeakerApplication ? (
                        <button
                          className="inline-flex h-7 items-center rounded-md border border-slate-200 bg-white px-2 text-[11px] font-medium text-slate-700 transition-colors duration-150 ease-out hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus-visible:border-brand-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:text-slate-300 disabled:opacity-80 dark:bg-app-surface"
                          disabled={isGenerating}
                          type="button"
                          onClick={handleApplySpeakerNames}
                        >
                          화자명 적용
                        </button>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-2 divide-y divide-slate-100">
                    {speakerInventory.map((speaker) => (
                      <label
                        key={speaker}
                        className="grid gap-2 py-1.5 text-[11px] sm:grid-cols-[minmax(120px,0.35fr)_minmax(0,1fr)] sm:items-center"
                      >
                        <span className="break-words font-medium text-slate-500">{speaker}</span>
                        <input
                          className="h-8 min-w-0 rounded-md border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-800 outline-none transition-colors duration-150 ease-out focus-visible:border-brand-300 focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400 disabled:opacity-80 dark:bg-app-field"
                          disabled={isGenerating}
                          value={speakerNames[speaker] ?? speaker}
                          onChange={(event) =>
                            setSpeakerNames((currentNames) => ({
                              ...currentNames,
                              [speaker]: event.target.value
                            }))
                          }
                        />
                      </label>
                    ))}
                  </div>
                  {isTranscriptManuallyEdited ? (
                    <div className="mt-2 flex gap-1.5 text-[11px] leading-4 text-amber-800">
                      <Info className="mt-0.5 shrink-0" size={14} />
                      <p className="min-w-0 whitespace-pre-line break-words">{TRANSCRIPT_EDIT_WARNING_TEXT}</p>
                    </div>
                  ) : null}
                </section>
              ) : null}

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
 * Returns speakers in first-appearance order from a structured transcript.
 */
function getSpeakerInventory(structuredTranscript: StructuredTranscript | null): string[] {
  if (!structuredTranscript) {
    return [];
  }

  const speakers: string[] = [];
  const seenSpeakers = new Set<string>();

  for (const utterance of structuredTranscript.utterances) {
    const speaker = normalizeSpeakerLabel(utterance.speaker);
    if (!seenSpeakers.has(speaker)) {
      seenSpeakers.add(speaker);
      speakers.push(speaker);
    }
  }

  return speakers;
}

/**
 * Builds the editable display-name mapping for current speakers.
 */
function buildInitialSpeakerNames(speakers: string[]): Record<string, string> {
  return speakers.reduce<Record<string, string>>((names, speaker) => {
    names[speaker] = speaker;
    return names;
  }, {});
}

/**
 * Renders structured utterances into the editable transcript surface.
 */
function renderStructuredTranscriptForReview(
  structuredTranscript: StructuredTranscript | null,
  speakerNames: Record<string, string>
): string {
  if (!structuredTranscript) {
    return "";
  }

  return structuredTranscript.utterances
    .map((utterance) => {
      const utteranceText = utterance.text.trim();

      if (!utteranceText) {
        return "";
      }

      const originalSpeaker = normalizeSpeakerLabel(utterance.speaker);
      const displaySpeaker = speakerNames[originalSpeaker]?.trim() || originalSpeaker;
      return `${displaySpeaker}: ${utteranceText}`;
    })
    .filter(Boolean)
    .join("\n");
}

/**
 * Replaces only line-start speaker prefixes in a manually edited transcript.
 */
function applySpeakerNamesToTranscript(
  transcript: string,
  speakers: string[],
  appliedSpeakerNames: Record<string, string>,
  nextSpeakerNames: Record<string, string>
): string {
  return transcript
    .split(/\n/)
    .map((line) =>
      speakers.reduce((currentLine, speaker) => {
        const nextSpeaker = nextSpeakerNames[speaker]?.trim() || speaker;
        const previousSpeakers = Array.from(new Set([appliedSpeakerNames[speaker]?.trim() || speaker, speaker])).sort(
          (leftSpeaker, rightSpeaker) => rightSpeaker.length - leftSpeaker.length
        );

        return previousSpeakers.reduce((nextLine, previousSpeaker) => {
          if (!previousSpeaker || previousSpeaker === nextSpeaker) {
            return nextLine;
          }

          const prefixPattern = new RegExp(`^(\\s*(?:\\[[^\\]]+\\]\\s*)?)${escapeRegExp(previousSpeaker)}(\\s*[:：])`);
          return nextLine.replace(prefixPattern, `$1${nextSpeaker}$2`);
        }, currentLine);
      }, line)
    )
    .join("\n");
}

/**
 * Escapes a string for exact use inside a regular expression.
 */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Applies speaker display names to every utterance without changing text content.
 */
function renameStructuredTranscript(
  structuredTranscript: StructuredTranscript | null,
  speakerNames: Record<string, string>
): StructuredTranscript | null {
  if (!structuredTranscript) {
    return null;
  }

  return {
    utterances: structuredTranscript.utterances.map((utterance) => {
      const originalSpeaker = normalizeSpeakerLabel(utterance.speaker);
      const renamedSpeaker = speakerNames[originalSpeaker]?.trim() || originalSpeaker;
      return {
        ...utterance,
        speaker: renamedSpeaker
      };
    })
  };
}

/**
 * Normalizes missing speaker labels to the display bucket used by the review UI.
 */
function normalizeSpeakerLabel(speaker: string | null | undefined): string {
  return speaker?.trim() || "Unknown";
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
