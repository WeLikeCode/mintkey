# Rule: Steering load discipline

**Default-loaded protocol rule.**

## The rule

Steering files are loaded into agent context based on their declared inclusion mode (see [`STEERING-PROTOCOL.md`](STEERING-PROTOCOL.md)). The three real Kiro modes:

1. **Default-load** — no frontmatter (or empty frontmatter block). Loaded every agent session. Cap: keep small (~5 files / 5000 words).
2. **fileMatch** — `inclusion: fileMatch` + `fileMatchPattern: "glob1,glob2"`. Loaded only when the agent's tool-call references a path matching the glob.
3. **Manual** — `inclusion: manual`. NEVER auto-loaded. Queryable by explicit name.

## Forbidden

- Loading every steering file "to be safe" before answering.
- Citing a `manual`-mode file's content as if it were always-known context.
- Adding a file to default-load without architect approval.
- Bypassing the loading protocol by using Read directly on multiple steering files when no trigger fires.
- Inventing other inclusion modes (e.g., `on-demand`, `always` as explicit frontmatter, `triggers:` blocks) — they don't exist in Kiro.

## When unsure whether to load a steering file

1. Check the file's frontmatter — does its inclusion mode permit auto-load for this task?
2. If yes — load.
3. If no — don't load. The protocol is doing its job.
4. If the agent thinks it needs a `manual`-mode file for a reason the protocol didn't anticipate, surface the gap to the architect rather than silently loading.

## Why

A typical engagement may have 20+ steering files. Loading all of them every session pollutes context, slows responses, and dilutes signal. The three-mode protocol prevents this. Honor it.
