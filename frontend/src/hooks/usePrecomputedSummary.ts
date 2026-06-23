import { useCallback, useEffect, useRef, useState } from "react";
import { createTranscriptJob, getJobResult, getJobStatus } from "../api/jobs";
import type { JobResult, JobStatus, MeetingType, TranscriptResult } from "../api/types";

const POLLING_INTERVAL_MS = 1500;

interface PrecomputedSummarySource {
  context: string;
  filename: string;
  meetingType: MeetingType;
  transcript: string;
  transcriptionJobId: string;
}

interface UsePrecomputedSummaryOptions {
  context: string;
  meetingType: MeetingType;
  transcriptResult: TranscriptResult | null;
}

export interface PrecomputedSummaryState {
  getPrecomputedResult: () => JobResult | null;
  isStale: boolean;
  precomputedError: string;
  precomputedResult: JobResult | null;
  precomputedStatus: JobStatus;
}

function waitForNextPoll(): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, POLLING_INTERVAL_MS));
}

function getErrorMessage(caughtError: unknown): string {
  return caughtError instanceof Error ? caughtError.message : "회의록 사전 생성을 완료하지 못했습니다.";
}

export function usePrecomputedSummary({
  context,
  meetingType,
  transcriptResult
}: UsePrecomputedSummaryOptions): PrecomputedSummaryState {
  const [precomputedError, setPrecomputedError] = useState("");
  const [precomputedResult, setPrecomputedResult] = useState<JobResult | null>(null);
  const [precomputedStatus, setPrecomputedStatus] = useState<JobStatus>("idle");
  const [isStale, setIsStale] = useState(false);
  const precomputedResultRef = useRef<JobResult | null>(null);
  const isStaleRef = useRef(false);
  const runIdRef = useRef(0);
  const sourceRef = useRef<PrecomputedSummarySource | null>(null);

  useEffect(() => {
    precomputedResultRef.current = precomputedResult;
  }, [precomputedResult]);

  useEffect(() => {
    isStaleRef.current = isStale;
  }, [isStale]);

  useEffect(() => {
    const source = sourceRef.current;
    if (!source) {
      return;
    }

    setIsStale(source.context !== context || source.meetingType !== meetingType);
  }, [context, meetingType]);

  useEffect(() => {
    if (!transcriptResult) {
      runIdRef.current += 1;
      sourceRef.current = null;
      setPrecomputedError("");
      setPrecomputedResult(null);
      setPrecomputedStatus("idle");
      setIsStale(false);
      return;
    }

    const runId = runIdRef.current + 1;
    runIdRef.current = runId;
    const source: PrecomputedSummarySource = {
      context,
      filename: transcriptResult.filename,
      meetingType,
      transcript: transcriptResult.transcript,
      transcriptionJobId: transcriptResult.job_id
    };
    sourceRef.current = source;
    setPrecomputedError("");
    setPrecomputedResult(null);
    setPrecomputedStatus("pending");
    setIsStale(false);

    let cancelled = false;

    async function startTranscriptJob() {
      try {
        const createdJob = await createTranscriptJob({
          context: source.context,
          filename: source.filename,
          meeting_type: source.meetingType,
          transcript: source.transcript,
          transcriptionJobId: source.transcriptionJobId
        });

        setPrecomputedStatus(createdJob.status);

        while (!cancelled && runIdRef.current === runId) {
          const nextStatus = await getJobStatus(createdJob.job_id);
          if (cancelled || runIdRef.current !== runId) {
            return;
          }

          setPrecomputedStatus(nextStatus.status);

          if (nextStatus.status === "completed") {
            const nextResult = await getJobResult(createdJob.job_id);
            if (!cancelled && runIdRef.current === runId) {
              setPrecomputedResult(nextResult);
              setPrecomputedStatus("completed");
            }
            return;
          }

          if (nextStatus.status === "failed") {
            throw new Error(nextStatus.error || "회의록 사전 생성을 완료하지 못했습니다.");
          }

          await waitForNextPoll();
        }
      } catch (caughtError) {
        if (!cancelled && runIdRef.current === runId) {
          setPrecomputedError(getErrorMessage(caughtError));
          setPrecomputedStatus("failed");
        }
      }
    }

    void startTranscriptJob();

    return () => {
      cancelled = true;
    };
  }, [transcriptResult?.job_id]);

  const getPrecomputedResult = useCallback(() => {
    if (isStaleRef.current) {
      return null;
    }

    return precomputedResultRef.current;
  }, []);

  return {
    getPrecomputedResult,
    isStale,
    precomputedError,
    precomputedResult,
    precomputedStatus
  };
}
