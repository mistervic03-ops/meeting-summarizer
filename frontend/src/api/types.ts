export type JobStatus = "idle" | "pending" | "processing" | "completed" | "failed";

export interface CreateJobResponse {
  job_id: string;
  status: Exclude<JobStatus, "idle">;
}

export interface JobStatusResponse {
  job_id: string;
  status: Exclude<JobStatus, "idle">;
  filename: string;
  created_at: string;
  completed_at?: string | null;
  error?: string | null;
}

export interface JobResult {
  job_id: string;
  filename: string;
  transcript?: string;
  minutes: string;
  action_items?: ActionItem[];
  summary_facts?: string[];
  decisions?: Decision[];
  speaker_highlights?: string[];
  warnings?: string[];
}

export interface CreateJobPayload {
  audioFile: File;
  contextFile?: File | null;
}

export interface ActionItem {
  task: string;
  owner: string;
  due_date: string;
  confidence: "high" | "low";
}

export interface Decision {
  decision: string;
  status: "확정" | "미확정";
}
