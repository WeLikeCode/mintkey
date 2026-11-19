# Proposal: fix 1 for agent-auth-unavailable

## Why
Requested by CiprianSpot, 2026-10-25T16:08:45Z in FB-001 (behaviour, apps/admin-api/src/admin_api/capacity.py:14-23): Review by Claude as the owner's delegate. The requirement "admin-api's memory limit fits its verify concurrency" says to_mib converts an integer followed by m, M or Mi (MiB) or g, G or Gi (times 1024) and that any other string SHALL raise ValueError whose message contains the string. The pattern (\d+)([mMgG]i?) also accepts a lowercase unit with i (512mi gives 512, 1gi gives 1024), and \d matches non-ASCII digits (５１２m gives 512). Accept exactly the six units (for example (\d+)(Mi|Gi|m|M|g|G) compiled with re.ASCII, still with fullmatch) and change nothing else: the other functions, their messages and the existing tests stay as they are.

    _MEMORY_RE = re.compile(r"(\d+)([mMgG]i?)")


    def to_mib(value: str) -> int:
        match = _MEMORY_RE.fullmatch(value)
        if match is None:
            raise ValueError(f"unsupported memory value: {value!r}")
        amount, unit = match.groups()
        factor = 1024 if unit[0] in ("g", "G") else 1
        return int(amount) * factor

The verifier found problems in `agent-auth-unavailable` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-fede8b82 (major): Feedback FB-001 (behaviour): to_mib accepts 512mi, 1gi and non-ASCII digits

## Impact
The code and the tests of `agent-auth-unavailable`.
