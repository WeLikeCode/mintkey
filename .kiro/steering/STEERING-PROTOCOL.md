# Steering Files — Loading Protocol & Governance

> Steering files state stable rules and conventions for the engagement. They are auto-loaded into agent context based on declared inclusion mode. Loading too many pollutes context; loading too few makes agents make uninformed decisions. **This file defines the rules that prevent both failures.**

## The three Kiro inclusion modes

| Mode | Frontmatter | When the agent sees the file |
|---|---|---|
| **Default (always)** | No frontmatter (most common) | Loaded into every agent session |
| **fileMatch** | `inclusion: fileMatch` + `fileMatchPattern: "glob1,glob2"` | Loaded only when the agent reads / writes a path matching the glob |
| **manual** | `inclusion: manual` | Never auto-loaded; only when explicitly cited by name |

**Hard rule:** Default-mode is the only mode that costs every-session context tokens. It is the architect's accountable budget. Keep it small.

## Frontmatter examples

**Default-load (most common):** no frontmatter at all. The file just starts with its `# Heading`.

**fileMatch (language / area conventions):**

```yaml
---
inclusion: fileMatch
fileMatchPattern: "apps/web/**,packages/ui-*/**"
---
```

**Manual (reference-only docs):**

```yaml
---
inclusion: manual
---
```

## Anti-pollution rules

1. **Word cap: 1500 per default-loaded steering file.** Anything longer is a deep spec — move to `docs/architecture/` and link from a manual-mode pointer.
2. **Default-loaded budget: cap at ~5 files / 5000 words total.** Adding to default-loaded requires removing something else.
3. **No duplication across steering files.** If two files both define the same rule, the canonical one wins; the other links via `See [file.md#anchor]`.
4. **Steering ≠ ADR.** Steering files state stable rules without rationale. ADRs hold the rationale. If a steering file contains "we chose X because…" longer than one sentence, it belongs in an ADR.
5. **Steering ≠ implementation.** No code samples longer than 15 lines; no API endpoint listings, no SQL schemas, no full config files.
6. **Deprecate via supersession, not deletion.** If a rule no longer applies, move the file to `manual` mode and add a header explaining what superseded it. Delete after one release.
7. **One owner per file.**

## Referencing template files from steering

Use Kiro's `#[[file:...]]` syntax to embed template content inline when the steering doc activates:

```markdown
## ADR template

#[[file:.kiro/skills/adr-from-decision/references/adr-template.md]]
```

This pulls the template into context only when this steering doc is loaded — preventing template content from polluting unrelated sessions.

## Mandatory minimum for any project

- **product.md** — what the product is and why (default-load)
- **structure.md** — top-level repo layout (default-load)
- **architecture-principles.md** — 3-10 stable rules; the constitution (default-load)

Recommended optional default-load:

- **tech.md** — names of chosen tools (≤ 500 words, default-load)

Common `fileMatch`:

| Steering file | fileMatchPattern |
|---|---|
| `python-conventions.md` | `**/*.py` |
| `typescript-conventions.md` | `**/*.ts,**/*.tsx` |
| `frontend-conventions.md` | `apps/web/**,packages/ui-*/**` |
| `database-conventions.md` | `infra/database/**,**/changesets/**` |
| `api-contracts-and-schemas.md` | `contracts/**` |

Common `manual` (queryable but never auto-loaded):

- `open-questions.md`
- `assumptions-and-constraints.md`
- All ADRs in `docs/architecture/adrs/`
- Deprecated docs

## When to add a steering file

1. The rule applies across more than one component or sprint.
2. The rule is stable — you don't expect to change it monthly.
3. The rule isn't already in an ADR (rationale + decision = ADR; rule-without-rationale = steering).
4. There is exactly one owner and they are named.
5. The rule is < 1500 words.

If any of (1)-(5) fails, don't add a steering file. Use a decision-log entry, an ADR, or a one-liner in an existing steering file.

## When to remove a steering file

1. The rule no longer applies (e.g., tech swapped).
2. The content has been absorbed into another steering file.

Remove via supersession: switch to `manual` mode with a header explaining what replaced it. Delete after one release cycle.
