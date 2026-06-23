import { useEffect, useState } from "react";
import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import { JobStatus, JobStatusResponse } from "../api/types";

interface ProgressPanelProps {
  idleMessage?: string;
  idleStage?: string;
  jobStatus: JobStatusResponse | null;
  pendingMessage?: string;
  pendingStage?: string;
  steps?: Array<{ label: string; progress: number }>;
  status: JobStatus;
}

const DEFAULT_STEPS = [
  { label: "업로드 준비", progress: 10 },
  { label: "음성 변환", progress: 80 },
  { label: "회의 요약 생성", progress: 88 },
  { label: "결과 정리", progress: 100 }
];

/**
 * Renders the upload job progress as a quiet, scan-friendly progress section.
 */
export default function ProgressPanel({
  idleMessage = "회의 녹음 파일 1개가 필요합니다.",
  idleStage = "업로드 준비",
  jobStatus,
  pendingMessage = "작업을 서버에 등록하고 있습니다.",
  pendingStage = "작업 접수",
  steps = DEFAULT_STEPS,
  status
}: ProgressPanelProps) {
  const reportedProgress = getReportedProgress(status, jobStatus);
  const [visibleProgress, setVisibleProgress] = useState(reportedProgress);
  const reportedStage = jobStatus?.stage ?? (status === "idle" ? idleStage : pendingStage);
  const progress = getVisibleProgress(status, visibleProgress, reportedProgress, reportedStage);
  const stage = getFriendlyStage(reportedStage, status);
  const message = jobStatus?.message ?? (status === "idle" ? idleMessage : pendingMessage);
  const activeStepIndex = getActiveStepIndex(steps, progress, stage, status);
  const chunkDetail = getChunkDetail(jobStatus);

  useEffect(() => {
    setVisibleProgress((currentProgress) => {
      const minimumProgress = getMinimumProgress(status, reportedProgress, reportedStage);
      if (status === "idle") {
        return 0;
      }
      if (status === "completed") {
        return 100;
      }
      if (currentProgress - minimumProgress > 20) {
        return minimumProgress;
      }
      return Math.max(minimumProgress, Math.min(currentProgress, 99));
    });
  }, [reportedProgress, reportedStage, status]);

  useEffect(() => {
    if (status !== "pending" && status !== "processing") {
      return;
    }

    const intervalId = window.setInterval(() => {
      setVisibleProgress((currentProgress) => {
        const cap = getOptimisticProgressCap(jobStatus, status);
        if (currentProgress >= cap) {
          return currentProgress;
        }
        return Math.min(cap, currentProgress + 1);
      });
    }, 2500);

    return () => window.clearInterval(intervalId);
  }, [jobStatus?.stage, status]);

  return (
    <section className="border-y border-slate-300 py-3">
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5 text-slate-400">
          {status === "completed" ? <CheckCircle2 size={15} /> : <Loader2 className={status === "idle" ? "" : "animate-spin"} size={15} />}
        </div>
        <div className="min-w-0">
          <h2 className="text-[12px] font-semibold text-slate-950">{stage}</h2>
          <p className="mt-0.5 break-words text-[11px] leading-4 text-slate-500">{message}</p>
          {chunkDetail ? <p className="mt-1 text-[11px] font-medium leading-4 text-brand-700 dark:text-app-accent">{chunkDetail}</p> : null}
        </div>
      </div>

      <div className="mt-3">
        <div className="h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-app-field">
          <div
            aria-label="작업 진행률"
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={Math.round(progress)}
            className={[
              "h-full rounded-full transition-all duration-500 ease-out",
              status === "failed" ? "bg-red-500" : "bg-brand-600 dark:bg-app-accent"
            ].join(" ")}
            role="progressbar"
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="mt-1 text-right text-[11px] font-medium text-slate-500">{Math.round(progress)}%</p>
      </div>

      <div className="mt-2 divide-y divide-slate-100">
        {steps.map((step, index) => {
          const state = getStepState(index, activeStepIndex, progress, step.progress, status);
          return (
            <div
              key={step.label}
              className="flex items-center gap-2.5 py-1.5"
            >
              <StepIcon state={state} />
              <div className="min-w-0 flex-1">
                <p
                  className={[
                    "text-[12px] font-medium",
                    state === "done" ? "text-slate-800" : state === "active" ? "text-brand-700 dark:text-app-accent" : "text-slate-500"
                  ].join(" ")}
                >
                  {step.label}
                </p>
              </div>
              {state === "active" ? <span className="shrink-0 whitespace-nowrap text-[11px] font-medium text-brand-700 dark:text-app-accent">진행</span> : null}
            </div>
          );
        })}
      </div>

      {jobStatus?.stt_seconds || jobStatus?.summary_seconds ? (
        <div className="mt-2 grid gap-1 text-[11px] font-medium text-slate-500">
          {jobStatus.stt_seconds ? <span>내용 정리 {formatDuration(jobStatus.stt_seconds)}</span> : null}
          {jobStatus.summary_seconds ? <span>회의록 작성 {formatDuration(jobStatus.summary_seconds)}</span> : null}
        </div>
      ) : null}
    </section>
  );
}

type StepState = "active" | "done" | "pending";

function getReportedProgress(status: JobStatus, jobStatus: JobStatusResponse | null): number {
  if (status === "idle") {
    return 0;
  }
  if (status === "completed") {
    return 100;
  }
  const chunkProgress = isChunkProgressActive(jobStatus) ? getChunkProgress(jobStatus) : null;
  if (chunkProgress !== null) {
    return chunkProgress;
  }
  return jobStatus?.progress ?? 5;
}

function getMinimumProgress(status: JobStatus, reportedProgress: number, stage: string): number {
  if (status === "completed") {
    return 100;
  }
  if (status === "failed") {
    return reportedProgress;
  }
  if (status === "pending") {
    return Math.max(reportedProgress, 10);
  }
  if (status === "processing") {
    if (stage.includes("Transcript 정리")) {
      return Math.max(reportedProgress, 90);
    }
    if (stage.includes("결과 정리")) {
      return Math.max(reportedProgress, 88);
    }
    if (stage.includes("회의록 작성") || stage.includes("요약")) {
      return Math.max(reportedProgress, 25);
    }
    if (stage.includes("음성 변환")) {
      return Math.max(reportedProgress, 10);
    }
    return Math.max(reportedProgress, 15);
  }
  return reportedProgress;
}

function getVisibleProgress(status: JobStatus, visibleProgress: number, reportedProgress: number, stage: string): number {
  if (status === "completed") {
    return 100;
  }
  if (status === "idle") {
    return 0;
  }
  return Math.max(getMinimumProgress(status, reportedProgress, stage), Math.min(visibleProgress, 99));
}

function getOptimisticProgressCap(jobStatus: JobStatusResponse | null, status: JobStatus): number {
  if (status === "pending") {
    return 10;
  }
  const chunkProgress = isChunkProgressActive(jobStatus) ? getChunkProgress(jobStatus) : null;
  if (chunkProgress !== null) {
    return Math.min(80, chunkProgress + 2);
  }

  const stage = jobStatus?.stage ?? "";
  if (stage.includes("회의록 작성") || stage.includes("요약")) {
    return 88;
  }
  if (stage.includes("결과 정리")) {
    return 95;
  }
  if (stage.includes("Transcript 정리")) {
    return 90;
  }
  if (stage.includes("음성 변환")) {
    return 80;
  }
  if (stage.includes("파일 준비")) {
    return 10;
  }
  return 70;
}

function getFriendlyStage(stage: string, status: JobStatus): string {
  if (status === "idle") {
    return stage;
  }
  if (status === "failed") {
    return "처리 실패";
  }
  if (status === "completed") {
    return stage;
  }
  if (stage.includes("파일 준비")) {
    return "음성 분석 준비 중";
  }
  if (stage.includes("음성 변환")) {
    return "음성 변환 중";
  }
  if (stage.includes("회의록 작성") || stage.includes("요약")) {
    return "회의 요약 생성 중";
  }
  if (stage.includes("결과 정리") || stage.includes("Transcript 정리")) {
    return "결과 정리 중";
  }
  return stage;
}

function getChunkDetail(jobStatus: JobStatusResponse | null): string {
  if (!isChunkProgressActive(jobStatus) || jobStatus?.completed_chunks == null || !jobStatus.total_chunks || jobStatus.total_chunks <= 1) {
    return "";
  }

  return `음성 변환 중 · ${jobStatus.completed_chunks}/${jobStatus.total_chunks} 구간 완료`;
}

function getChunkProgress(jobStatus: JobStatusResponse | null): number | null {
  if (jobStatus?.completed_chunks == null || !jobStatus.total_chunks || jobStatus.total_chunks <= 0) {
    return null;
  }

  const completedRatio = Math.max(0, Math.min(jobStatus.completed_chunks, jobStatus.total_chunks)) / jobStatus.total_chunks;
  return 10 + Math.round(completedRatio * 70);
}

function isChunkProgressActive(jobStatus: JobStatusResponse | null): boolean {
  return Boolean(jobStatus?.stage.includes("음성 변환") && jobStatus.status !== "completed");
}

/**
 * Returns the step index that should be emphasized as the current user-visible stage.
 */
function getActiveStepIndex(
  steps: Array<{ label: string; progress: number }>,
  progress: number,
  stage: string,
  status: JobStatus
): number {
  if (status === "idle" || status === "completed" || status === "failed") {
    return -1;
  }

  const stageIndex = steps.findIndex((step) => stage.includes(step.label));
  if (stageIndex >= 0) {
    return stageIndex;
  }

  const nextStepIndex = steps.findIndex((step) => progress < step.progress);
  return nextStepIndex >= 0 ? nextStepIndex : steps.length - 1;
}

/**
 * Maps a step to done, active, or pending for the step-based progress UI.
 */
function getStepState(
  index: number,
  activeStepIndex: number,
  progress: number,
  stepProgress: number,
  status: JobStatus
): StepState {
  if (status === "completed" || progress >= stepProgress) {
    return "done";
  }
  if (index === activeStepIndex) {
    return "active";
  }
  return "pending";
}

/**
 * Renders the icon for a step state without changing row size between states.
 */
function StepIcon({ state }: { state: StepState }) {
  if (state === "done") {
    return <CheckCircle2 className="shrink-0 text-brand-600" size={14} />;
  }

  if (state === "active") {
    return <Loader2 className="shrink-0 animate-spin text-brand-600" size={14} />;
  }

  return <Circle className="shrink-0 text-slate-300" size={14} />;
}

/**
 * Formats elapsed seconds into a compact Korean duration.
 */
function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds.toFixed(1)}초`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}분 ${remainingSeconds}초`;
}
