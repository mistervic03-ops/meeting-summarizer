# Summarization Engine

This document describes the current Meeting Summarizer summarization engine and the remaining direction. It is the active reference for work in `summarization/` and `summarize.py`.

## Product Goal

Meeting Summarizer is an internal meeting-minutes tool for BigxData. The goal is practical Korean meeting summaries with reliable action items, decisions, discussion notes, and warnings, while keeping cost and latency reasonable for internal use.

The most important failure mode is silently omitting a real decision or follow-up item. Hallucination reduction matters, but recall for useful meeting semantics matters just as much.

## Current Product Flow

The current React and FastAPI flow is:

1. `UploadPage`
2. `POST /api/transcriptions`
3. Poll transcription job status
4. `TranscriptPage`
5. User reviews and edits the transcript
6. `POST /api/transcript-jobs`
7. `summarize_transcript()`
8. `ResultPage`

The UI also supports direct text/transcript upload (`텍스트 업로드` mode), which skips STT and sends the provided transcript to the transcript-job summarization path.

Important properties:

- STT and meeting-minutes generation are separated.
- Users can review/edit transcripts before summarization.
- Edited transcripts are treated as the source of truth.
- Meeting type is passed into the summarization policy.
- Plain transcript input does not require speaker labels.

## Current Module Layout

The summarization engine is already split into focused modules:

```text
summarization/
  models.py
  normalization.py
  profiling.py
  prompts.py
  schemas.py
  glossary.py       # 요약 glossary 용어 로딩, 파싱, 길이 제한
  extraction.py
  validation.py
  rendering.py
  openai_utils.py
  chunking.py
  chunk_pipeline.py
  merge.py
  policies.py
  pipeline.py

summarize.py  # backward-compatible facade
```

`summarize.py` intentionally remains as an import-compatible facade. Existing callers and tests may still import public helpers from `summarize`.

## Current Pipeline

`summarization.pipeline.summarize_transcript()` currently runs:

```text
preprocess_transcript
-> normalize_transcript
-> analyze_transcript_profile
-> choose_processing_strategy
-> extract_structure or extract_structure_by_chunks
-> apply_extraction_policy
-> validate_structure
-> generate_minutes
-> render_output
-> build_summary_result
```

### 1. Preprocess and Normalize

`preprocess_transcript()`:

- removes only standalone filler tokens
- preserves meaningful context
- merges consecutive utterances from the same speaker
- extracts meeting date information

`normalize_transcript()`:

- creates stable utterance records
- assigns `utterance_id`
- preserves speaker labels when present
- supports speakerless plain transcripts with `Unknown`

### 2. Profile and Strategy Selection

`analyze_transcript_profile()` measures transcript complexity, including utterance count, speaker count, and cue density.

`choose_processing_strategy()` selects:

- `direct`
- `chunk`
- `deep`

Deep mode currently uses the chunk pipeline rather than a separate heavy architecture.

### 3. Structured Extraction

Direct mode calls `extract_structure()`.

Chunk/deep mode calls `extract_structure_by_chunks()`, then merges chunk outputs.

The model-facing schema returns:

- `summary_facts`
- `decisions`
- `action_items`
- `speaker_highlights`
- `warnings`

Internally, decisions and action items include:

- `source_quote`
- `source_utterance_ids`

These grounding fields are used for validation but are not exposed in the public API result.

### 4. Policy and Validation

`apply_extraction_policy()` applies meeting-type-specific rules and can downgrade weak action/decision candidates to discussion notes.

`validate_structure()` performs deterministic Python checks:

- required shape normalization
- owner/due date normalization
- decision status normalization
- source quote verification
- source utterance reference checks
- duplicate handling
- stale warning cleanup
- user-facing warning formatting

### 5. Minutes Generation and Rendering

`generate_minutes()` asks the summary model to write natural Korean minutes from the validated structure and transcript context.

`render_output()` renders critical operational sections from structured data, not from free-form prose alone.

`build_summary_result()` maps the internal result into the public response shape:

- `minutes`
- `action_items`
- `summary_facts`
- `decisions`
- `speaker_highlights`
- `warnings`

Public action items and decisions intentionally hide `source_quote` and `source_utterance_ids` until the API/UI explicitly supports exposing them.

## Current Constraints

- Keep `summarize_transcript()` compatible.
- Keep the public `SummaryResult` shape stable.
- Keep transcript review before summarization.
- Keep deterministic rendering of critical sections.
- Keep meeting-type policy behavior centralized.
- Do not add enterprise orchestration for summarization.

## Remaining Future Work

The main remaining direction is not broad modularization; that is already done. Remaining work should be targeted:

- add a lightweight coverage audit for strong transcript cues that were not represented in extracted candidates
- refine chunk/deep thresholds based on real meeting fixtures
- decide whether public UI should expose source evidence
- expand structured fields only when product usage justifies it, for example `open_questions`, `risks`, `requirements`, `blockers`, or `dependencies`
- continue improving warning quality without exposing internal field names

## Working Guidance

When changing summarization:

- Prefer small behavior changes with focused tests.
- Preserve `summarize.py` facade compatibility unless intentionally migrating callers.
- Keep OpenAI request helpers in `openai_utils.py`.
- Keep prompt-only changes in `prompts.py`.
- Keep deterministic checks in `validation.py`.
- Keep output shaping in `rendering.py`.
- Do not mix file movement with behavior changes.
