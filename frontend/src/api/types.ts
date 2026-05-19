export type JobStatus = "idle" | "pending" | "processing" | "completed" | "failed";
export type SttProviderMode = "local_gpu_whisper" | "openai";
export type TranscriptionMode = "plain" | "diarized";
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
  structured_transcript?: StructuredTranscript | null;
}

export interface CreateJobPayload {
  audioFile: File;
  context?: string;
  contextFile?: File | null;
  meetingType?: MeetingType;
}

export interface CreateTranscriptionJobPayload {
  audioFile: File;
  context?: string;
  contextFile?: File | null;
  meetingType?: MeetingType;
  sttProvider?: SttProviderMode;
  transcriptionMode?: TranscriptionMode;
}

export interface CreateTranscriptJobPayload {
  filename: string;
  transcript: string;
  context?: string;
  meeting_type?: MeetingType;
  structured_transcript?: StructuredTranscript | null;
}

export interface TranscriptUtterance {
  utterance_id?: string | null;
  speaker?: string | null;
  text: string;
  start_ms?: number | null;
  end_ms?: number | null;
}

export interface StructuredTranscript {
  utterances: TranscriptUtterance[];
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
