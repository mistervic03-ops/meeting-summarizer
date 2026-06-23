# Dead Code And Inactive Paths

This document lists code that exists in the repository but is not active in the current Spark production deployment.

Current Spark production deployment means:

- Backend runs with the local GPU overlay from `docker-compose.local-gpu.yml`.
- `STT_PROVIDER=local_gpu_whisper`.
- User-facing audio flow uses `POST /api/transcriptions`, transcript review, then `POST /api/transcript-jobs`.
- Default transcription mode is `plain`.

## Diarized Mode

Status: inactive in current Spark production. Removal is planned and in progress.

Why inactive:

- The frontend audio upload flow does not expose a diarized option and defaults to plain transcription.
- `frontend/src/hooks/useMeetingJob.ts:startTranscriptionJob()` defaults `transcriptionMode` to `plain`.
- `frontend/src/pages/UploadPage.tsx` calls `startTranscriptionJob()` without passing `transcriptionMode`.
- Spark production uses `STT_PROVIDER=local_gpu_whisper`.
- `LocalGpuWhisperProvider` explicitly supports only plain transcription and raises for diarized mode.
- `LocalWhisperProvider` also explicitly supports only plain transcription.

Locations:

- `frontend/src/api/types.ts`: still defines `TranscriptionMode = "plain" | "diarized"`.
- `frontend/src/api/jobs.ts`: still sends `transcription_mode`, defaulting to `plain`.
- `backend/api/routes.py:create_transcription_job()`: still accepts `transcription_mode` values `plain` and `diarized`.
- `backend/services/pipeline.py:get_transcription_mode()`: still resolves `TRANSCRIPTION_MODE` and `ENABLE_DIARIZED_TRANSCRIPTION`.
- `backend/services/pipeline.py:transcribe_audio_for_review()`: still has a diarized branch and plain fallback.
- `backend/services/stt/providers.py`: provider protocol still includes `TranscriptionMode = Literal["plain", "diarized"]`.
- `transcribe.py:transcribe_audio_diarized()`: legacy OpenAI diarized workflow.
- `transcribe.py:diarized_segments_to_utterances()` and `diarized_segments_to_normalized_transcript()`: legacy segment conversion.
- `transcribe.py:call_diarized_transcription_provider*()`: legacy diarized provider call and retry wrappers.
- `transcribe.py:extract_diarized_segments()` and `normalize_diarized_segments()`: legacy response parsing.
- `transcribe.py:get_diarized_transcription_model()`, `get_diarized_chunk_duration_seconds()`, and `get_diarized_chunk_overlap_seconds()`: legacy diarized configuration.

Notes:

- A request can still technically send `transcription_mode=diarized` to the backend API.
- In the Spark local GPU default, that path is not a production path and falls back after provider failure behavior.
- Treat this as legacy residue until the planned removal is completed.

## `/jobs` One-Shot Endpoint

Status: inactive in current user-facing Spark production flow.

Why inactive:

- Current audio UI flow uses transcript review:
  1. `POST /api/transcriptions`
  2. `GET /api/jobs/{job_id}/transcript`
  3. `POST /api/transcript-jobs`
  4. `GET /api/jobs/{job_id}/result`
- `frontend/src/pages/UploadPage.tsx` starts audio jobs through `startTranscriptionJob()`, not the one-shot minutes job.
- The one-shot endpoint skips transcript review, which is not the current product flow.

Locations:

- `backend/api/routes.py:create_process_job()` defines `POST /api/jobs`.
- `backend/services/pipeline.py:run_meeting_pipeline()` performs STT and summarization in one background task.
- `frontend/src/api/jobs.ts:createJob()` still exists as the client helper for `POST /api/jobs`.
- `frontend/src/hooks/useMeetingJob.ts:startMeetingJob()` still exists but is not used by the current upload page audio path.

Notes:

- Keep this separate from `GET /api/jobs/{job_id}`, `GET /api/jobs/{job_id}/result`, and download endpoints, which are active polling/result endpoints.

## `local_whisper` CPU Provider

Status: inactive in current Spark production deployment.

Why inactive:

- Spark production uses `STT_PROVIDER=local_gpu_whisper` through `docker-compose.local-gpu.yml`.
- The API only allows request-level STT overrides for `local_gpu_whisper` and `openai`.
- The frontend exposes only `local_gpu_whisper` and `openai`.
- The CPU provider was retained as an experimental path but did not meet production quality expectations.

Locations:

- `backend/services/stt/providers.py:LocalWhisperProvider`.
- `backend/services/stt/providers.py:get_stt_provider()` still accepts `local_whisper`.
- `.env.example` documents `STT_PROVIDER=local_whisper` as an experimental setting.
- `docs/DEPLOYMENT_SPARK.md` documents CPU local Whisper as experimental and not the production-candidate default.

Notes:

- `local_whisper` is code-reachable only through environment/provider selection outside the current API/UI Spark production path.
- Do not optimize around this provider unless explicitly reviving the CPU path.
