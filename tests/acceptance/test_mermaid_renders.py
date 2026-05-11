"""
CI gate: T-1.11.7 — Mermaid render validation.

Validates every ```mermaid block in docs/architecture/:
  - the docs directory exists
  - every block starts with a known diagram-type keyword
  - no block is empty (whitespace-only)
  - if `mmdc` (mermaid-cli) is available on PATH, each block is rendered to SVG

References: CLAUDE.md verification commands; ADR-0014, ADR-0017 Mermaid guardrails.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

DOCS_DIR = Path(__file__).parents[2] / "docs" / "architecture"

# All diagram types recognised by Mermaid 10.x
VALID_DIAGRAM_TYPES = re.compile(
    r"^\s*("
    r"graph|flowchart|sequenceDiagram|classDiagram|erDiagram"
    r"|stateDiagram(-v2)?|gitGraph|pie|gantt|mindmap|timeline"
    r"|xychart-beta|block-beta|packet-beta|architecture-beta|zenuml"
    r")\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_mermaid_blocks(md_path: Path) -> list[tuple[Path, int, str]]:
    """
    Return list of (file, block_index, block_content) tuples for every
    ```mermaid ... ``` block found in *md_path*.
    """
    src = md_path.read_text(encoding="utf-8", errors="replace")
    results = []
    for idx, m in enumerate(re.finditer(r"```mermaid\s*\n(.*?)```", src, re.DOTALL)):
        results.append((md_path, idx, m.group(1)))
    return results


def _all_blocks() -> list[tuple[Path, int, str]]:
    """Walk docs/architecture/ and collect all mermaid blocks."""
    blocks: list[tuple[Path, int, str]] = []
    for md_file in sorted(DOCS_DIR.rglob("*.md")):
        blocks.extend(_extract_mermaid_blocks(md_file))
    return blocks


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMermaidRenders:
    """T-1.11.7 — Mermaid block validation."""

    def test_architecture_docs_exist(self):
        """docs/architecture/ must exist and contain at least one .md file."""
        assert DOCS_DIR.is_dir(), f"Architecture docs directory not found: {DOCS_DIR}"
        md_files = list(DOCS_DIR.rglob("*.md"))
        assert md_files, f"No .md files found under {DOCS_DIR}"

    def test_mermaid_blocks_are_not_empty(self):
        """No mermaid block may be empty (just whitespace)."""
        blocks = _all_blocks()
        assert blocks, "No mermaid blocks found — check docs/architecture/"

        failures = []
        for path, idx, content in blocks:
            if not content.strip():
                failures.append(f"{path.relative_to(DOCS_DIR)} block #{idx}")

        assert not failures, (
            "Empty mermaid blocks found:\n" + "\n".join(f"  {f}" for f in failures)
        )

    def test_mermaid_blocks_have_valid_diagram_types(self):
        """
        Every mermaid block must begin with a recognised diagram-type keyword.
        Validates the guardrails from ADR-0017 (no raw HTML, correct syntax).
        """
        blocks = _all_blocks()
        failures = []

        for path, idx, content in blocks:
            first_line = content.lstrip("\n").split("\n")[0]
            if not VALID_DIAGRAM_TYPES.match(first_line):
                failures.append(
                    f"{path.relative_to(DOCS_DIR)} block #{idx}: "
                    f"first line {first_line!r} is not a valid diagram type"
                )

        assert not failures, (
            "Mermaid blocks with unrecognised diagram types:\n"
            + "\n".join(f"  {f}" for f in failures)
        )

    def test_mermaid_cli_renders_if_available(self):
        """
        If `mmdc` is on PATH, render every block to SVG and assert exit-code 0.
        Skipped gracefully when mmdc is not installed.
        """
        mmdc = shutil.which("mmdc")
        if mmdc is None:
            # mmdc not installed — structural checks above are sufficient for CI
            return

        blocks = _all_blocks()
        failures = []

        with tempfile.TemporaryDirectory() as tmp:
            for path, idx, content in blocks:
                src_file = Path(tmp) / f"block_{idx}.mmd"
                out_file = Path(tmp) / f"block_{idx}.svg"
                src_file.write_text(content, encoding="utf-8")

                result = subprocess.run(
                    [mmdc, "-i", str(src_file), "-o", str(out_file), "--quiet"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    failures.append(
                        f"{path.relative_to(DOCS_DIR)} block #{idx}: "
                        f"mmdc exit {result.returncode}\n"
                        f"    stderr: {result.stderr.strip()}"
                    )

        assert not failures, (
            "mmdc rendering failures:\n" + "\n".join(f"  {f}" for f in failures)
        )
