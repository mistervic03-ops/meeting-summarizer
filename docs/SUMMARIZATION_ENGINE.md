# Summarization Engine Architecture

This document defines the intended architecture direction for the Meeting Summarizer summarization engine. It is a reference for future `summarize.py` refactoring and related API or UI work.

It describes design goals and target behavior. It does not claim that every target component is implemented today.

## 1. Product Goal

Meeting Summarizer is an internal meeting-minutes tool for BigxData, an approximately 80-person data and IT company.

The goal is not to replicate every feature of commercial meeting assistant products. The goal is to provide practical, reliable internal meeting summaries with a cost profile that makes regular company use reasonable.

The engine should optimize for:

- Useful Korean meeting minutes generated from reviewed transcripts.
- Cost-efficient use of OpenAI models.
- Clear separation between transcript generation, human transcript review, structured extraction, and final prose.
- Reduced hallucination through grounding and validation.
- Strong protection against missing important action items, decisions, risks, and blockers.

Hallucination reduction matters, but the more important operational failure mode is silently omitting a real decision or action item that the team needed to track.

## 2. Core Design Principles

### Recall-first extraction

Extraction should favor capturing plausible action items, decisions, risks, blockers, and requirements over prematurely filtering them out. Later stages can merge, downgrade, warn, or mark uncertainty.

### Grounded validation

Important structured outputs should be traceable to transcript evidence. The engine should prefer fields such as `source_quote`, utterance references, and confidence values over unsupported claims.

### Human transcript review before summarization

The current product flow intentionally lets users review and edit the transcript before generating minutes. The summarization engine should treat the reviewed transcript as the source of truth.

### Structured facts before prose generation

The engine should extract structured facts before asking a model to write natural-language minutes. Prose generation should document and organize facts, not discover new facts.

### Conditional complexity based on transcript size

Short, simple meetings should use a direct, low-cost path. Long or complex meetings should use chunking, merging, validation, and audit layers only when those layers are worth the extra cost.

### No silent dropping of important candidates

Candidates that look like decisions, action items, risks, or blockers should not disappear without trace. If a candidate is uncertain, duplicated, incomplete, or contradicted, the output should preserve that state through confidence, warnings, or an audit signal.

### Python validation over prompt-only control

Prompt instructions are not enough for reliability. Deterministic Python validation should check required fields, normalize shapes, merge duplicates, recalculate confidence, and generate warnings.

## 3. Current Pipeline

### Current product flow

The current React and FastAPI flow is:

1. `UploadPage`
2. `POST /api/transcriptions`
3. Polling for transcription job status
4. `TranscriptPage`
5. User transcript edit and review
6. `POST /api/transcript-jobs`
7. `summarize_transcript()`
8. `ResultPage`

This flow has several important strengths:

- STT and meeting-minutes generation are separated.
- Humans can review the transcript before summary generation.
- Edited transcripts can be summarized instead of raw STT output.
- Context can be injected before summary generation.
- Structured extraction and prose generation are separate stages.

### Current `summarize.py` flow

The current summarization module is organized as:

1. `preprocess_transcript()`
   - Removes filler-only tokens.
   - Merges consecutive utterances from the same speaker.
   - Extracts meeting date information.
2. `extract_structure()`
   - Uses GPT-4o-mini Structured Output.
   - Extracts `summary_facts`, `decisions`, `action_items`, `speaker_highlights`, and `warnings`.
3. `generate_minutes()`
   - Uses GPT-5.4.
   - Takes the preprocessed transcript and structured JSON as input.
   - Generates natural Korean meeting minutes.
4. `render_output()`
   - Combines structured extraction and generated minutes.
   - Renders the final Markdown output.

### Current limitations

The current architecture is useful, but it has known scaling and reliability limits:

- Long meetings are handled by a single `extract_structure()` call.
- Action item and decision evidence is limited.
- Hallucination and omission controls are mostly prompt-driven.
- There is no explicit strategy branch for different meeting complexity levels.
- Important candidates can be lost between extraction, generation, and rendering without a dedicated audit layer.

## 4. Target Architecture

The future summarization engine should move toward the following staged architecture:

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

Converts the reviewed transcript into a stable internal representation. This should include speaker normalization, utterance boundaries, and eventually `utterance_id` assignment.

### `analyze_transcript_profile`

Measures transcript size and complexity. Useful signals include utterance count, token estimate, meeting duration, number of speakers, action/decision cue density, and transcript quality warnings.

### `choose_processing_strategy`

Selects Direct Mode, Chunk Mode, or Deep Mode based on transcript profile and cost-quality requirements.

### `extract_candidates`

Extracts high-recall candidates for decisions, action items, risks, blockers, requirements, open questions, and summary facts. This stage should treat ambiguous items as candidates rather than deleting them.

### `merge_candidates`

Combines candidates across chunks or repeated mentions. It should preserve evidence and avoid losing lower-confidence but important items.

### `validate_structure`

Applies deterministic Python checks to structured output. This includes required field validation, duplicate merging, confidence recalculation, and warning generation.

### `audit_coverage`

Checks whether likely important transcript cues are represented in the final structured result. This stage exists to protect recall, especially for action items and decisions.

### `generate_minutes`

Generates polished Korean meeting minutes from the validated structured data and transcript context. It should not invent new facts.

### `render_output`

Renders the final Markdown output from structured data and generated prose. Critical sections should be driven by structured data rather than free-form text alone.

## 5. Processing Modes

### Direct Mode

Use Direct Mode for short or simple meetings where the transcript can be safely processed in one pass.

Best for:

- Short internal syncs.
- Meetings with few speakers.
- Low action item density.
- Transcripts that fit comfortably in one extraction call.

Tradeoff:

- Lowest cost and simplest execution.
- Lower protection against omissions in long or complex meetings.

### Chunk Mode

Use Chunk Mode for longer meetings where a single extraction call risks losing details.

Best for:

- Long recurring team meetings.
- Cross-functional planning meetings.
- Meetings with many action items or decisions.
- Transcripts that approach model context or quality limits.

Tradeoff:

- Better recall for long meetings.
- Higher cost due to chunk extraction and merge steps.
- Requires careful duplicate handling and evidence preservation.

### Deep Mode

Use Deep Mode for high-importance or high-complexity meetings where omission risk is more expensive than model cost.

Best for:

- Executive or leadership meetings.
- Customer-facing review meetings.
- Incident reviews.
- Project kickoff, planning, or decision-heavy meetings.

Tradeoff:

- Highest quality and strongest recall protection.
- Highest cost and latency.
- Should include deeper validation, coverage audit, and richer warnings.

## 6. Chunking Strategy

Chunking should be conditional. It should be applied to long or complex meetings, not every transcript.

The preferred approach is utterance-based chunking:

- Split on utterance boundaries, not arbitrary character counts.
- Keep speaker and utterance metadata with every chunk.
- Use overlap between adjacent chunks.
- Preserve enough context around action and decision cues.
- Avoid separating an action item from its owner, due date, rationale, or decision context.

Overlap should be large enough to protect continuity but small enough to avoid excessive cost and duplicate noise.

The chunking layer should support later merge logic by preserving stable IDs and source references.

## 7. Candidate Extraction Philosophy

`extract_structure()` should evolve from a final truth generator into a high-recall candidate extractor.

This means:

- It should capture plausible candidates even when they are incomplete.
- It should use confidence and warnings to represent ambiguity.
- It should preserve `source_quote` evidence for important items.
- It should avoid converting weak evidence into strong claims.
- It should avoid deleting uncertain but potentially important candidates.

The final structured result should be produced after validation, merging, and audit, not directly from a single model response.

## 8. Validation Layer

`validate_structure()` should be a deterministic Python layer between extraction and prose generation.

Its responsibilities should include:

- Validate required fields and expected data shapes.
- Check action item `owner`, `due_date`, and `source_quote` fields.
- Check decision `source_quote` and confidence fields.
- Recalculate or downgrade confidence when evidence is weak.
- Merge duplicates across chunks or repeated mentions.
- Generate warnings for missing owners, vague deadlines, weak evidence, contradictions, or suspiciously empty sections.
- Preserve uncertain candidates instead of silently dropping them.

This layer is important because model prompts alone cannot reliably enforce schema quality, evidence quality, or recall protection.

## 9. Coverage Audit

Important candidates should not disappear silently between the transcript and the final result.

The future engine should include a coverage audit step that scans for cues such as:

- Action language: "해야 합니다", "진행하겠습니다", "담당", "follow up", "next step"
- Decision language: "결정했습니다", "확정", "approved", "go with"
- Risk and blocker language: "리스크", "막힘", "blocked", "issue", "concern"
- Requirement language: "필요합니다", "must", "requirement", "조건"

The cue scanner should not be treated as final truth. Its purpose is recall protection: if the transcript contains strong cues that are absent from extracted candidates, the engine should warn, re-check, or surface the gap for review.

## 10. Recommended Future Fields

Future structured extraction should consider adding these fields:

### `open_questions`

Questions that remain unresolved after the meeting. These help teams identify follow-up discussion points.

### `risks`

Potential problems, uncertainties, or negative outcomes that were raised but not necessarily blocking progress yet.

### `requirements`

Explicit needs, constraints, specifications, or acceptance criteria discussed during the meeting.

### `blockers`

Issues currently preventing progress. These should be distinguished from general risks.

### `dependencies`

People, teams, systems, approvals, data, or external events that another task or decision depends on.

## 11. Rendering Philosophy

Critical operational sections should be rendered from validated structured data:

- Action items
- Decisions
- Risks
- Blockers
- Requirements
- Open questions

`generate_minutes()` should focus on natural-language documentation:

- Organizing the discussion.
- Writing readable Korean minutes.
- Explaining context and flow.
- Turning validated facts into a professional document.

It should not be responsible for discovering action items, decisions, or risks that the structured extraction layer failed to capture.

## 12. Incremental Roadmap

### Phase 1

- Add `source_quote` to important structured items.
- Add `validate_structure()`.

### Phase 2

- Normalize utterances with stable `utterance_id` values.
- Add conditional Chunk Mode for long meetings.

### Phase 3

- Add cue scanner logic.
- Add `audit_coverage()` for recall protection.

### Phase 4

- Expand structured output fields.
- Add `open_questions`, `risks`, `requirements`, `blockers`, and `dependencies` to rendering.
