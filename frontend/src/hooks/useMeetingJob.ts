import { useEffect, useRef, useState } from "react";
import {
  createJob,
  createTranscriptJob,
  createTranscriptionJob,
  downloadMinutes,
  getJobResult,
  getJobStatus,
  getTranscriptResult
} from "../api/jobs";
import { JobResult, JobStatus, JobStatusResponse, MeetingType, SttProviderMode, StructuredTranscript, TranscriptResult, TranscriptionMode } from "../api/types";

const POLLING_INTERVAL_MS = 1500;
const ACTIVE_JOB_STORAGE_KEY = "meeting_summarizer.active_job";

type ActiveJobKind = "minutes" | "transcript";

interface ActiveJobSnapshot {
  jobId: string;
  kind: ActiveJobKind;
}

interface StartMeetingJobPayload {
  audioFile: File | null;
  context?: string;
  contextFile: File | null;
  meetingType?: MeetingType;
  sttProvider?: SttProviderMode;
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

function readActiveJobSnapshot(): ActiveJobSnapshot | null {
  if (typeof window === "undefined") {
    return null;
  }

  const rawSnapshot = window.localStorage.getItem(ACTIVE_JOB_STORAGE_KEY);
  if (!rawSnapshot) {
    return null;
  }

  try {
    const parsedSnapshot = JSON.parse(rawSnapshot) as Partial<ActiveJobSnapshot>;
    if (!parsedSnapshot.jobId || (parsedSnapshot.kind !== "minutes" && parsedSnapshot.kind !== "transcript")) {
      window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
      return null;
    }

    return {
      jobId: parsedSnapshot.jobId,
      kind: parsedSnapshot.kind
    };
  } catch {
    window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
    return null;
  }
}

function saveActiveJobSnapshot(snapshot: ActiveJobSnapshot): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(ACTIVE_JOB_STORAGE_KEY, JSON.stringify(snapshot));
}

function clearActiveJobSnapshot(jobId?: string): void {
  if (typeof window === "undefined") {
    return;
  }

  if (!jobId) {
    window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
    return;
  }

  const currentSnapshot = readActiveJobSnapshot();
  if (currentSnapshot?.jobId === jobId) {
    window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
  }
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
  const [recoveryMessage, setRecoveryMessage] = useState("");
  const recoveryStartedRef = useRef(false);

  useEffect(() => {
    if (recoveryStartedRef.current) {
      return;
    }

    recoveryStartedRef.current = true;
    const storedJob = readActiveJobSnapshot();
    if (!storedJob) {
      return;
    }

    void recoverActiveJob(storedJob);
  }, []);

  /**
   * Uploads the selected files and waits until the backend finishes processing.
   */
  async function startMeetingJob({ audioFile, context = "", contextFile, meetingType = "execution" }: StartMeetingJobPayload) {
    if (!audioFile) {
      setError("회의 녹음 파일을 먼저 선택해 주세요.");
      return;
    }

    setError("");
    setJobStatus(null);
    setResult(null);
    setTranscriptResult(null);
    setCompletedFileName("");
    setRecoveryMessage("");
    setStatus("pending");

    try {
      const createdJob = await createJob({ audioFile, context, contextFile, meetingType });
      saveActiveJobSnapshot({ jobId: createdJob.job_id, kind: "minutes" });
      await pollJobUntilComplete(createdJob.job_id);
    } catch (caughtError) {
      setStatus("failed");
      setError(caughtError instanceof Error ? caughtError.message : "처리 중 오류가 발생했습니다.");
    }
  }

  /**
   * Uploads the selected audio and waits until the transcript is ready for review.
   */
  async function startTranscriptionJob({
    audioFile,
    context = "",
    contextFile,
    meetingType = "execution",
    sttProvider = "local_gpu_whisper",
    transcriptionMode = "plain"
  }: StartMeetingJobPayload) {
    if (!audioFile) {
      setError("회의 녹음 파일을 먼저 선택해 주세요.");
      return;
    }

    setError("");
    setJobStatus(null);
    setResult(null);
    setTranscriptResult(null);
    setCompletedFileName("");
    setRecoveryMessage("");
    setStatus("pending");

    try {
      const createdJob = await createTranscriptionJob({ audioFile, context, contextFile, meetingType, sttProvider, transcriptionMode });
      saveActiveJobSnapshot({ jobId: createdJob.job_id, kind: "transcript" });
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
    setRecoveryMessage("");
    setStatus("pending");

    try {
      const createdJob = await createTranscriptJob({ context, filename, meeting_type, structured_transcript, transcript });
      saveActiveJobSnapshot({ jobId: createdJob.job_id, kind: "minutes" });
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
    setRecoveryMessage("");
    clearActiveJobSnapshot();
  }

  async function recoverActiveJob(storedJob: ActiveJobSnapshot) {
    setError("");
    setResult(null);
    setTranscriptResult(null);
    setCompletedFileName("");
    setJobId(storedJob.jobId);
    setStatus("pending");
    setRecoveryMessage("이전 작업 상태를 확인하는 중입니다.");

    try {
      const nextStatus = await getJobStatus(storedJob.jobId);
      setJobStatus(nextStatus);
      setStatus(nextStatus.status);

      if (nextStatus.status === "completed") {
        setRecoveryMessage("진행 중인 작업을 복구했습니다.");
        await loadCompletedJob(storedJob);
        return;
      }

      if (nextStatus.status === "failed") {
        clearActiveJobSnapshot(storedJob.jobId);
        setRecoveryMessage("");
        setStatus("failed");
        setError(nextStatus.error || "이전 작업이 실패했습니다.");
        return;
      }

      setRecoveryMessage("진행 중인 작업을 복구했습니다.");
      if (storedJob.kind === "transcript") {
        await pollTranscriptUntilComplete(storedJob.jobId);
      } else {
        await pollJobUntilComplete(storedJob.jobId);
      }
    } catch (caughtError) {
      clearActiveJobSnapshot(storedJob.jobId);
      setRecoveryMessage("");
      setStatus("idle");
      setJobId("");
      setJobStatus(null);
      setError(caughtError instanceof Error ? caughtError.message : "이전 작업 상태를 복구하지 못했습니다.");
    }
  }

  async function loadCompletedJob(storedJob: ActiveJobSnapshot) {
    if (storedJob.kind === "transcript") {
      const nextTranscript = await getTranscriptResult(storedJob.jobId);
      setTranscriptResult(nextTranscript);
      setCompletedFileName(nextTranscript.filename);
    } else {
      const nextResult = await getJobResult(storedJob.jobId);
      setResult(nextResult);
      setCompletedFileName(nextResult.filename);
    }

    setStatus("completed");
    clearActiveJobSnapshot(storedJob.jobId);
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
        clearActiveJobSnapshot(nextJobId);
        return;
      }

      if (nextStatus.status === "failed") {
        clearActiveJobSnapshot(nextJobId);
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
        clearActiveJobSnapshot(nextJobId);
        return;
      }

      if (nextStatus.status === "failed") {
        clearActiveJobSnapshot(nextJobId);
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
    recoveryMessage,
    startMeetingJob,
    startTranscriptionJob,
    startTranscriptJob,
    status,
    transcriptResult
  };
}
