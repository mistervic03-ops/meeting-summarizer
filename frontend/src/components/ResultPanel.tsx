import React from "react";
import { JobResult } from "../api/types";
import { normalizeMarkdownForDisplay } from "../utils/displayText";

interface ResultPanelProps {
  result: JobResult | null;
  onDownload?: () => void;
}

export function ResultPanel({ result }: ResultPanelProps) {
  if (!result) {
    return <p className="empty-state">처리가 완료되면 이곳에서 회의록을 확인할 수 있습니다.</p>;
  }

  const displayMinutes = normalizeMarkdownForDisplay(result.minutes);

  /**
   * Downloads the same cleaned minutes text shown in the preview.
   */
  function handleDownload() {
    const blob = new Blob([displayMinutes], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = "meeting_minutes.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="minutes-preview">
      <div className="result-actions">
        <button type="button" onClick={() => navigator.clipboard.writeText(displayMinutes)}>
          회의록 복사
        </button>
        <button type="button" onClick={handleDownload}>
          txt 다운로드
        </button>
      </div>
      <pre>{displayMinutes}</pre>
    </div>
  );
}
