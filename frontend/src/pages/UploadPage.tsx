import { useState } from "react";
import { ArrowRight, CheckCircle2, Info, Loader2 } from "lucide-react";
import FileDropZone from "../components/FileDropZone";
import ProgressPanel from "../components/ProgressPanel";
import StatusPill from "../components/StatusPill";
import ThemeToggle from "../components/ThemeToggle";
import { useMeetingJob } from "../hooks/useMeetingJob";
import type { MeetingType, TranscriptionMode } from "../api/types";
import { DEFAULT_MEETING_TYPE, MEETING_TYPE_OPTIONS, getMeetingTypeLabel } from "../utils/meetingTypes";
import ResultPage from "./ResultPage";
import TranscriptPage from "./TranscriptPage";

const AUDIO_ACCEPT = "audio/*,.m4a,.mp3,.mp4,.mpeg,.mpga,.wav,.webm";
const CONTEXT_ACCEPT = ".md,.txt";
const CONTEXT_HELP_TEXT = "회의명, 프로젝트 용어, 참석자 이름 등을 함께 넣으면\n약어·고유명사·담당자 인식 정확도를 높이는 데 도움이 됩니다.";
const SPEAKER_MODE_HELP_TEXT = "회의 참석자가 여러 명일 때 추천됩니다.\n발화자와 액션 아이템 담당자를 더 정확하게 구분할 수 있습니다.";
const TRANSCRIPTION_PROGRESS_STEPS = [
  { label: "파일 준비", progress: 10 },
  { label: "내용 정리", progress: 95 },
  { label: "검토 준비", progress: 100 }
];

const TRANSCRIPTION_MODES: Array<{
  description: string;
  label: string;
  mode: TranscriptionMode;
}> = [
  {
    description: "화자 구분 없이 회의 내용을 준비합니다.",
    label: "기본",
    mode: "plain"
  },
  {
    description: "화자를 구분해 담당자 정리를 돕습니다.",
    label: "화자 구분",
    mode: "diarized"
  }
];

/**
 * Provides the branded upload page for starting a meeting minutes job.
 */
export default function UploadPage() {
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [contextFile, setContextFile] = useState<File | null>(null);
  const [meetingType, setMeetingType] = useState<MeetingType>(DEFAULT_MEETING_TYPE);
  const [transcriptionMode, setTranscriptionMode] = useState<TranscriptionMode>("plain");
  const {
    completedFileName,
    error,
    jobStatus,
    resetJobState,
    result,
    startTranscriptionJob,
    status,
    transcriptResult
  } = useMeetingJob();

  const canProcess = Boolean(audioFile) && status !== "processing" && status !== "pending";

  if (transcriptResult) {
    return (
      <TranscriptPage
        context={transcriptResult.context ?? ""}
        filename={transcriptResult.filename}
        meetingType={transcriptResult.meeting_type ?? meetingType}
        structuredTranscript={transcriptResult.structured_transcript ?? null}
        transcript={transcriptResult.transcript}
        onBack={() => {
          resetJobState();
          setAudioFile(null);
          setContextFile(null);
          setMeetingType(DEFAULT_MEETING_TYPE);
        }}
      />
    );
  }

  if (result) {
    return (
      <ResultPage
        filename={result.filename}
        meetingType={result.meeting_type ?? meetingType}
        result={result}
      />
    );
  }

  return (
    <main className="min-h-screen bg-white px-4 py-6 text-slate-950 dark:bg-app-bg sm:px-6 lg:px-8">
      <div className="mx-auto flex min-h-[calc(100vh-48px)] w-full max-w-5xl flex-col">
        <header className="flex flex-col gap-3.5 border-b border-slate-300 pb-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="text-[10px] font-medium tracking-[0.04em] text-brand-700 dark:text-app-accent">BIGXDATA · 회의 문서</p>
            <h1 className="mt-1.5 text-[30px] font-semibold leading-[1.12] tracking-normal text-slate-950">회의록</h1>
            <p className="mt-1.5 max-w-2xl text-[12px] leading-5 text-slate-500">
              녹음을 정리하고 확인한 뒤 회의록을 작성합니다.
            </p>
          </div>
          <div className="flex items-center gap-2 sm:pt-1">
            <ThemeToggle />
            <StatusPill status={status} />
          </div>
        </header>

        <section className="grid flex-1 items-start gap-6 py-5 lg:grid-cols-[minmax(0,1fr)_248px]">
          <div className="space-y-5">
            <section className="space-y-3.5">
              <FileDropZone
                accept={AUDIO_ACCEPT}
                description="회의 녹음 파일"
                file={audioFile}
                kind="audio"
                label="회의 녹음"
                onFileChange={setAudioFile}
              />

              <FileDropZone
                accept={CONTEXT_ACCEPT}
                description="회의명, 프로젝트 용어, 참석자 정보"
                file={contextFile}
                helpText={CONTEXT_HELP_TEXT}
                kind="context"
                label="참고 자료"
                optional
                onFileChange={setContextFile}
              />
            </section>

            <section className="space-y-3">
              <div>
                <h2 className="text-[13px] font-semibold text-slate-950">회의 유형</h2>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-500">요약 기준을 선택하세요.</p>
              </div>
              <div className="grid gap-1.5 sm:grid-cols-2">
                {MEETING_TYPE_OPTIONS.map(({ description, label, value }) => {
                  const selected = meetingType === value;
                  return (
                    <button
                      key={value}
                      className={[
                        "min-h-[58px] rounded-md border px-2.5 py-2 text-left transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:opacity-70",
                        selected
                          ? "border-brand-300 bg-brand-50 text-slate-950 dark:border-app-accent-border dark:bg-app-accent-soft"
                          : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 dark:bg-app-surface"
                      ].join(" ")}
                      disabled={status === "processing" || status === "pending"}
                      type="button"
                      onClick={() => setMeetingType(value)}
                    >
                      <span className="block text-[12px] font-semibold leading-4">{label}</span>
                      <span className="mt-1 block text-[11px] leading-4 text-slate-500">{description}</span>
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="space-y-3">
              <div>
                <h2 className="text-[13px] font-semibold text-slate-950">회의 처리 방식</h2>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-500">필요한 정리 방식을 선택하세요.</p>
              </div>
              <div className="divide-y divide-slate-100 border-y border-slate-300">
                {TRANSCRIPTION_MODES.map(({ description, label, mode }) => {
                  const selected = transcriptionMode === mode;
                  return (
                    <button
                      key={mode}
                      className={[
                        "group flex w-full items-start gap-2.5 rounded-sm px-1 py-2 text-left transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:opacity-70",
                        selected ? "text-slate-950" : "text-slate-700 hover:bg-slate-50 hover:text-slate-900"
                      ].join(" ")}
                      disabled={status === "processing" || status === "pending"}
                      type="button"
                      onClick={() => setTranscriptionMode(mode)}
                    >
                      <span
                        className={[
                          "mt-1 size-2.5 shrink-0 rounded-full border",
                          selected ? "border-brand-600 bg-brand-600" : "border-slate-300 bg-white dark:bg-app-surface"
                        ].join(" ")}
                      />
                      <span className="min-w-0">
                        <span className="flex items-center gap-1.5 text-[13px] font-medium">
                          {label}
                          {mode === "diarized" ? (
                            <span className="relative inline-flex text-slate-400">
                              <Info size={13} strokeWidth={2} />
                              <span className="pointer-events-none absolute left-0 top-full z-20 mt-1.5 hidden w-60 whitespace-pre-line rounded-md border border-slate-200 bg-white px-2.5 py-2 text-[11px] font-normal leading-4 text-slate-600 shadow-sm group-focus:block group-hover:block dark:bg-app-popover">
                                {SPEAKER_MODE_HELP_TEXT}
                              </span>
                            </span>
                          ) : null}
                        </span>
                        <span className="mt-0.5 block break-words text-[11px] leading-4 text-slate-500">{description}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>

            <section className="space-y-2 border-t border-slate-300 pt-4">
              <button
                className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-medium text-white transition-colors duration-150 ease-out hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:opacity-80 dark:h-9 dark:bg-app-accent-button dark:px-3.5 dark:text-[13px] dark:hover:bg-app-accent-button-hover dark:focus-visible:ring-app-accent-border"
                disabled={!canProcess}
                type="button"
                onClick={() => startTranscriptionJob({ audioFile, contextFile, meetingType, transcriptionMode })}
              >
                {status === "processing" || status === "pending" ? (
                  <Loader2 className="animate-spin" size={16} />
                ) : (
                  <ArrowRight size={16} />
                )}
                {status === "processing" || status === "pending" ? "준비 중" : "검토 시작"}
              </button>
              {!audioFile && status === "idle" ? (
                <p className="text-[11px] leading-4 text-slate-500">회의 녹음 파일을 선택하면 시작할 수 있습니다.</p>
              ) : null}
              {status === "processing" || status === "pending" ? (
                <p className="text-[11px] leading-4 text-brand-700 dark:text-app-accent">파일을 올리고 검토용 내용을 준비하고 있습니다.</p>
              ) : null}
              {error ? <p className="break-words text-xs font-medium leading-5 text-red-700">{error}</p> : null}
              {completedFileName ? (
                <p className="flex items-center gap-2 break-words text-xs font-medium leading-5 text-emerald-700">
                  <CheckCircle2 className="shrink-0" size={15} />
                  <span className="min-w-0">{completedFileName} 준비 완료</span>
                </p>
              ) : null}
            </section>
          </div>

          <aside className="space-y-3.5 lg:pt-6">
            <ProgressPanel jobStatus={jobStatus} status={status} steps={TRANSCRIPTION_PROGRESS_STEPS} />
            <section className="border-y border-slate-300 py-3">
              <h2 className="text-[12px] font-semibold text-slate-950">상태</h2>
              <dl className="mt-2 divide-y divide-slate-100 text-[11px]">
                <div className="flex items-center justify-between gap-4 py-1.5">
                  <dt className="text-slate-500">녹음 파일</dt>
                  <dd className={audioFile ? "font-medium text-slate-950" : "font-medium text-slate-400"}>
                    {audioFile ? "선택됨" : "필수"}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-4 py-1.5">
                  <dt className="text-slate-500">참고 자료</dt>
                  <dd className={contextFile ? "font-medium text-slate-950" : "font-medium text-slate-400"}>
                    {contextFile ? "선택됨" : "선택"}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-4 py-1.5">
                  <dt className="text-slate-500">회의 유형</dt>
                  <dd className="break-words text-right font-medium text-slate-950">{getMeetingTypeLabel(meetingType)}</dd>
                </div>
                <div className="flex items-center justify-between gap-4 py-1.5">
                  <dt className="text-slate-500">처리 방식</dt>
                  <dd className="break-words text-right font-medium text-slate-950">
                    {transcriptionMode === "plain" ? "기본" : "화자 구분"}
                  </dd>
                </div>
              </dl>
            </section>
          </aside>
        </section>
      </div>
    </main>
  );
}
