# Summarization Module Plan

This document describes a safe modularization plan for `summarize.py`.

It is a planning document only. It does not require immediate code movement, API changes, frontend changes, chunking, or public response shape changes.

## 1. Current `summarize.py` Responsibilities

`summarize.py` currently acts as the full summarization engine. It contains several responsibilities that are useful, but increasingly mixed:

- Normalization
  - Transcript parsing.
  - Speaker detection.
  - standalone filler removal.
  - same-speaker utterance merge.
  - meeting date extraction.
  - normalized utterance and `utterance_id` groundwork.
- Profiling
  - `TranscriptProfile`.
  - cue constants and cue counting.
  - complexity estimation.
  - Direct / Chunk / Deep strategy selection groundwork.
  - calibration logging.
- Schema
  - Structured Output JSON schema for `summary_facts`, `decisions`, `action_items`, `speaker_highlights`, and `warnings`.
  - Internal `source_quote` fields for grounding.
- Prompts
  - system prompts.
  - extraction prompt builder.
  - minutes-generation prompt builder.
  - context prefix builder.
- Extraction
  - `extract_structure()`.
  - structured extraction request.
  - model selection for structure extraction.
- Validation
  - `validate_structure()`.
  - owner, due date, confidence, status, and `source_quote` normalization.
  - duplicate merge.
  - source quote verification.
- Warning filtering
  - model warning filtering.
  - stale warning detection.
  - validation-derived warning preservation.
- OpenAI response parsing
  - client creation.
  - response text extraction.
  - response JSON extraction.
  - response content traversal helpers.
- Minutes generation
  - `generate_minutes()`.
  - model selection for final prose generation.
  - natural Korean minutes request.
- Rendering
  - warning rendering.
  - quick summary rendering.
  - structured action item rendering.
  - generated action-item section removal.
  - public `SummaryResult` mapping.
- Orchestration
  - `summarize_transcript()`.
  - timed stage execution.
  - pipeline logging.
  - backwards-compatible `summarize_meeting()`.

## 2. Guiding Principle

The file being long is a signal, but it is not the core problem by itself.

The real problem is responsibility mixing:

- Prompt changes are near rendering logic.
- OpenAI response parsing is near transcript cleanup.
- validation and warning filtering are coupled to public result mapping.
- future chunking, merge, and coverage audit would add new responsibilities into an already dense module.

The modularization goal should therefore be separation by responsibility, not simply reducing line count.

A smaller file is only useful if it also creates clearer ownership, easier tests, and fewer accidental cross-stage changes.

## 3. Recommended Target Structure

Recommended future package layout:

```text
summarization/
  __init__.py
  models.py
  normalization.py
  profiling.py
  prompts.py
  schemas.py
  extraction.py
  validation.py
  rendering.py
  openai_utils.py
  pipeline.py

summarize.py  # backward-compatible facade
```

`summarize.py` should remain import-compatible during migration. Existing callers should still be able to import:

- `summarize_transcript`
- `summarize_meeting`
- current public helpers used by tests or backend code

## 4. Module Roles

### `models.py`

Owns shared internal and public type definitions:

- `TranscriptUtterance`
- `NormalizedTranscript`
- `TranscriptProfile`
- `MeetingStructure`
- `SummaryResult`
- future candidate models such as `TranscriptChunk`, `ExtractionCandidate`, and `CoverageWarning`

This module should not import OpenAI clients, prompts, or pipeline functions.

### `normalization.py`

Owns transcript cleanup and deterministic transcript parsing:

- `normalize_transcript()`
- `preprocess_transcript()`
- meeting date extraction
- speaker-line parsing
- standalone filler removal
- same-speaker merge

This module should stay Python-only.

### `profiling.py`

Owns transcript profile analysis and future strategy selection:

- cue constants
- `analyze_transcript_profile()`
- `choose_processing_strategy()`
- `log_transcript_profile()`
- complexity thresholds

This module should stay Python-only and should not trigger strategy execution by itself.

### `schemas.py`

Owns model-facing structured output schemas:

- `MEETING_STRUCTURE_SCHEMA`
- schema-specific constants
- future expanded schemas for candidates, chunks, or coverage warnings

This module should not know about rendering or backend API models.

### `prompts.py`

Owns prompt text and prompt builders:

- `STRUCTURE_SYSTEM_PROMPT`
- `MINUTES_SYSTEM_PROMPT`
- `build_extraction_prompt()`
- `build_minutes_prompt()`
- `build_context_prompt_prefix()`

Prompt-only changes should be isolated here so they do not accidentally affect validation or rendering logic.

### `extraction.py`

Owns structured extraction calls:

- `extract_structure()`
- `request_structured_structure()`
- future `extract_candidates()`
- future chunk-level extraction entry points

This module can depend on `schemas.py`, `prompts.py`, and `openai_utils.py`.

### `validation.py`

Owns deterministic structure validation:

- `validate_structure()`
- `ensure_structure_shape()`
- `normalize_action_owner()`
- `source_quote_in_transcript()`
- duplicate merge helpers
- warning filtering helpers
- source quote normalization and verification helpers

This module should be Python-only and should not call OpenAI.

### `rendering.py`

Owns deterministic output shaping:

- `render_output()`
- `build_summary_result()`
- public action item and decision mapping
- markdown section rendering helpers

This module should not call OpenAI and should not perform extraction.

### `openai_utils.py`

Owns OpenAI client and response helpers:

- `create_openai_client()`
- `get_structure_model()`
- `get_summary_model()`
- `extract_response_text()`
- `extract_response_json()`
- response content traversal helpers

This module should be the only place that understands common OpenAI response object shapes.

### `pipeline.py`

Owns summarization orchestration:

- `summarize_transcript()`
- timed stage execution
- profile logging placement
- Direct / Chunk / Deep branching later
- final call order

This module can depend on the other engine modules, but lower-level modules should not import `pipeline.py`.

### `summarize.py`

Eventually becomes a backward-compatible facade:

```python
from summarization.pipeline import summarize_transcript
from summarization.pipeline import summarize_meeting
```

During migration it may also re-export public helpers that tests or legacy callers still import.

## 5. Step-by-Step Separation Order

### Step A: Split `models.py`, `schemas.py`, and `prompts.py`

Move low-risk constants and type definitions first.

Why first:

- These modules should have few dependencies.
- They help reveal import boundaries early.
- Tests can still import through `summarize.py` facade.

Main risks:

- accidentally changing schema identity or prompt text.
- missing re-exports for tests.
- import cycles if models import behavior modules.

### Step B: Split `validation.py`

Move validation and warning filtering next.

Why second:

- Validation is already a major independent responsibility.
- It is Python-only and heavily testable.
- Future chunk merge and coverage audit will depend on it.

Main risks:

- `ensure_structure_shape()` and rendering both need the same normalized shape.
- warning tests may fail if helper imports are not preserved.
- source quote helpers must remain internal and not leak into API output.

### Step C: Split `normalization.py` and `profiling.py`

Move transcript normalization and profile/strategy helpers.

Why third:

- Chunking depends on normalized utterances and profile analysis.
- These modules are Python-only.
- They should be independent from OpenAI and prompts.

Main risks:

- `preprocess_transcript()` compatibility.
- exact text output changes.
- meeting date behavior changes.
- profile logging accidentally triggering extra pipeline changes.

### Step D: Split `rendering.py`

Move markdown rendering and public `SummaryResult` mapping.

Why fourth:

- Rendering is deterministic and can be tested without OpenAI.
- It should be separated before output expansion adds risks, blockers, or requirements.

Main risks:

- public API shape regressions.
- frontend expectations around `minutes`, `action_items`, `decisions`, and `warnings`.
- accidentally exposing internal `source_quote`.

### Step E: Split `extraction.py` and `openai_utils.py`

Move OpenAI-facing extraction and response parsing later.

Why later:

- OpenAI mock tests are more sensitive to import paths.
- response parsing helpers are shared by extraction and minutes generation.
- model getters and client creation need stable patch points for tests.

Main risks:

- mock paths in tests break.
- environment variable behavior changes.
- OpenAI response parsing behavior changes unintentionally.

### Step F: Move orchestration to `pipeline.py`

Move `summarize_transcript()` after lower-level responsibilities are stable.

Why near the end:

- Orchestration depends on nearly every other module.
- Moving it too early can force broad import churn.

Main risks:

- backend pipeline import compatibility.
- `summarize_meeting()` compatibility.
- logging behavior changes.
- stage order regressions.

### Step G: Reduce `summarize.py` to a facade

Keep `summarize.py` as the compatibility boundary.

Responsibilities:

- re-export `summarize_transcript()`.
- re-export `summarize_meeting()`.
- optionally re-export tested helper functions during a transition period.

Main risks:

- deleting re-exports before callers/tests are migrated.
- breaking CLI, Streamlit, FastAPI, or ad hoc scripts that import from `summarize`.

## 6. Cross-Cutting Risks

### Circular imports

Likely cycle risks:

- `validation.py` importing rendering helpers.
- `rendering.py` importing pipeline helpers.
- `prompts.py` importing extraction helpers.
- `openai_utils.py` importing extraction or pipeline code.

Mitigation:

- Keep dependency direction one-way:
  - `models.py` at the bottom.
  - pure helpers above models.
  - OpenAI utilities separate.
  - `pipeline.py` imports others, others do not import `pipeline.py`.

### Test import paths

Existing tests import `summarize` directly. Changing every test import at once creates noise.

Mitigation:

- Keep `summarize.py` facade exports until module migration is complete.
- Adjust tests one area at a time.
- Prefer testing public compatibility through `summarize` and new internals through their target modules only after each split is stable.

### Public API compatibility

Backend and frontend depend on the public summary result shape.

Mitigation:

- Keep `SummaryResult` fields stable:
  - `minutes`
  - `action_items`
  - `summary_facts`
  - `decisions`
  - `speaker_highlights`
  - `warnings`
- Do not expose `source_quote` until the API and UI intentionally support it.

### Backend pipeline import compatibility

`backend/services/pipeline.py` currently calls the existing summarization entry point.

Mitigation:

- Keep `from summarize import summarize_transcript` working.
- Do not require backend import changes during early module splits.

### OpenAI mock tests

Tests patch `create_openai_client()`, request helpers, model getters, and response parsing behavior.

Mitigation:

- Move OpenAI-facing code late.
- Preserve patchable names through `summarize.py` during transition.
- After `openai_utils.py` split, update tests in one focused change.

## 7. Migration Principles

- Do not split the entire file in one step.
- Do not mix behavior changes with file moves.
- Run tests after every separation step.
- Keep `summarize_transcript` import compatibility throughout migration.
- Keep the existing public `SummaryResult` shape stable.
- Keep backend and frontend unchanged unless a later product task explicitly requires it.
- Move one responsibility group at a time.
- Preserve existing tests first; only adjust imports that are necessary for the current split.
- If a behavior change is needed, do it before or after the move, not in the same change.
- Prefer Python-only module splits before OpenAI-facing module splits.

## 8. Chunking Before or After Modularization

There are two reasonable options before implementing conditional chunking.

### Option 1: Split core modules before chunking

Minimum recommended split before chunking:

- `models.py`
- `schemas.py`
- `prompts.py`
- `validation.py`
- `profiling.py`

Pros:

- chunking has cleaner dependencies.
- chunk extraction can reuse schemas/prompts without growing `summarize.py`.
- merge and coverage audit can reuse validation models.
- future tests are easier to target.

Cons:

- delays chunking implementation slightly.
- import churn must be handled carefully.

### Option 2: Add chunking as a new module first

Create a new `summarization/chunking.py` or `chunking.py` and call it from current `summarize.py`.

Pros:

- avoids a broad module migration before proving chunk behavior.
- keeps the chunking change isolated if it is still experimental.
- lower initial risk to existing imports.

Cons:

- `summarize.py` remains the central dependency hub.
- chunking may need to import types and helpers from `summarize.py`, which can make later splitting harder.
- future merge/audit code may deepen the same-file coupling.

### Safer Strategy

For this project, Option 1 is safer if the next work is a sustained refactor.

If chunking must be delivered immediately, Option 2 is acceptable only if chunking is isolated and does not move existing behavior at the same time.

## 9. Final Recommendation

Do not split the entire summarization engine immediately.

Recommended next implementation path:

1. Before Step 3, split `models.py`, `schemas.py`, `prompts.py`, and `validation.py`.
2. Keep `summarize.py` as a compatibility facade during each split.
3. Add chunking as a new module once the basic boundaries are stable.
4. Keep `summarize_transcript()` behavior and public result shape unchanged during module movement.
5. Gradually move orchestration into `pipeline.py` only after normalization, profiling, validation, rendering, and OpenAI utilities are stable.

This keeps the project pragmatic:

- normal meetings continue to use the current direct path.
- tests remain useful during migration.
- source grounding and validation stay protected.
- chunking can be added without turning `summarize.py` into a larger mixed-responsibility file.
