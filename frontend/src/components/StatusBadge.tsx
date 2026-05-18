import React from "react";
import { JobStatus } from "../api/types";

const STATUS_LABELS: Record<JobStatus, string> = {
  idle: "대기",
  pending: "준비 중",
  processing: "진행 중",
  completed: "완료",
  failed: "오류"
};

interface StatusBadgeProps {
  status: JobStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={`status-badge status-${status}`}>{STATUS_LABELS[status]}</span>;
}
