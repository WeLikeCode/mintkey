# Requirements Tracker

Canonical requirements live in `requirements.csv`. This is the single source of truth for what the system must do.

## CSV schema (6 columns)

| Column | Type | Description |
|---|---|---|
| `id` | `REQ-NNN` | Auto-incrementing. Never reuse a retired ID. |
| `title` | Free text | One-sentence "the system shall…" statement. ≤ 120 chars. |
| `priority` | `must` / `should` / `could` / `wont` | MoSCoW. Default: `should`. |
| `source` | Filename or reference | Where this requirement was first stated (meeting notes, BA doc, ticket). |
| `status` | `open` / `validated` / `implemented` / `deferred` / `retired` | Lifecycle state. |
| `notes` | Free text | Clarifications, links to ADRs, dedup references. Optional. |

## Rules

1. **One requirement per row.** Compound requirements get split.
2. **No duplicates.** The `requirements-extract` skill deduplicates on semantic similarity before appending.
3. **Source traceability.** Every requirement links back to its origin document in `sources/`.
4. **Architect owns the file.** Developers may propose additions via draft; architect merges.
5. **IDs are immutable.** A retired requirement keeps its ID forever. New requirements get the next available number.

## Sources directory

Place raw BA artifacts (meeting notes, exported stories, process docs) in `sources/`. The `requirements-extract` skill reads from here.

## Workflow

```
BA artifact → sources/ → requirements-extract skill → requirements.csv (deduped)
                                                     ↓
                                              architect reviews & merges
```

## Viewing

```bash
# Pretty-print in terminal (requires csvkit from `make deps`)
csvlook docs/requirements/requirements.csv

# Filter by priority
csvgrep -c priority -m "must" docs/requirements/requirements.csv | csvlook
```
