# Summarization Refactor Plan

This document analyzes the current `summarize.py` implementation and proposes a realistic migration path toward the architecture described in `docs/SUMMARIZATION_ENGINE.md`.

This is a planning document only. It does not require immediate logic, API, endpoint, or frontend changes.

## 1. Current Architecture Analysis

### Current `summarize.py` pipeline

The current public entry point is:

```text
summarize_transcript(transcript: str, context: str = "") -> SummaryResult
```

It runs four main stages:

1. `preprocess_transcript()`
2. `extract_structure()`
3. `generate_minutes()`
4. `render_output()`

The pipeline currently returns a `SummaryResult` dictionary with:

- `minutes`
- `action_items`
- `summary_facts`
- `decisions`
- `speaker_highlights`
- `warnings`

This shape is consumed by FastAPI storage and response models, so it is an important compatibility boundary.

### `preprocess_transcript()`

Current role:

- Parses transcript lines into speaker-aware utterances.
- Removes only standalone filler utterances.
- Merges consecutive utterances from the same speaker.
- Extracts a meeting date for relative due-date interpretation.

Strengths:

- The filler removal is intentionally conservative. It removes tokens such as `아`, `음`, `네네`, and `어` only when they are standalone after punctuation and spacing normalization.
- It avoids deleting filler-like words inside meaningful context, such as "네네 확인했습니다".
- It keeps the summarization input cleaner without changing the meaning of normal utterances.
- It already has a useful internal `Utterance` dataclass, which can evolve into richer utterance normalization later.

Parts to preserve:

- Conservative filler handling.
- Speaker-line parsing.
- Same-speaker merge behavior, unless future `utterance_id` work requires preserving raw utterance boundaries separately.
- Meeting-date extraction as an early deterministic step.

### `extract_structure()`

Current role:

- Builds an extraction prompt from cleaned transcript text, meeting date, and optional context.
- Calls GPT-4o-mini with Structured Output.
- Extracts `summary_facts`, `decisions`, `action_items`, `speaker_highlights`, and `warnings`.

Strengths:

- Structured extraction is separated from prose generation.
- The schema already prevents arbitrary top-level fields.
- The prompt asks for factual extraction and warns against unsupported inference.
- It already captures low-confidence action items and warnings in a simple form.
- It uses a lower-cost model for extraction, which fits the internal-tool cost profile.

Parts to preserve:

- Use a cheaper model for structured extraction by default.
- Keep structured extraction before prose generation.
- Keep context injection support.
- Keep schema-constrained output as the first line of defense.

### `generate_minutes()`

Current role:

- Builds a Korean meeting-minutes prompt from the preprocessed transcript and structured JSON.
- Calls the summary model.
- Treats structured JSON as verified facts.

Strengths:

- Prose generation is conceptually downstream of structured facts.
- The prompt explicitly says not to invent decisions, owners, deadlines, or action items.
- It supports optional context without changing the public interface.

Parts to preserve:

- `generate_minutes()` should remain a prose/documentation step, not the primary fact-discovery step.
- It should continue to receive structured facts and transcript context.
- It should remain replaceable without changing API endpoints.

### `render_output()`

Current role:

- Normalizes structure shape.
- Removes the model-generated `액션 아이템` section from generated minutes.
- Renders warnings, quick summary, structured action items, and full minutes into final Markdown.

Strengths:

- Structured action items are rendered directly from structured data, not copied from free-form prose.
- This reduces the chance that generated prose can invent or reshape action items.
- It gives warnings and low-confidence items visible placement.
- It is a practical bridge between model output and deterministic display.

Parts to preserve:

- Critical operational sections should keep being rendered from structured data.
- `render_output()` should remain deterministic and simple.
- Generated minutes should not be allowed to override structured action items.

### FastAPI summary call flow

Current summary-related API flow:

```text
UploadPage
-> POST /api/transcriptions
-> polling
-> TranscriptPage
-> user transcript edit/review
-> POST /api/transcript-jobs
-> run_transcript_summary_pipeline()
-> summarize_transcript()
-> ResultPage
```

Important current design points:

- Transcript review and edit happen before summary generation.
- `backend/services/pipeline.py` calls `summarize_transcript(transcript, context=context)`.
- `/api/transcript-jobs` accepts the reviewed transcript and creates the summary job.
- `backend/storage.py` stores only the API-facing summary fields.
- `backend/schemas.py` exposes the existing response shape to the frontend.

This is a good product flow and should remain stable during refactoring.

## 2. Current Weaknesses

### Single `extract_structure()` call

The current implementation sends the full cleaned transcript to one structured extraction call. This is simple and cost-efficient, but it becomes less reliable as transcripts get longer.

Risks:

- Important action items can be missed in long meetings.
- Late-meeting decisions may be underrepresented.
- Model attention can drift toward broad summary facts instead of operational details.
- A single malformed or weak extraction result affects the whole output.

### Long transcript stability

There is no transcript profile step today. The pipeline does not estimate size, speaker count, cue density, or complexity before choosing a strategy.

Risks:

- Small and long meetings receive the same processing strategy.
- Long transcripts may exceed practical quality limits before they hit hard context limits.
- The system cannot decide when extra cost is justified.

### Evidence and `source_quote` absence

Action items and decisions do not currently include transcript evidence.

Risks:

- The system cannot verify whether an item came from the transcript.
- Users cannot trace uncertain items back to source wording.
- Validation is limited because Python cannot compare extracted facts against quoted evidence.

### Hallucination defense limits

Current hallucination protection relies mostly on:

- Prompt instructions.
- Structured Output schema.
- Basic shape normalization.
- Deterministic rendering of action items.

This is helpful, but it does not verify semantic grounding.

Risks:

- A valid schema can still contain unsupported facts.
- A fluent generated minutes section can overstate uncertain points.
- Missing evidence cannot be detected after extraction.

### Validation layer gaps

Current deterministic validation is lightweight:

- `ensure_structure_shape()` checks expected list fields.
- `build_summary_result()` normalizes owner, due date fallback, decision status, and confidence.
- `render_output()` marks low-confidence or missing due-date action items.

Missing validation:

- `source_quote` verification.
- Duplicate candidate merge.
- Confidence recalculation from evidence.
- Owner and due-date normalization beyond simple fallback.
- Contradiction or suspicious empty-section warning.

### Silent omission possibility

If `extract_structure()` misses an important action or decision, downstream stages usually cannot recover it.

Current risk points:

- `generate_minutes()` is told to rely on JSON, so missing structured items remain missing.
- `render_output()` only renders what structure contains.
- There is no coverage audit comparing transcript cues against extracted candidates.

### No complexity-based strategy

The current pipeline has no Direct Mode, Chunk Mode, or Deep Mode selection.

Risks:

- Applying only Direct Mode to long meetings may reduce recall.
- Applying heavy processing to all meetings would be too expensive.
- The system cannot match cost to meeting importance or transcript size.

## 3. Refactor Constraints

The refactor should be pragmatic for an 80-person internal data/IT company.

Hard constraints:

- Do not cause a broad cost increase for normal meetings.
- Do not significantly increase latency for small meetings.
- Do not build a full commercial meeting-assistant architecture unless usage proves it is needed.
- Assume most meetings are small or medium-sized internal meetings.
- Preserve existing API behavior as much as possible.
- Preserve the current frontend flow.
- Migrate in small steps.
- Keep `summarize_transcript()` as the public interface if possible.
- Keep `/api/transcript-jobs` unchanged unless a later product requirement explicitly justifies a change.
- Keep the existing `SummaryResult` response shape compatible while adding internal fields gradually.

Design implication:

- Direct Mode should remain the default path.
- New layers should be optional, internal, and testable.
- Evidence and validation should improve reliability before chunking adds complexity.

## 4. Proposed Target Flow

Recommended future internal flow:

```text
normalize_transcript
-> analyze_transcript_profile
-> choose_processing_strategy
-> extract_candidates
-> merge_candidates
-> validate_structure
-> audit_coverage
-> generate_minutes
-> render_output
```

### `normalize_transcript`

Role:

- Convert reviewed transcript text into stable utterance records.
- Preserve speaker, text, order, and eventually `utterance_id`.
- Keep a display-ready text form for existing prompt use.

Why needed:

- Chunking, evidence, and coverage audit all need stable source references.
- The current `Utterance` model is a good starting point, but it does not include IDs or raw line references.

Cost impact:

- Low. This is Python-only.

Quality impact:

- Medium. It enables better grounding and safer chunking.

### `analyze_transcript_profile`

Role:

- Measure transcript size and complexity.
- Estimate tokens or characters.
- Count utterances and speakers.
- Detect action/decision cue density.

Why needed:

- The engine needs a low-cost way to decide whether Direct Mode is enough.

Cost impact:

- Low. Python-only.

Quality impact:

- Medium. It prevents over-processing small meetings and under-processing long meetings.

### `choose_processing_strategy`

Role:

- Select Direct Mode, Chunk Mode, or Deep Mode.

Why needed:

- Cost and quality should scale with meeting complexity.

Cost impact:

- Low by itself.
- Indirectly controls model cost.

Quality impact:

- High for long meetings because it can activate recall-protection steps only when needed.

### `extract_candidates`

Role:

- Treat model extraction as high-recall candidate generation.
- Extract action items, decisions, risks, blockers, requirements, open questions, and summary facts over time.
- Include `source_quote` for important candidates.

Why needed:

- The model should not be asked to produce final truth in one pass.
- Ambiguous candidates should survive into validation instead of disappearing.

Cost impact:

- Low in Direct Mode if it replaces the current `extract_structure()` call.
- Medium to high in Chunk Mode because multiple extraction calls may run.

Quality impact:

- High. Better recall and grounding.

### `merge_candidates`

Role:

- Combine repeated candidates.
- Merge candidates across overlapping chunks.
- Preserve multiple evidence quotes where useful.

Why needed:

- Chunking and overlap create duplicates.
- Repeated mentions can strengthen confidence.

Cost impact:

- Low if implemented in Python first.
- Medium if model-assisted merging is later needed for Deep Mode.

Quality impact:

- Medium to high. It reduces duplicate clutter while preserving evidence.

### `validate_structure`

Role:

- Convert candidates into a validated structure used by rendering and prose generation.
- Normalize owner, due date, source evidence, confidence, and warnings.

Why needed:

- Prompt-only control cannot enforce reliability.
- Python should own deterministic checks.

Cost impact:

- Low. Python-only.

Quality impact:

- High. This is the best first refactor target.

### `audit_coverage`

Role:

- Scan transcript cues and compare them with extracted candidates.
- Warn when strong action, decision, risk, or blocker cues appear absent from final structure.

Why needed:

- Important candidates should not vanish silently.

Cost impact:

- Low for a lightweight cue scanner.
- Medium if later re-check calls are added for Deep Mode.

Quality impact:

- High for recall protection.

### `generate_minutes`

Role:

- Generate readable Korean minutes from validated facts.
- Use transcript only for context and wording.

Why needed:

- Natural-language output still benefits from a strong model.
- It should remain downstream of validation.

Cost impact:

- Same as current unless prompt size grows.

Quality impact:

- Medium. Quality improves when inputs are better grounded.

### `render_output`

Role:

- Render critical sections from validated structured data.
- Combine warnings, quick summary, action items, decisions, risks, and final prose.

Why needed:

- The UI and downloaded minutes need deterministic, consistent output.

Cost impact:

- Low. Python-only.

Quality impact:

- High for trust and consistency.

## 5. Recommended Intermediate Architecture

A full commercial meeting-assistant architecture would be too heavy for the current project. It would likely add unnecessary cost, latency, and operational complexity.

The better intermediate target is a pragmatic internal-tool design:

```text
preprocess_transcript
-> normalize_transcript
-> analyze_transcript_profile
-> direct_or_chunk_extract_candidates
-> validate_structure
-> optional_lightweight_audit
-> generate_minutes
-> render_output
```

Recommended priorities:

- Keep Direct Mode as default.
- Add `source_quote` and validation before adding chunking.
- Add conditional chunking only for long or complex transcripts.
- Add lightweight cue scanning before any expensive re-check workflow.
- Keep the current public `SummaryResult` shape until the frontend is ready for expanded fields.

Why this fits the company scale:

- Most internal meetings do not need expensive multi-pass processing.
- The highest-value reliability gain comes from evidence and Python validation, not from immediately adding many model calls.
- The current transcript review flow already removes a major source of STT-quality risk.
- The team can improve recall and trust without rebuilding the entire API or UI.

Pragmatic design choices:

- Use one extraction call for normal meetings.
- Use chunk extraction only when transcript size or cue density crosses a threshold.
- Store richer internal candidates first, then map back to existing API fields.
- Treat `warnings` as the early user-facing escape hatch for uncertainty.

## 6. Suggested New Internal Models

These are design candidates only. They should not be implemented until the migration step that needs them.

### `TranscriptUtterance`

Purpose:

- Stable representation of one transcript utterance.

Suggested fields:

- `utterance_id`
- `speaker`
- `text`
- `index`
- `raw_line`

Notes:

- This can evolve from the current `Utterance` dataclass.
- It should preserve enough source information for evidence checks and chunking.

### `TranscriptChunk`

Purpose:

- A chunk of utterances used for conditional Chunk Mode.

Suggested fields:

- `chunk_id`
- `utterances`
- `start_utterance_id`
- `end_utterance_id`
- `overlap_before_ids`
- `overlap_after_ids`
- `text`

Notes:

- Chunk metadata is important for duplicate merge and source traceability.

### `ExtractionCandidate`

Purpose:

- High-recall candidate extracted by a model or cue scanner.

Suggested fields:

- `candidate_id`
- `kind`
- `text`
- `owner`
- `due_date`
- `status`
- `confidence`
- `source_quote`
- `source_utterance_ids`
- `warnings`

Notes:

- `kind` can start with `action_item`, `decision`, and `summary_fact`.
- Later kinds can include `risk`, `blocker`, `requirement`, `dependency`, and `open_question`.

### `ValidatedActionItem`

Purpose:

- Final validated action item ready for rendering and API mapping.

Suggested fields:

- `task`
- `owner`
- `due_date`
- `confidence`
- `source_quote`
- `source_utterance_ids`
- `warnings`

Notes:

- Existing API can continue returning only `task`, `owner`, `due_date`, and `confidence` until response models are expanded.

### `CoverageWarning`

Purpose:

- Warning generated by audit logic when transcript cues may not be covered.

Suggested fields:

- `kind`
- `message`
- `source_quote`
- `source_utterance_ids`
- `severity`

Notes:

- These can initially be flattened into the existing `warnings` list.

## 7. Suggested Validation Rules

Validation should be deterministic Python logic between extraction and minutes generation.

### Owner normalization

Rules:

- Convert first-person owners such as `저`, `제가`, `나`, and `내가` to `미정`.
- Normalize empty owners to `미정`.
- Preserve explicit Korean names, team names, and role names.
- Warn when owner is missing or first-person.

Current basis:

- `normalize_action_owner()` already implements the first simple version.

### Due-date normalization

Rules:

- Normalize empty or unclear due dates to `미정`.
- Use extracted meeting date as the base for relative due-date interpretation only when the transcript clearly supports it.
- Avoid inventing dates from vague expressions such as "나중에" or "빠르게".
- Warn when a task has no clear due date.

### `source_quote` verification

Rules:

- Require `source_quote` for action items and decisions in the future internal structure.
- Check that `source_quote` appears in the normalized transcript or can be matched with a conservative fuzzy rule.
- Downgrade confidence or warn when source evidence is missing.
- Do not silently drop an item solely because the quote is imperfect.

### Duplicate merge

Rules:

- Merge items with substantially similar task text, owner, and due date.
- Preserve stronger confidence when evidence supports it.
- Preserve multiple source quotes if they add context.
- Prefer one clear item over repeated duplicates in rendering.

### Confidence recalculation

Rules:

- `high` should require clear task, owner, due date, and source evidence.
- Missing owner, missing due date, missing source quote, or vague task should downgrade to `low`.
- Repeated supported mentions can raise confidence only when they are consistent.

### Warning generation

Rules:

- Warn for missing owner.
- Warn for missing or vague due date.
- Warn for weak or missing source evidence.
- Warn for strong cue scanner hits that are not represented in candidates.
- Warn for suspiciously empty action item or decision sections in cue-heavy transcripts.

## 8. Chunking Strategy Proposal

Chunking should be utterance-based and conditional.

### Chunk construction

Recommended rules:

- Split by utterance boundaries, not raw character count.
- Preserve speaker, utterance order, and `utterance_id`.
- Use overlap between adjacent chunks.
- Keep action and decision context together where possible.
- Avoid separating an action item from its owner, due date, rationale, or decision context.

### Overlap

Recommended initial overlap:

- 3 to 8 utterances for typical meetings.
- Larger overlap only if utterances are short or cue density is high.

Overlap tradeoff:

- More overlap protects continuity.
- More overlap creates duplicates and increases model cost.
- Merge logic must expect duplicates.

### Conditional activation

Direct Mode should remain default.

Suggested initial Chunk Mode triggers:

- More than roughly 120 to 180 normalized utterances.
- More than roughly 18,000 to 25,000 estimated tokens.
- More than roughly 8 to 10 speakers.
- High action/decision cue density across distant transcript sections.
- A transcript that is close to the model context limit or produces poor extraction in tests.

These numbers should be treated as starting heuristics, not permanent product rules.

### Deep Mode triggers

Deep Mode should not be automatic for most meetings.

Possible triggers:

- Manual opt-in later.
- High-importance meeting type from context.
- Very long transcript plus high cue density.
- Incident review, leadership review, or customer-facing review classification.

## 9. Coverage Audit Proposal

Coverage audit is a recall-protection layer, not a final truth generator.

### Cue scanner concept

A lightweight Python cue scanner can identify transcript spans that look operationally important.

Initial cue categories:

- Action cues: "해야 합니다", "진행하겠습니다", "담당", "까지 완료", "follow up", "next step"
- Decision cues: "결정했습니다", "확정", "하기로 했습니다", "approved", "go with"
- Risk or blocker cues: "리스크", "막힘", "blocked", "issue", "concern"
- Requirement cues: "필요합니다", "must", "requirement", "조건"

### Missing candidate detection

The audit step should compare cue hits with extracted and validated candidates.

Initial behavior:

- If a strong cue span is not near any candidate source quote or utterance ID, add a warning.
- If action cues are frequent but action items are empty, add a warning.
- If decision cues are frequent but decisions are empty, add a warning.

### Recall protection purpose

The audit should not add final action items by itself at first. It should surface likely omissions so users and later model passes can review them.

This keeps the first implementation lightweight and avoids replacing one hallucination risk with another.

## 10. Safe Migration Plan

Do not rewrite all of `summarize.py` at once.

The current design already has good separation between preprocessing, extraction, prose generation, and rendering. Refactoring should preserve that shape while adding reliability layers.

### Step 1: `source_quote` + validation layer

Scope:

- Add `source_quote` to internal extraction schema for action items and decisions.
- Add `validate_structure()` after extraction and before `generate_minutes()`.
- Keep `summarize_transcript()` public interface unchanged.
- Keep API response shape unchanged initially.

Risk:

- Structured Output schema changes can break tests or model responses.
- Prompts may need adjustment to avoid excessive quote length.

Expected benefit:

- Better grounding.
- First meaningful Python validation point.
- Lower hallucination risk without adding extra model calls.

Existing test impact:

- Update schema tests.
- Add validation tests for missing quote, missing owner, missing due date, and confidence downgrade.
- Existing `SummaryResult` shape tests should continue passing.

### Step 2: `utterance_id` normalization

Scope:

- Evolve preprocessing to preserve stable utterance records.
- Add IDs without changing rendered transcript text.
- Keep current conservative filler removal behavior.

Risk:

- Same-speaker merge behavior may conflict with source-level IDs.
- Tests that assert exact preprocessed text may need careful updates if internals change.

Expected benefit:

- Enables source references.
- Prepares chunking and coverage audit.
- Improves debugging of extracted candidates.

Existing test impact:

- Existing preprocess text tests should remain unless output text changes.
- Add tests for stable utterance IDs and source mapping.

### Step 3: conditional Chunk Mode

Scope:

- Add transcript profile analysis.
- Add strategy selection.
- Use Direct Mode by default.
- Use chunk extraction only above size or complexity thresholds.
- Merge duplicate candidates before validation.

Risk:

- More model calls for long meetings.
- Duplicate candidates from overlap.
- More complex failure paths.

Expected benefit:

- Better recall for long meetings.
- Reduced risk of single-call extraction missing late or local details.

Existing test impact:

- Add tests for strategy selection.
- Add tests that small transcripts still call extraction once.
- Add tests for duplicate merge.
- Mock model calls to avoid network dependency.

### Step 4: coverage audit

Scope:

- Add lightweight cue scanner.
- Add `audit_coverage()` after validation.
- Flatten audit warnings into existing `warnings` list at first.

Risk:

- False-positive warnings if cue rules are too broad.
- Too many warnings could reduce user trust.

Expected benefit:

- Better protection against silent omission.
- Clearer signal when action items or decisions may be missing.

Existing test impact:

- Add cue scanner tests.
- Add omission-warning tests.
- Add negative tests to prevent warning spam on ordinary text.

### Step 5: expanded output fields

Scope:

- Add internal candidates for `open_questions`, `risks`, `requirements`, `blockers`, and `dependencies`.
- Expand rendering when product UI is ready.
- Consider API schema changes only after frontend compatibility work is planned.

Risk:

- API and frontend response model changes.
- More UI complexity.
- More extraction ambiguity.

Expected benefit:

- More useful meeting outputs for planning, incident review, and cross-functional work.

Existing test impact:

- Add response model tests only when API fields are exposed.
- Add rendering tests for expanded sections.
- Keep backward compatibility tests for existing fields.

## 11. Backward Compatibility

The refactor should preserve user-facing flow.

Must remain stable:

- Existing frontend flow.
- `UploadPage`.
- `TranscriptPage` review/edit flow.
- `ResultPage`.
- `POST /api/transcriptions`.
- Polling through existing job status endpoints.
- `POST /api/transcript-jobs`.
- `run_transcript_summary_pipeline()`.
- `summarize_transcript(transcript, context="")`.
- Existing `SummaryResult` fields where possible.

Recommended compatibility approach:

- Add richer internal structures inside `summarize.py`.
- Map validated internal structures back to the current `SummaryResult`.
- Do not expose `source_quote`, `utterance_id`, or expanded fields in API responses until the frontend is ready.
- Keep `warnings` as the initial compatibility channel for uncertainty and audit findings.
- Preserve `action_items` fields: `task`, `owner`, `due_date`, `confidence`.
- Preserve `decisions` fields: `decision`, `status`.

This lets the engine improve internally while avoiding a coordinated API/frontend migration too early.

## 12. Testing Strategy

### Preserve existing unittest coverage

Current tests already cover:

- Conservative filler removal.
- Public pipeline stage order.
- Context propagation.
- Empty transcript rejection.
- API result shape.
- Structured Output request shape.
- Prompt principles.
- Rendering of structured action items.
- Response parsing helpers.
- Model environment overrides.

These tests should remain valuable during refactoring.

### Add regression tests

Recommended regression areas:

- `summarize_transcript()` still returns the same public keys.
- Existing `/api/transcript-jobs` flow still stores and returns summary results.
- Direct Mode remains single-extraction for small transcripts.
- Existing rendering does not duplicate generated and structured action sections.

### Build a golden transcript dataset

Create a small local dataset of representative transcripts:

- Short team sync.
- Medium planning meeting.
- Long meeting with many action items.
- Decision-heavy meeting.
- Transcript with ambiguous owners and due dates.
- Transcript with no action items.

Each golden transcript should include expected:

- Minimum action items that must be recalled.
- Decisions that must appear.
- Warnings that should appear.
- Items that should not be invented.

### Measure action item recall

For golden transcripts, track:

- Required action items found.
- Required owners found.
- Required due dates found or correctly marked `미정`.
- Low-confidence handling for incomplete items.

Recall should be prioritized over perfect precision for candidate extraction, then improved by validation.

### Hallucination detection

Add tests that verify:

- Unsupported owners are not invented.
- Unsupported due dates are not invented.
- Decisions absent from transcript do not appear as confirmed.
- First-person owners normalize to `미정`.

### Omission detection

Add tests for cue-heavy transcripts:

- Action cue present but no extracted action item should produce a warning.
- Decision cue present but no extracted decision should produce a warning.
- Weak cue-only text should not produce excessive warnings.

### Mock model calls

All unit tests should keep mocking OpenAI calls. Network calls should not be required for local verification.

### Verification order

For implementation phases, use the project verification order:

1. `python3 -m py_compile`
2. `python3 -m unittest discover -s tests -v`
3. Browser verification only when UI changes are made

For this document-only planning step, code tests are not required.
