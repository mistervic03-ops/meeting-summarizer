import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { ArrowRight, CheckCircle2, FileAudio, FileText, Loader2, UploadCloud, X } from "lucide-react";
import { createJob, downloadMinutes, getJobResult, getJobStatus } from "../api/jobs";
import { JobResult, JobStatus } from "../api/types";
import ResultPage from "./ResultPage";

const AUDIO_ACCEPT = "audio/*,.m4a,.mp3,.mp4,.mpeg,.mpga,.wav,.webm";
const CONTEXT_ACCEPT = ".md,.txt";
const POLLING_INTERVAL_MS = 1500;

type UploadKind = "audio" | "context";

interface FileDropZoneProps {
  accept: string;
  description: string;
  file: File | null;
  kind: UploadKind;
  label: string;
  optional?: boolean;
  onFileChange: (file: File | null) => void;
}

/**
 * Formats a file size into a short human-readable label.
 */
function formatFileSize(size: number): string {
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`;
  }

  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Keeps the polling cadence readable while the backend processes the upload.
 */
function waitForNextPoll(): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, POLLING_INTERVAL_MS));
}

/**
 * Renders the upload surface for required audio and optional team context files.
 */
function FileDropZone({ accept, description, file, kind, label, optional = false, onFileChange }: FileDropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const Icon = kind === "audio" ? FileAudio : FileText;

  /**
   * Opens the hidden file input from the custom drop zone.
   */
  function handleBrowse() {
    inputRef.current?.click();
  }

  /**
   * Stores the selected file from the native file input.
   */
  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    onFileChange(event.target.files?.[0] ?? null);
  }

  /**
   * Highlights the drop zone while a file is dragged over it.
   */
  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(true);
  }

  /**
   * Removes the active drag state when the pointer leaves the drop zone.
   */
  function handleDragLeave() {
    setIsDragging(false);
  }

  /**
   * Accepts the first dropped file for this upload slot.
   */
  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    onFileChange(event.dataTransfer.files?.[0] ?? null);
  }

  /**
   * Clears the selected file without opening the file picker.
   */
  function handleClear() {
    onFileChange(null);

    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-950">{label}</h2>
          <p className="mt-1 text-sm text-slate-500">{description}</p>
        </div>
        {optional ? (
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500">선택</span>
        ) : null}
      </div>

      <div
        className={[
          "rounded-lg border border-dashed bg-white p-4 transition sm:p-5",
          isDragging ? "border-brand-500 bg-brand-50 shadow-card" : "border-slate-200 hover:border-brand-200 hover:bg-brand-50/50"
        ].join(" ")}
        role="button"
        tabIndex={0}
        onClick={handleBrowse}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            handleBrowse();
          }
        }}
      >
        <input ref={inputRef} accept={accept} className="hidden" type="file" onChange={handleInputChange} />

        {file ? (
          <div className="flex items-center gap-4">
            <div className="grid size-12 shrink-0 place-items-center rounded-lg bg-brand-100 text-brand-600">
              <Icon size={24} strokeWidth={2.2} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-slate-950">{file.name}</p>
              <p className="mt-1 text-sm text-slate-500">{formatFileSize(file.size)}</p>
            </div>
            <button
              aria-label={`${label} 제거`}
              className="grid size-9 shrink-0 place-items-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:border-brand-200 hover:text-brand-600"
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                handleClear();
              }}
            >
              <X size={18} />
            </button>
          </div>
        ) : (
          <div className="flex min-h-20 flex-col items-center justify-center gap-3 text-center sm:flex-row sm:justify-start sm:gap-4 sm:text-left">
            <div className="grid size-11 shrink-0 place-items-center rounded-lg bg-brand-100 text-brand-600">
              <UploadCloud size={25} strokeWidth={2.2} />
            </div>
            <div className="min-w-0 max-w-full">
              <p className="text-sm font-semibold text-slate-950">파일을 끌어오거나 클릭해서 선택</p>
              <p className="mt-1 truncate text-xs text-slate-500">{accept}</p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

/**
 * Renders a compact processing state indicator.
 */
function StatusPill({ status }: { status: JobStatus }) {
  const labelByStatus: Record<JobStatus, string> = {
    idle: "대기",
    pending: "접수",
    processing: "처리 중",
    completed: "완료",
    failed: "실패"
  };

  const toneByStatus: Record<JobStatus, string> = {
    idle: "bg-slate-100 text-slate-600",
    pending: "bg-brand-100 text-brand-700",
    processing: "bg-brand-100 text-brand-700",
    completed: "bg-emerald-100 text-emerald-700",
    failed: "bg-red-100 text-red-700"
  };

  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${toneByStatus[status]}`}>
      {labelByStatus[status]}
    </span>
  );
}

/**
 * Provides the branded upload page for starting a meeting minutes job.
 */
export default function UploadPage() {
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [contextFile, setContextFile] = useState<File | null>(null);
  const [status, setStatus] = useState<JobStatus>("idle");
  const [error, setError] = useState("");
  const [jobId, setJobId] = useState("");
  const [result, setResult] = useState<JobResult | null>(null);
  const [completedFileName, setCompletedFileName] = useState("");

  const canProcess = Boolean(audioFile) && status !== "processing" && status !== "pending";

  /**
   * Uploads the selected files and waits until the backend finishes processing.
   */
  async function handleProcess() {
    if (!audioFile) {
      setError("오디오 파일을 먼저 선택해 주세요.");
      return;
    }

    setError("");
    setResult(null);
    setCompletedFileName("");
    setStatus("pending");

    try {
      const createdJob = await createJob({ audioFile, contextFile });
      setJobId(createdJob.job_id);

      while (true) {
        const nextStatus = await getJobStatus(createdJob.job_id);
        setStatus(nextStatus.status);

        if (nextStatus.status === "completed") {
          const nextResult = await getJobResult(createdJob.job_id);
          setResult(nextResult);
          setCompletedFileName(nextResult.filename);
          return;
        }

        if (nextStatus.status === "failed") {
          throw new Error(nextStatus.error || "회의록 생성에 실패했습니다.");
        }

        await waitForNextPoll();
      }
    } catch (caughtError) {
      setStatus("failed");
      setError(caughtError instanceof Error ? caughtError.message : "처리 중 오류가 발생했습니다.");
    }
  }

  if (result) {
    return (
      <ResultPage
        filename={result.filename}
        result={result}
        onDownload={() => {
          if (jobId) {
            downloadMinutes(jobId);
          }
        }}
      />
    );
  }

  return (
    <main className="min-h-screen bg-[#F6F4F8] px-4 py-6 text-slate-950 sm:px-6 lg:px-8">
      <div className="mx-auto flex min-h-[calc(100vh-48px)] w-full max-w-6xl flex-col">
        <header className="flex flex-col gap-5 border-b border-slate-200/80 pb-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="grid size-11 place-items-center rounded-lg bg-brand-500 text-sm font-black text-white shadow-lg shadow-brand-500/25">
              BX
            </div>
            <div>
              <p className="text-sm font-bold text-brand-600">BigxData</p>
              <h1 className="text-2xl font-bold tracking-normal text-slate-950 sm:text-3xl">회의록 생성기</h1>
            </div>
          </div>
          <StatusPill status={status} />
        </header>

        <section className="grid flex-1 items-start gap-8 py-6 lg:grid-cols-[1fr_360px] lg:py-8">
          <div className="rounded-lg border border-white/70 bg-white p-5 shadow-card sm:p-6 lg:p-7">
            <div className="mb-5">
              <p className="text-sm font-semibold text-brand-600">Upload</p>
              <h2 className="mt-2 text-2xl font-bold text-slate-950 sm:text-3xl">회의 파일을 추가하세요</h2>
            </div>

            <div className="space-y-5">
              <FileDropZone
                accept={AUDIO_ACCEPT}
                description="회의 녹음 파일"
                file={audioFile}
                kind="audio"
                label="오디오 파일 업로드"
                onFileChange={setAudioFile}
              />

              <FileDropZone
                accept={CONTEXT_ACCEPT}
                description="회의명, 프로젝트 용어, 참석자 정보"
                file={contextFile}
                kind="context"
                label="팀 컨텍스트 파일"
                optional
                onFileChange={setContextFile}
              />

              <div className="space-y-3 pt-1">
                <button
                  className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-brand-500 px-5 text-sm font-bold text-white shadow-lg shadow-brand-500/25 transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500 disabled:shadow-none"
                  disabled={!canProcess}
                  type="button"
                  onClick={handleProcess}
                >
                  {status === "processing" || status === "pending" ? (
                    <Loader2 className="animate-spin" size={18} />
                  ) : (
                    <ArrowRight size={18} />
                  )}
                  처리 시작
                </button>
                {error ? <p className="rounded-lg bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</p> : null}
                {completedFileName ? (
                  <p className="flex items-center gap-2 rounded-lg bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">
                    <CheckCircle2 size={18} />
                    {completedFileName} 처리 완료
                  </p>
                ) : null}
              </div>
            </div>
          </div>

          <aside className="rounded-lg border border-slate-200 bg-white/80 p-5 shadow-sm sm:p-6">
            <div className="flex items-center gap-3">
              <div className="grid size-10 place-items-center rounded-lg bg-brand-100 text-brand-600">
                <CheckCircle2 size={21} />
              </div>
              <div>
                <h2 className="text-base font-bold text-slate-950">업로드 준비</h2>
                <p className="mt-1 text-sm text-slate-500">오디오 파일 1개가 필요합니다.</p>
              </div>
            </div>

            <div className="mt-6 space-y-4">
              <div className="flex items-center justify-between gap-4 rounded-lg bg-slate-50 px-4 py-3">
                <span className="text-sm font-medium text-slate-600">오디오</span>
                <span className={audioFile ? "text-sm font-bold text-brand-600" : "text-sm font-semibold text-slate-400"}>
                  {audioFile ? "선택됨" : "필수"}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4 rounded-lg bg-slate-50 px-4 py-3">
                <span className="text-sm font-medium text-slate-600">컨텍스트</span>
                <span className={contextFile ? "text-sm font-bold text-brand-600" : "text-sm font-semibold text-slate-400"}>
                  {contextFile ? "선택됨" : "선택"}
                </span>
              </div>
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}
