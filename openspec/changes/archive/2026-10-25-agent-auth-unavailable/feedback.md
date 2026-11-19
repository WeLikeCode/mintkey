# Feedback — agent-auth-unavailable

<!-- l4:feedback v1
Ask for changes here while the unit's branch is open. The easy way is `l4 feedback add` (see `l4 feedback --help`).
An item is read only when its **Status** is `submitted`; `draft` items wait and `withdrawn` items are ignored.
Kinds: refactor · duplication · tests · config · behaviour (see docs/feedback.md).
Do not change item IDs. Commit and push to the l4/… branch: the harness takes submitted items at its next
verification round, turns them into a fix unit and checks that each one was addressed. -->

<!-- l4:feedback-index:start -->
| ID | Status | Kind | Where | Feedback |
|----|--------|------|-------|----------|
| FB-001 | addressed | behaviour | apps/admin-api/src/admin_api/capacity.py:14 | to_mib accepts 512mi, 1gi and non-ASCII digits |
<!-- l4:feedback-index:end -->

---

## FB-001: to_mib accepts 512mi, 1gi and non-ASCII digits

- **Status:** addressed
- **Kind:** behaviour
- **Where:** `apps/admin-api/src/admin_api/capacity.py:14-23`
- **Lesson:** no
- **By:** CiprianSpot, 2026-10-25T16:08:45Z

### Code
```python
_MEMORY_RE = re.compile(r"(\d+)([mMgG]i?)")


def to_mib(value: str) -> int:
    match = _MEMORY_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"unsupported memory value: {value!r}")
    amount, unit = match.groups()
    factor = 1024 if unit[0] in ("g", "G") else 1
    return int(amount) * factor
```

### Feedback
Review by Claude as the owner's delegate. The requirement "admin-api's memory limit fits its verify concurrency" says to_mib converts an integer followed by m, M or Mi (MiB) or g, G or Gi (times 1024) and that any other string SHALL raise ValueError whose message contains the string. The pattern (\d+)([mMgG]i?) also accepts a lowercase unit with i (512mi gives 512, 1gi gives 1024), and \d matches non-ASCII digits (５１２m gives 512). Accept exactly the six units (for example (\d+)(Mi|Gi|m|M|g|G) compiled with re.ASCII, still with fullmatch) and change nothing else: the other functions, their messages and the existing tests stay as they are.

### When / Then
- **When:** to_mib is given 512mi, 1gi, or 512m written with non-ASCII digits (the full-width ５１２m)
- **Then:** it raises ValueError whose message contains the string, as it already does for 512, 512k, '512 Mi', '' and abc; only ASCII digits followed by exactly m, M, Mi, g, G or Gi convert

### Outcome
<!-- written by the harness -->
Addressed in round 3 at 5bb7af461f: apps/admin-api/src/admin_api/capacity.py: _MEMORY_RE = re.compile(r"(\d+)(Mi|Gi|m|M|g|G)", re.ASCII), still fullmatch
