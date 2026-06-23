# Dead Code And Inactive Paths

This document lists code that exists in the repository but is not active in the current Spark production deployment.

Current Spark production deployment means:

- Backend runs with the local GPU overlay from `docker-compose.local-gpu.yml`.
- `STT_PROVIDER=local_gpu_whisper`.
- User-facing audio flow uses `POST /api/transcriptions`, transcript review, then `POST /api/transcript-jobs`.
- Default transcription mode is `plain`.

## Diarized Mode

Status: inactive in current Spark production. Frontend/API and backend pipeline/provider plumbing has been removed; `transcribe.py` still contains legacy diarized internals.

Why inactive:

- The frontend audio upload flow does not expose a diarized option.
- The frontend no longer sends a `transcription_mode` form field.
- `backend/api/routes.py:create_transcription_job()` no longer accepts a `transcription_mode` form field.
- `backend/services/pipeline.py:run_transcription_pipeline()` always uses plain STT.
- STT providers no longer accept a transcription mode parameter.
- Spark production uses `STT_PROVIDER=local_gpu_whisper`.

Removed locations:

- `frontend/src/api/types.ts`: removed `TranscriptionMode = "plain" | "diarized"`.
- `frontend/src/api/jobs.ts`: stopped sending `transcription_mode`.
- `backend/api/routes.py:create_transcription_job()`: removed the `transcription_mode` form parameter and validation.
- `backend/services/pipeline.py:get_transcription_mode()`: removed environment-driven mode resolution.
- `backend/services/pipeline.py:transcribe_audio_for_review()`: removed diarized branch and plain fallback.
- `backend/services/pipeline.py:normalized_transcript_to_structured_payload()`: removed diarized structured-payload conversion.
- `backend/services/stt/providers.py`: removed `TranscriptionMode` and provider-level mode parameters.

Remaining locations:

- `transcribe.py:transcribe_audio_diarized()`: legacy OpenAI diarized workflow.
- `transcribe.py:diarized_segments_to_utterances()` and `diarized_segments_to_normalized_transcript()`: legacy segment conversion.
- `transcribe.py:call_diarized_transcription_provider*()`: legacy diarized provider call and retry wrappers.
- `transcribe.py:extract_diarized_segments()` and `normalize_diarized_segments()`: legacy response parsing.
- `transcribe.py:get_diarized_transcription_model()`, `get_diarized_chunk_duration_seconds()`, and `get_diarized_chunk_overlap_seconds()`: legacy diarized configuration.

Notes:

- Requests can no longer select `transcription_mode=diarized` through the public backend API.
- Internal environment-driven diarized mode has been removed from the backend pipeline.
- Legacy diarized code remains in `transcribe.py` until the transcription-module cleanup is completed.

## `/jobs` One-Shot Endpoint

Status: removed from the frontend and backend API layer.

Why inactive:

- Current audio UI flow uses transcript review:
  1. `POST /api/transcriptions`
  2. `GET /api/jobs/{job_id}/transcript`
  3. `POST /api/transcript-jobs`
  4. `GET /api/jobs/{job_id}/result`
- `frontend/src/pages/UploadPage.tsx` starts audio jobs through `startTranscriptionJob()`, not the one-shot minutes job.
- The one-shot endpoint skipped transcript review, which is not the current product flow.

Removed locations:

- `backend/api/routes.py:create_process_job()` no longer defines `POST /api/jobs`.
- `frontend/src/api/jobs.ts:createJob()` was removed.
- `frontend/src/hooks/useMeetingJob.ts:startMeetingJob()` was removed.
- `backend/services/pipeline.py:run_meeting_pipeline()` was removed.

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
