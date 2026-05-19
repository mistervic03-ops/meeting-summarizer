import { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, Info, Loader2 } from "lucide-react";
import FileDropZone from "../components/FileDropZone";
import ProgressPanel from "../components/ProgressPanel";
import StatusPill from "../components/StatusPill";
import ThemeToggle from "../components/ThemeToggle";
import { useMeetingJob } from "../hooks/useMeetingJob";
import type { MeetingType, SttProviderMode } from "../api/types";
import { DEFAULT_MEETING_TYPE, MEETING_TYPE_OPTIONS, getMeetingTypeLabel } from "../utils/meetingTypes";
import ResultPage from "./ResultPage";
import TranscriptPage from "./TranscriptPage";

const AUDIO_ACCEPT = "audio/*,.m4a,.mp3,.mp4,.mpeg,.mpga,.wav,.webm";
const CONTEXT_ACCEPT = ".md,.txt";
const TRANSCRIPT_ACCEPT = ".txt,.md,text/plain,text/markdown";
const CONTEXT_HELP_TEXT = "회의 목적, 고객사, 프로젝트명, 주요 용어를 짧게 적어주세요.\n예: A소프트와 향후 협력 방향성 및 후속 액션 논의";
const CLOUD_MODE_HELP_TEXT = "OpenAI로 음성을 텍스트로 바꿉니다.\n비용이 발생할 수 있어 중요한 회의나 결과 비교가 필요할 때만 사용하세요.";
type InputMode = "audio" | "text";

const INPUT_MODES: Array<{
  description: string;
  label: string;
  mode: InputMode;
}> = [
  {
    description: "녹음 파일을 올려 텍스트로 변환한 뒤 회의록을 작성합니다.",
    label: "음성 업로드",
    mode: "audio"
  },
  {
    description: "이미 가진 회의 내용을 바로 회의록 작성에 사용합니다.",
    label: "텍스트 업로드",
    mode: "text"
  }
];
const TRANSCRIPTION_PROGRESS_STEPS = [
  { label: "업로드 준비", progress: 10 },
  { label: "음성 분석 준비", progress: 20 },
  { label: "음성 변환", progress: 70 },
  { label: "결과 정리", progress: 100 }
];
const SUMMARY_PROGRESS_STEPS = [
  { label: "내용 확인", progress: 55 },
  { label: "회의 요약 생성", progress: 90 },
  { label: "결과 정리", progress: 100 }
];

const TRANSCRIPTION_MODES: Array<{
  description: string;
  label: string;
  mode: SttProviderMode;
  recommended?: boolean;
}> = [
  {
    description: "사내 서버에서 회의 내용을 빠르게 텍스트로 바꿉니다.",
    label: "기본 모드 / 사내 서버",
    mode: "local_gpu_whisper",
    recommended: true
  },
  {
    description: "OpenAI를 사용하며 비용이 발생할 수 있습니다.",
    label: "고급 모드 / OpenAI",
    mode: "openai"
  }
];

/**
 * Provides the branded upload page for starting a meeting minutes job.
 */
export default function UploadPage() {
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [contextFile, setContextFile] = useState<File | null>(null);
  const [contextText, setContextText] = useState("");
  const [inputMode, setInputMode] = useState<InputMode>("audio");
  const [meetingType, setMeetingType] = useState<MeetingType>(DEFAULT_MEETING_TYPE);
  const [sttProvider, setSttProvider] = useState<SttProviderMode>("local_gpu_whisper");
  const [transcriptFile, setTranscriptFile] = useState<File | null>(null);
  const [transcriptText, setTranscriptText] = useState("");
  const {
    completedFileName,
    error,
    jobStatus,
    recoveryMessage,
    resetJobState,
    result,
    startTranscriptJob,
    startTranscriptionJob,
    status,
    transcriptResult
  } = useMeetingJob();

  const isBusy = status === "processing" || status === "pending";
  const canProcess =
    !isBusy &&
    (inputMode === "audio" ? Boolean(audioFile) : Boolean(transcriptText.trim()));

  useEffect(() => {
    if (!transcriptFile) {
      return;
    }

    let cancelled = false;
    transcriptFile
      .text()
      .then((text) => {
        if (!cancelled) {
          setTranscriptText(text);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTranscriptText("");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [transcriptFile]);

  async function handleStart() {
    const context = await buildMeetingContext(contextText, contextFile);

    if (inputMode === "audio") {
      startTranscriptionJob({ audioFile, context, contextFile: null, meetingType, sttProvider });
      return;
    }

    const transcript = transcriptText.trim();
    if (!transcript) {
      return;
    }

    startTranscriptJob({
      context,
      filename: transcriptFile?.name || "uploaded_transcript.txt",
      meeting_type: meetingType,
      transcript
    });
  }

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
          setContextText("");
          setMeetingType(DEFAULT_MEETING_TYPE);
          setTranscriptFile(null);
          setTranscriptText("");
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
              <section className="space-y-2">
                <div>
                  <h2 className="text-[13px] font-semibold text-slate-950">입력 방식</h2>
                  <p className="mt-0.5 text-[11px] leading-4 text-slate-500">회의 내용을 준비하는 방법을 선택하세요.</p>
                </div>
                <div className="grid gap-1.5 sm:grid-cols-2">
                  {INPUT_MODES.map(({ description, label, mode }) => {
                    const selected = inputMode === mode;
                    return (
                      <button
                        key={mode}
                        className={[
                          "min-h-[58px] rounded-md border px-2.5 py-2 text-left transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:opacity-70",
                          selected
                            ? "border-brand-300 bg-brand-50 text-slate-950 dark:border-app-accent-border dark:bg-app-accent-soft"
                            : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 dark:bg-app-surface"
                        ].join(" ")}
                        disabled={isBusy}
                        type="button"
                        onClick={() => setInputMode(mode)}
                      >
                        <span className="block text-[12px] font-semibold leading-4">{label}</span>
                        <span className="mt-1 block text-[11px] leading-4 text-slate-500">{description}</span>
                      </button>
                    );
                  })}
                </div>
              </section>

              {inputMode === "audio" ? (
                <FileDropZone
                  accept={AUDIO_ACCEPT}
                  description="회의 녹음 파일"
                  file={audioFile}
                  kind="audio"
                  label="회의 녹음"
                  onFileChange={setAudioFile}
                />
              ) : (
                <section className="space-y-2">
                  <FileDropZone
                    accept={TRANSCRIPT_ACCEPT}
                    description="txt 또는 md 회의 내용 파일"
                    file={transcriptFile}
                    kind="context"
                    label="회의 내용 파일"
                    optional
                    onFileChange={setTranscriptFile}
                  />
                  <label className="block">
                    <span className="text-[13px] font-semibold text-slate-950">회의 내용 붙여넣기</span>
                    <textarea
                      className="mt-2 min-h-56 w-full resize-y rounded-md border border-slate-300 bg-white p-3 font-sans text-[13px] leading-6 text-slate-800 outline-none transition-colors duration-150 ease-out placeholder:text-slate-400 focus-visible:border-brand-300 focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500 disabled:opacity-90 dark:bg-app-field"
                      disabled={isBusy}
                      placeholder="이미 정리된 회의 transcript를 붙여넣으세요."
                      value={transcriptText}
                      onChange={(event) => setTranscriptText(event.target.value)}
                    />
                  </label>
                </section>
              )}

              <section className="space-y-2">
                <label className="block">
                  <span className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-slate-950">
                    회의 배경 메모
                    <Info className="text-slate-400" size={13} strokeWidth={2} />
                  </span>
                  <span className="mt-0.5 block whitespace-pre-line text-[11px] leading-4 text-slate-500">{CONTEXT_HELP_TEXT}</span>
                  <textarea
                    className="mt-2 min-h-24 w-full resize-y rounded-md border border-slate-300 bg-white p-3 font-sans text-[13px] leading-5 text-slate-800 outline-none transition-colors duration-150 ease-out placeholder:text-slate-400 focus-visible:border-brand-300 focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500 disabled:opacity-90 dark:bg-app-field"
                    disabled={isBusy}
                    placeholder="예: A소프트와 향후 협력 방향성 및 후속 액션 논의"
                    value={contextText}
                    onChange={(event) => setContextText(event.target.value)}
                  />
                </label>

                <FileDropZone
                  accept={CONTEXT_ACCEPT}
                  description="필요할 때만 txt 또는 md 파일을 추가하세요."
                  file={contextFile}
                  kind="context"
                  label="추가 참고 파일"
                  optional
                  onFileChange={setContextFile}
                />
              </section>
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
                      disabled={isBusy}
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

            {inputMode === "audio" ? (
              <section className="space-y-3">
                <div>
                  <h2 className="text-[13px] font-semibold text-slate-950">음성 변환 방식</h2>
                  <p className="mt-0.5 text-[11px] leading-4 text-slate-500">회의 음성을 텍스트로 바꿀 방법을 선택하세요.</p>
                </div>
                <div className="divide-y divide-slate-100 border-y border-slate-300">
                  {TRANSCRIPTION_MODES.map(({ description, label, mode, recommended }) => {
                    const selected = sttProvider === mode;
                    return (
                      <button
                        key={mode}
                        className={[
                          "group flex w-full items-start gap-2.5 rounded-sm px-1 py-2 text-left transition-colors duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-100 disabled:cursor-not-allowed disabled:opacity-70",
                          selected ? "text-slate-950" : "text-slate-700 hover:bg-slate-50 hover:text-slate-900"
                        ].join(" ")}
                        disabled={isBusy}
                        type="button"
                        onClick={() => setSttProvider(mode)}
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
                            {recommended ? (
                              <span className="rounded-sm bg-brand-50 px-1.5 py-0.5 text-[10px] font-semibold text-brand-700 dark:bg-app-accent-soft dark:text-app-accent">
                                권장
                              </span>
                            ) : null}
                            {mode === "openai" ? (
                              <span className="relative inline-flex text-slate-400">
                                <Info size={13} strokeWidth={2} />
                                <span className="pointer-events-none absolute left-0 top-full z-20 mt-1.5 hidden w-60 whitespace-pre-line rounded-md border border-slate-200 bg-white px-2.5 py-2 text-[11px] font-normal leading-4 text-slate-600 shadow-sm group-focus:block group-hover:block dark:bg-app-popover">
                                  {CLOUD_MODE_HELP_TEXT}
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
            ) : null}

            <section className="space-y-2 border-t border-slate-300 pt-4">
              <button
                className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-brand-600 px-4 text-sm font-medium text-white transition-colors duration-150 ease-out hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-200 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:opacity-80 dark:h-9 dark:bg-app-accent-button dark:px-3.5 dark:text-[13px] dark:hover:bg-app-accent-button-hover dark:focus-visible:ring-app-accent-border"
                disabled={!canProcess}
                type="button"
                onClick={handleStart}
              >
                {isBusy ? (
                  <Loader2 className="animate-spin" size={16} />
                ) : (
                  <ArrowRight size={16} />
                )}
                {isBusy ? "준비 중" : inputMode === "audio" ? "검토 시작" : "회의록 작성 시작"}
              </button>
              {inputMode === "audio" && !audioFile && status === "idle" ? (
                <p className="text-[11px] leading-4 text-slate-500">회의 녹음 파일을 선택하면 시작할 수 있습니다.</p>
              ) : null}
              {inputMode === "text" && !transcriptText.trim() && !transcriptFile && status === "idle" ? (
                <p className="text-[11px] leading-4 text-slate-500">회의 내용을 붙여넣거나 txt/md 파일을 선택하면 시작할 수 있습니다.</p>
              ) : null}
              {isBusy ? (
                <p className="text-[11px] leading-4 text-brand-700 dark:text-app-accent">
                  {inputMode === "audio" ? "파일을 올리고 검토용 내용을 준비하고 있습니다." : "회의록을 작성하고 있습니다."}
                </p>
              ) : null}
              {recoveryMessage ? (
                <p className="flex items-center gap-1.5 text-[11px] leading-4 text-brand-700 dark:text-app-accent">
                  <Info className="shrink-0" size={13} />
                  <span>{recoveryMessage}</span>
                </p>
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
            <ProgressPanel
              idleMessage={inputMode === "audio" ? undefined : "회의 내용을 넣으면 회의록 작성을 시작할 수 있습니다."}
              idleStage={inputMode === "audio" ? undefined : "내용 입력 대기"}
              jobStatus={jobStatus}
              pendingMessage={inputMode === "audio" ? undefined : "회의록 작성을 준비하고 있습니다."}
              pendingStage={inputMode === "audio" ? undefined : "회의록 작성 준비"}
              status={status}
              steps={inputMode === "audio" ? TRANSCRIPTION_PROGRESS_STEPS : SUMMARY_PROGRESS_STEPS}
            />
            <section className="border-y border-slate-300 py-3">
              <h2 className="text-[12px] font-semibold text-slate-950">상태</h2>
              <dl className="mt-2 divide-y divide-slate-100 text-[11px]">
                <div className="flex items-center justify-between gap-4 py-1.5">
                  <dt className="text-slate-500">입력 방식</dt>
                  <dd className="font-medium text-slate-950">
                    {inputMode === "audio" ? "음성 업로드" : "텍스트 업로드"}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-4 py-1.5">
                  <dt className="text-slate-500">{inputMode === "audio" ? "녹음 파일" : "회의 내용"}</dt>
                  <dd className={(inputMode === "audio" ? audioFile : transcriptText.trim() || transcriptFile) ? "font-medium text-slate-950" : "font-medium text-slate-400"}>
                    {(inputMode === "audio" ? audioFile : transcriptText.trim() || transcriptFile) ? "준비됨" : "필수"}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-4 py-1.5">
                  <dt className="text-slate-500">참고 자료</dt>
                  <dd className={contextText.trim() || contextFile ? "font-medium text-slate-950" : "font-medium text-slate-400"}>
                    {contextText.trim() || contextFile ? "입력됨" : "선택"}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-4 py-1.5">
                  <dt className="text-slate-500">회의 유형</dt>
                  <dd className="break-words text-right font-medium text-slate-950">{getMeetingTypeLabel(meetingType)}</dd>
                </div>
                {inputMode === "audio" ? (
                  <div className="flex items-center justify-between gap-4 py-1.5">
                    <dt className="text-slate-500">음성 변환</dt>
                    <dd className="break-words text-right font-medium text-slate-950">
                      {sttProvider === "local_gpu_whisper" ? "사내 서버" : "OpenAI"}
                    </dd>
                  </div>
                ) : null}
              </dl>
            </section>
          </aside>
        </section>
      </div>
    </main>
  );
}

async function buildMeetingContext(contextText: string, contextFile: File | null): Promise<string> {
  const typedContext = contextText.trim();
  const fileContext = await readOptionalContextFile(contextFile);
  const sections: string[] = [];

  if (typedContext) {
    sections.push(`회의 배경 메모:\n${typedContext}`);
  }
  if (fileContext) {
    const filename = contextFile?.name ? ` (${contextFile.name})` : "";
    sections.push(`추가 참고 파일${filename}:\n${fileContext}`);
  }

  return sections.join("\n\n").trim();
}

async function readOptionalContextFile(contextFile: File | null): Promise<string> {
  if (!contextFile) {
    return "";
  }

  try {
    return (await contextFile.text()).trim();
  } catch {
    return "";
  }
}
