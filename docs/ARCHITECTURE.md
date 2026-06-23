# Architecture

This document describes the current repository structure and production data flow.

## Directory Structure

- `backend/`: FastAPI application, API routes, request/response schemas, session handling, storage, and job orchestration.
- `backend/api/`: HTTP route definitions for health checks, uploads, transcript jobs, meeting history, results, and downloads.
- `backend/services/`: Backend service layer that connects API jobs to STT and summarization.
- `backend/services/stt/`: STT provider abstraction and local GPU Whisper runtime.
- `frontend/`: React + TypeScript + Vite application served by nginx in Docker production builds.
- `frontend/src/`: Upload, transcript review, result, history UI, API client helpers, components, and export utilities.
- `summarization/`: Meeting-minutes engine for transcript normalization, profiling, extraction, validation, rendering, policies, glossary, and LLM provider selection.
- `tests/`: Unit tests for backend structured transcript handling, chunking, summarization, transcription helpers, CLI behavior, and utilities.
- `config/`: STT vocabulary and summary glossary configuration files.
- `docs/`: Architecture, deployment, summarization, and dead-code documentation.
- `tools/`: Operational or evaluation helpers, including Whisper evaluation scripts.
- `assets/`: Static assets used by the project.

## Top-Level Runtime Files

- `main.py`: CLI entry point.
- `transcribe.py`: Shared plain STT workflow, audio preparation, chunking, OpenAI STT calls, and provider selection.
- `summarize.py`: Backward-compatible facade for the `summarization/` package.
- `utils.py`: Audio file validation, format detection, temporary file cleanup, and chunk splitting helpers.
- `docker-compose.yml`: Base Docker Compose stack.
- `docker-compose.local-gpu.yml`: Spark local GPU STT overlay that enables `STT_PROVIDER=local_gpu_whisper`.
- `Dockerfile.backend`: Base backend image.
- `Dockerfile.backend.local-gpu`: NGC PyTorch backend image for local GPU Whisper.
- `Dockerfile.frontend`: React build and nginx serving image.

## Data Flow: Audio Upload To Final Minutes

### 1. Audio Upload

- UI entry: `frontend/src/pages/UploadPage.tsx`.
- API client: `frontend/src/api/jobs.ts` calls `POST /api/transcriptions`.
- Backend route: `backend/api/routes.py:create_transcription_job()`.
- Upload storage: `backend/storage.py:save_upload_file()` stores the uploaded audio in the temporary job area.
- Job state: `backend/storage.py:create_job()`, `set_job_context()`, and `set_job_meeting_type()` initialize in-memory job state.

### 2. STT Processing

- Route schedules `backend/services/pipeline.py:run_transcription_pipeline()` as a background task.
- `run_transcription_pipeline()` calls `transcribe_audio_for_review()`.
- Plain production path calls `transcribe.py:transcribe_audio()` with the selected provider.
- Provider selection is implemented in `backend/services/stt/providers.py:get_stt_provider()`.
- Spark production default is `LocalGpuWhisperProvider`, implemented in `backend/services/stt/providers.py` and backed by `backend/services/stt/transformers_whisper.py`.
- Local GPU Whisper reuses shared audio preparation and plain chunk concurrency from `transcribe.py`.
- Chunk progress is reported through `backend/services/pipeline.py:build_chunk_progress_callback()` and `backend/storage.py:mark_job_chunk_progress()`.

### 3. Transcript Review

- STT output is saved by `backend/services/pipeline.py:run_transcription_pipeline()` through `backend/storage.py:mark_job_transcribed()`.
- The frontend polls `GET /api/jobs/{job_id}` and then fetches `GET /api/jobs/{job_id}/transcript`.
- Review UI entry: `frontend/src/pages/TranscriptPage.tsx`.
- Optional speaker-name edits are applied client-side before submitting the reviewed transcript.

### 4. Summarization Job

- API client: `frontend/src/api/jobs.ts` calls `POST /api/transcript-jobs`.
- Backend route: `backend/api/routes.py:create_transcript_process_job()`.
- Reviewed transcripts can include `transcription_job_id` so the generated minutes job updates the original STT meeting history row instead of inserting a duplicate row.
- Route schedules `backend/services/pipeline.py:run_transcript_summary_pipeline()`.
- Structured transcript payloads, when present, are converted by `summarization/normalization.py:structured_transcript_payload_to_normalized_transcript()`.
- The pipeline calls `summarize.py:summarize_transcript()`, which delegates to `summarization/pipeline.py:summarize_transcript()`.
- Summarization progress is reported through a summary progress callback, then exposed through the same `GET /api/jobs/{job_id}` polling status fields used by the frontend progress panel.

### 5. Summarization Engine

`summarization/pipeline.py:summarize_transcript()` runs:

1. `summarization/normalization.py:preprocess_transcript()`
2. `summarization/normalization.py:normalize_transcript()`
3. `summarization/profiling.py:analyze_transcript_profile()`
4. `summarization/profiling.py:choose_processing_strategy()`
5. `summarization/extraction.py:extract_structure()` or `summarization/chunk_pipeline.py:extract_structure_by_chunks()`
6. `summarization/policies.py:apply_extraction_policy()`
7. `summarization/validation.py:validate_structure()`
8. `summarization/pipeline.py:generate_minutes()`
9. `summarization/rendering.py:render_output()`
10. `summarization/rendering.py:build_summary_result()`

### 6. Result And Export

- Backend completion: `backend/services/pipeline.py:run_transcript_summary_pipeline()` calls `backend/storage.py:mark_job_completed()`.
- Text artifacts are written through `backend/storage.py:save_text_artifacts()`.
- Frontend polls `GET /api/jobs/{job_id}` and fetches `GET /api/jobs/{job_id}/result`.
- Result UI entry: `frontend/src/pages/ResultPage.tsx`.
- Result tabs/components live under `frontend/src/components/`.
- Download endpoint: `backend/api/routes.py:download_minutes()` serves `GET /api/jobs/{job_id}/download`.
- History deletion: `frontend/src/pages/HistoryPage.tsx` calls `DELETE /api/meetings/{meeting_id}` to remove a saved meeting row and its transcript/summary artifacts for the current session.
- Frontend export helpers are in `frontend/src/utils/exportDocument.ts`.

## Direct Text Upload Flow

The UI also supports text/transcript upload mode from `frontend/src/pages/UploadPage.tsx`.

- Text mode skips STT and transcript review.
- The frontend calls `POST /api/transcript-jobs` through `frontend/src/api/jobs.ts:createTranscriptJob()`.
- Backend processing then continues from `backend/services/pipeline.py:run_transcript_summary_pipeline()`.
