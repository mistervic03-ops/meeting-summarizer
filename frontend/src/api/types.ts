export type JobStatus = "idle" | "pending" | "processing" | "completed" | "failed";
export type SttProviderMode = "local_gpu_whisper" | "openai";
export type MeetingType = "execution" | "customer_meeting" | "technical_review" | "brainstorming" | "general";

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
  progress: number;
  stage: string;
  message: string;
  completed_chunks?: number | null;
  total_chunks?: number | null;
  stt_seconds?: number | null;
  summary_seconds?: number | null;
}

export interface JobResult {
  job_id: string;
  filename: string;
  meeting_type?: MeetingType;
  transcript?: string;
  minutes: string;
  action_items?: ActionItem[];
  summary_facts?: string[];
  decisions?: Decision[];
  speaker_highlights?: string[];
  warnings?: string[];
}

export interface TranscriptResult {
  job_id: string;
  filename: string;
  meeting_type?: MeetingType;
  transcript: string;
  context?: string;
  stt_seconds?: number | null;
}

export interface CreateTranscriptionJobPayload {
  audioFile: File;
  context?: string;
  meetingType?: MeetingType;
  sttProvider?: SttProviderMode;
}

export interface CreateTranscriptJobPayload {
  filename: string;
  transcript: string;
  context?: string;
  meeting_type?: MeetingType;
  transcriptionJobId?: string;
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
