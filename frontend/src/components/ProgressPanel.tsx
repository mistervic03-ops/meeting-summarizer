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
  { label: "파일 준비", progress: 10 },
  { label: "내용 정리", progress: 55 },
  { label: "회의록 작성", progress: 90 },
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
  const progress = status === "idle" ? 0 : jobStatus?.progress ?? 5;
  const stage = jobStatus?.stage ?? (status === "idle" ? idleStage : pendingStage);
  const message = jobStatus?.message ?? (status === "idle" ? idleMessage : pendingMessage);
  const activeStepIndex = getActiveStepIndex(steps, progress, stage, status);

  return (
    <section className="border-y border-slate-300 py-3">
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5 text-slate-400">
          {status === "completed" ? <CheckCircle2 size={15} /> : <Loader2 className={status === "idle" ? "" : "animate-spin"} size={15} />}
        </div>
        <div className="min-w-0">
          <h2 className="text-[12px] font-semibold text-slate-950">{stage}</h2>
          <p className="mt-0.5 break-words text-[11px] leading-4 text-slate-500">{message}</p>
        </div>
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
