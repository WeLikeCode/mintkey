# Serena MCP code-navigation discipline

Applies to both IMPLEMENTER and REVIEWER subagents.

## If Serena MCP is available

Prefer Serena tools over raw grep + Read for navigation and surgical edits:

**Navigation (prefer these over grep for symbol-level questions):**
- `get_symbols_overview` — get the symbol inventory of a file before reading it whole
- `find_symbol` — locate a function, class, method, or variable by name
- `find_referencing_symbols` — find everything that calls or imports the target symbol
- `find_implementations` — find concrete implementations of an interface or abstract method

**Surgical edits (prefer these over sed/awk/search-replace for code changes):**
- `replace_symbol_body` — replace the entire body of a function or method precisely
- `insert_after_symbol` — add code immediately after a named symbol
- `insert_before_symbol` — add code immediately before a named symbol

**Post-edit hygiene:**
- `get_diagnostics_for_file` — check for type errors or lint issues after editing a file

## What IMPLEMENTERS should do with Serena

1. Call `get_symbols_overview` on a file before deciding what to read in full.
2. Use `find_symbol` to locate the exact function to edit — do not grep for it.
3. Use `find_referencing_symbols` to understand callers before changing a signature.
4. Use `replace_symbol_body` for surgical function body replacement — avoids off-by-one line errors.
5. Run `get_diagnostics_for_file` after any edit to the file.

## What REVIEWERS should do with Serena

1. Use `find_symbol` to verify the changed symbol's signature matches what was claimed.
2. Use `find_referencing_symbols` to verify no orphaned callers remain after a rename or removal.
3. Use `get_diagnostics_for_file` to check the changed file for type errors independently.

## If Serena is NOT available

Fall back to `grep -rn` + `Read` for navigation and standard Edit/Write for changes.
Explicitly note in your output: **"navigating without Serena"** — so the orchestrator
knows context was assembled by line-search rather than symbol-aware navigation.

This note is informational, not a blocker. The work can still pass review; just be more
careful about off-by-one errors and missed callers when navigating blind.
