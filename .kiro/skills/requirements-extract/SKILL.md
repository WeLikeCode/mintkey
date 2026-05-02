---
name: requirements-extract
description: >
  Extract requirements from meeting notes, BA documents, or any markdown file and append them
  (deduplicated) to docs/requirements/requirements.csv. Activate when the user says
  "extract requirements from X", "ingest BA notes", "update requirements from meeting notes",
  "what requirements are in this doc", or "deduplicate requirements".
compatibility: >
  Requires read access to source documents (markdown, text). Requires read/write access to
  docs/requirements/requirements.csv. Uses semantic comparison for deduplication — no external
  API needed; relies on textual similarity heuristics.
metadata:
  author: kiro-project-template
  version: 0.1
---

## Instructions

You extract actionable requirements from unstructured text (meeting notes, BA documents, user story exports, process descriptions) and append them to the canonical tracker at `docs/requirements/requirements.csv`. You deduplicate against existing entries before appending.

## When to invoke

- "Extract requirements from this meeting note"
- "Ingest BA notes into the tracker"
- "Update requirements from [filename]"
- "What requirements are in this doc?"
- "Deduplicate requirements" (run dedup pass on existing CSV without new input)
- After the bootstrap wizard when Q26 indicates BA artifacts exist

## When NOT to invoke

- The document is an ADR → requirements don't live in ADRs
- The user wants to manually add a single known requirement → just edit the CSV
- The document is a risk or assumption → use those skills
- The content is architecture decisions, not requirements → use `decision-log-append`

## Inputs

- `source-file` (required) — path to the markdown/text file to extract from, OR pasted content
- `priority-default` (optional) — MoSCoW default if not inferrable. Default: `should`
- `dry-run` (optional) — if true, show proposed additions without writing. Default: false

## CSV schema

The target CSV has exactly 6 columns:

```
id,title,priority,source,status,notes
```

- `id`: `REQ-NNN` — auto-increment from the highest existing ID
- `title`: one-sentence "the system shall…" statement, ≤ 120 chars
- `priority`: `must` / `should` / `could` / `wont`
- `source`: filename of the source document (relative to `docs/requirements/sources/`)
- `status`: always `open` for newly extracted requirements
- `notes`: dedup references, clarifications, or "merged from REQ-XXX"

## Workflow

### Phase 1: Read & parse source

1. Read the source file.
2. Identify requirement-like statements. Look for:
   - Explicit "shall", "must", "should", "needs to", "required to" language
   - Action items with system implications ("we need X to do Y")
   - Acceptance criteria or definition-of-done items
   - Constraints stated as facts ("the system cannot exceed 200ms latency")
   - User stories in any format ("As a… I want… So that…")
3. Ignore: opinions, questions, parking-lot items, social chatter, scheduling.

### Phase 2: Normalize

For each extracted statement:
1. Rewrite as a single "The system shall…" sentence (≤ 120 chars).
2. Infer priority from language:
   - "must", "critical", "blocker", "non-negotiable" → `must`
   - "should", "important", "expected" → `should`
   - "nice to have", "could", "ideally", "stretch" → `could`
   - "out of scope", "not now", "deferred" → `wont`
   - If unclear → use `priority-default` input (default: `should`)
3. Record the source filename.

### Phase 3: Deduplicate

For each candidate requirement:
1. Read existing `docs/requirements/requirements.csv`.
2. Compare the candidate title against every existing title using these heuristics:
   - **Exact match:** same words after lowercasing and stripping punctuation → skip (duplicate)
   - **Semantic overlap:** >70% word overlap after removing stop words → flag as potential duplicate
   - **Subsumption:** candidate is a subset of an existing requirement → skip, add note to existing
   - **Contradiction:** candidate contradicts an existing requirement → flag for architect review
3. For potential duplicates: present both to the user and ask which to keep, merge, or keep both.
4. For contradictions: do NOT auto-resolve. Flag with `[CONFLICT]` prefix in notes.

### Phase 4: Append

1. Determine next available `REQ-NNN` ID.
2. Append new rows to `docs/requirements/requirements.csv`.
3. If the source file is not already in `docs/requirements/sources/`, copy or link it there.
4. Report summary: N extracted, M deduplicated, K appended, J flagged for review.

### Phase 5: Offer follow-ups

- "Want me to extract from another file?"
- "N requirements flagged as potential duplicates — review now?"
- If any `must` requirements touch architecture: "These look architectural — want me to check if ADRs exist for them?"

## Deduplication heuristics (detail)

The dedup logic does NOT require embeddings or external APIs. It uses:

1. **Normalized token sets:** lowercase, remove punctuation, split on whitespace, remove stop words (the, a, an, is, are, will, shall, system, be, to, of, for, in, on, at, by, with, from, that, this, it).
2. **Jaccard similarity:** |intersection| / |union| of token sets. Threshold: 0.7 = potential duplicate.
3. **Prefix match:** if one title starts with the same 8+ words as another → potential duplicate.
4. **Domain-term anchoring:** if both requirements mention the same domain noun (e.g., "invoice", "tenant", "pipeline") AND the same verb (e.g., "validate", "store", "process") → potential duplicate.

When in doubt, keep both and flag. False negatives (missed duplicates) are cheaper than false positives (lost requirements).

## Output format

Present results as:

```
## Extraction Summary

Source: `meeting-2024-03-15.md`
Extracted: 8 requirement candidates
Deduplicated: 2 (matched REQ-012, REQ-045)
Appended: 6 new requirements (REQ-051 through REQ-056)
Flagged: 1 potential conflict with REQ-003

### New requirements added:

| ID | Title | Priority |
|---|---|---|
| REQ-051 | The system shall validate tenant isolation at API gateway | must |
| ... | ... | ... |

### Flagged for review:

- REQ-052 vs REQ-003: possible conflict — "system shall reject cross-tenant queries" vs "system shall allow admin cross-tenant access"
```

## Anti-patterns

- Extracting vague wishes as requirements ("it would be cool if…" → not a requirement)
- Auto-resolving contradictions without architect input
- Generating requirements the source doesn't actually state (no hallucinated requirements)
- Changing existing requirement IDs or titles during dedup
- Appending without reading existing CSV first (guarantees duplicates)
- Treating every bullet point as a requirement — apply judgment

## Cross-references

- `docs/requirements/README.md` — CSV schema and rules
- `docs/requirements/sources/` — raw BA artifacts
- Bootstrap Q26 — triggers initial ingestion
- `decision-log-append` — if extraction reveals decisions, not requirements
- `risk-register-update` — if extraction reveals risks, not requirements

#[[file:docs/requirements/README.md]]
