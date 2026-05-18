import { useState } from "react";
import {
  createJob,
  createTranscriptJob,
  createTranscriptionJob,
  downloadMinutes,
  getJobResult,
  getJobStatus,
  getTranscriptResult
} from "../api/jobs";
import { JobResult, JobStatus, JobStatusResponse, MeetingType, StructuredTranscript, TranscriptResult, TranscriptionMode } from "../api/types";

const POLLING_INTERVAL_MS = 1500;

interface StartMeetingJobPayload {
  audioFile: File | null;
  contextFile: File | null;
  meetingType?: MeetingType;
  transcriptionMode?: TranscriptionMode;
}

interface StartTranscriptJobPayload {
  context?: string;
  filename: string;
  meeting_type?: MeetingType;
  structured_transcript?: StructuredTranscript | null;
  transcript: string;
}

/**
 * Keeps the polling cadence readable while the backend processes the upload.
 */
function waitForNextPoll(): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, POLLING_INTERVAL_MS));
}

/**
 * Handles meeting upload, polling, result loading, and download state.
 */
export function useMeetingJob() {
  const [status, setStatus] = useState<JobStatus>("idle");
  const [error, setError] = useState("");
  const [jobId, setJobId] = useState("");
  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const [transcriptResult, setTranscriptResult] = useState<TranscriptResult | null>(null);
  const [completedFileName, setCompletedFileName] = useState("");

  /**
   * Uploads the selected files and waits until the backend finishes processing.
   */
  async function startMeetingJob({ audioFile, contextFile, meetingType = "execution" }: StartMeetingJobPayload) {
    if (!audioFile) {
      setError("회의 녹음 파일을 먼저 선택해 주세요.");
      return;
    }

    setError("");
    setJobStatus(null);
    setResult(null);
    setTranscriptResult(null);
    setCompletedFileName("");
    setStatus("pending");

    try {
      const createdJob = await createJob({ audioFile, contextFile, meetingType });
      await pollJobUntilComplete(createdJob.job_id);
    } catch (caughtError) {
      setStatus("failed");
      setError(caughtError instanceof Error ? caughtError.message : "처리 중 오류가 발생했습니다.");
    }
  }

  /**
   * Uploads the selected audio and waits until the transcript is ready for review.
   */
  async function startTranscriptionJob({ audioFile, contextFile, meetingType = "execution", transcriptionMode = "plain" }: StartMeetingJobPayload) {
    if (!audioFile) {
      setError("회의 녹음 파일을 먼저 선택해 주세요.");
      return;
    }

    setError("");
    setJobStatus(null);
    setResult(null);
    setTranscriptResult(null);
    setCompletedFileName("");
    setStatus("pending");

    try {
      const createdJob = await createTranscriptionJob({ audioFile, contextFile, meetingType, transcriptionMode });
      await pollTranscriptUntilComplete(createdJob.job_id);
    } catch (caughtError) {
      setStatus("failed");
      setError(caughtError instanceof Error ? caughtError.message : "내용을 준비하는 중 오류가 발생했습니다.");
    }
  }

  /**
   * Starts a meeting minutes job from a reviewed or edited transcript.
   */
  async function startTranscriptJob({
    context = "",
    filename,
    meeting_type = "general",
    structured_transcript = null,
    transcript
  }: StartTranscriptJobPayload) {
    if (!transcript.trim()) {
      setError("회의록을 작성할 내용이 비어 있습니다.");
      return;
    }

    setError("");
    setJobStatus(null);
    setResult(null);
    setTranscriptResult(null);
    setCompletedFileName("");
    setStatus("pending");

    try {
      const createdJob = await createTranscriptJob({ context, filename, meeting_type, structured_transcript, transcript });
      await pollJobUntilComplete(createdJob.job_id);
    } catch (caughtError) {
      setStatus("failed");
      setError(caughtError instanceof Error ? caughtError.message : "회의록 작성 중 오류가 발생했습니다.");
    }
  }

  /**
   * Clears the current job state so another upload can start.
   */
  function resetJobState() {
    setStatus("idle");
    setError("");
    setJobId("");
    setJobStatus(null);
    setResult(null);
    setTranscriptResult(null);
    setCompletedFileName("");
  }

  /**
   * Polls a backend job until the result is ready or a failure is reported.
   */
  async function pollJobUntilComplete(nextJobId: string) {
    setJobId(nextJobId);

    while (true) {
      const nextStatus = await getJobStatus(nextJobId);
      setJobStatus(nextStatus);
      setStatus(nextStatus.status);

      if (nextStatus.status === "completed") {
        const nextResult = await getJobResult(nextJobId);
        setResult(nextResult);
        setCompletedFileName(nextResult.filename);
        return;
      }

      if (nextStatus.status === "failed") {
        throw new Error(nextStatus.error || "회의록 작성을 완료하지 못했습니다.");
      }

      await waitForNextPoll();
    }
  }

  /**
   * Polls a transcription job until the transcript is ready for review.
   */
  async function pollTranscriptUntilComplete(nextJobId: string) {
    setJobId(nextJobId);

    while (true) {
      const nextStatus = await getJobStatus(nextJobId);
      setJobStatus(nextStatus);
      setStatus(nextStatus.status);

      if (nextStatus.status === "completed") {
        const nextTranscript = await getTranscriptResult(nextJobId);
        setTranscriptResult(nextTranscript);
        setCompletedFileName(nextTranscript.filename);
        return;
      }

      if (nextStatus.status === "failed") {
        throw new Error(nextStatus.error || "내용 준비를 완료하지 못했습니다.");
      }

      await waitForNextPoll();
    }
  }

  /**
   * Starts a download for the completed job when one exists.
   */
  function downloadCurrentMinutes() {
    if (jobId) {
      downloadMinutes(jobId);
    }
  }

  return {
    completedFileName,
    downloadCurrentMinutes,
    error,
    jobStatus,
    resetJobState,
    result,
    startMeetingJob,
    startTranscriptionJob,
    startTranscriptJob,
    status,
    transcriptResult
  };
}
