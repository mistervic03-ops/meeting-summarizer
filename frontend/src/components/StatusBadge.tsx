import React from "react";
import { JobStatus } from "../api/types";

const STATUS_LABELS: Record<JobStatus, string> = {
  idle: "대기",
  pending: "준비 중",
  processing: "처리 중",
  completed: "완료",
  failed: "실패"
};

interface StatusBadgeProps {
  status: JobStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={`status-badge status-${status}`}>{STATUS_LABELS[status]}</span>;
}
