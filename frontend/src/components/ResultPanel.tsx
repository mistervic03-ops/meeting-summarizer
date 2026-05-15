import React from "react";
import { JobResult } from "../api/types";

interface ResultPanelProps {
  result: JobResult | null;
  onDownload: () => void;
}

export function ResultPanel({ result, onDownload }: ResultPanelProps) {
  if (!result) {
    return <p className="empty-state">처리가 완료되면 이곳에서 회의록을 확인할 수 있습니다.</p>;
  }

  return (
    <div className="minutes-preview">
      <div className="result-actions">
        <button type="button" onClick={() => navigator.clipboard.writeText(result.minutes)}>
          회의록 복사
        </button>
        <button type="button" onClick={onDownload}>
          txt 다운로드
        </button>
      </div>
      <pre>{result.minutes}</pre>
    </div>
  );
}
