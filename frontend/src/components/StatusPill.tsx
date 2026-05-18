import { JobStatus } from "../api/types";

/**
 * Renders a compact processing state indicator.
 */
export default function StatusPill({ status }: { status: JobStatus }) {
  const labelByStatus: Record<JobStatus, string> = {
    idle: "대기",
    pending: "준비 중",
    processing: "진행 중",
    completed: "완료",
    failed: "오류"
  };

  const toneByStatus: Record<JobStatus, string> = {
    idle: "border-slate-200 bg-white text-slate-500 dark:border-app-line dark:bg-app-rail",
    pending: "border-brand-200 bg-white text-brand-700 dark:border-app-accent-border dark:bg-app-rail dark:text-app-accent",
    processing: "border-brand-200 bg-white text-brand-700 dark:border-app-accent-border dark:bg-app-rail dark:text-app-accent",
    completed: "border-emerald-200 bg-white text-emerald-700 dark:border-app-success-border dark:bg-app-rail",
    failed: "border-red-200 bg-white text-red-700 dark:border-app-danger-border dark:bg-app-rail"
  };

  return (
    <span className={`inline-flex h-6 items-center rounded-md border px-2.5 text-[11px] font-medium leading-none ${toneByStatus[status]}`}>
      {labelByStatus[status]}
    </span>
  );
}
