import { CreateJobPayload, CreateJobResponse, JobResult, JobStatusResponse } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";
const CONNECTION_ERROR_MESSAGE =
  "API 서버에 연결할 수 없습니다. 백엔드 서버가 http://localhost:8000 에서 실행 중인지 확인해 주세요.";

/**
 * Parses an API JSON response and raises a clear message for non-2xx responses.
 */
async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    throw new Error(errorBody?.detail || "API 요청에 실패했습니다.");
  }

  return response.json() as Promise<T>;
}

/**
 * Sends a fetch request and normalizes browser network failures into a helpful API message.
 */
async function fetchJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  try {
    const response = await fetch(input, init);
    return parseJsonResponse<T>(response);
  } catch (caughtError) {
    if (caughtError instanceof TypeError) {
      throw new Error(CONNECTION_ERROR_MESSAGE);
    }

    throw caughtError;
  }
}

/**
 * Creates a meeting processing job from the selected audio and optional context file.
 */
export async function createJob(payload: CreateJobPayload): Promise<CreateJobResponse> {
  const formData = new FormData();
  formData.append("audio_file", payload.audioFile);

  if (payload.contextFile) {
    formData.append("context_file", payload.contextFile);
  }

  return fetchJson<CreateJobResponse>(`${API_BASE_URL}/jobs`, {
    method: "POST",
    body: formData
  });
}

/**
 * Gets the current processing status for a meeting job.
 */
export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  return fetchJson<JobStatusResponse>(`${API_BASE_URL}/jobs/${jobId}`);
}

/**
 * Gets the transcript and generated minutes for a completed meeting job.
 */
export async function getJobResult(jobId: string): Promise<JobResult> {
  return fetchJson<JobResult>(`${API_BASE_URL}/jobs/${jobId}/result`);
}

/**
 * Starts a browser download for the generated minutes file.
 */
export function downloadMinutes(jobId: string): void {
  window.location.href = `${API_BASE_URL}/jobs/${jobId}/download`;
}
