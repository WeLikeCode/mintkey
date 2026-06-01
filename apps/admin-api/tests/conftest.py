"""
Root conftest for admin-api unit tests.

Sets MINTKEY_AUDIT_HMAC_KEY to a deterministic dev-only value before any
admin-api module is imported.  The setdefault runs at conftest import time
(module-level), which is before pytest collects and imports test modules.
This prevents the RuntimeError that audit_fingerprint raises at import time
when the variable is absent.

Production containers read the real key from the operator-provided .env
(see infra/compose/docker-compose.yml and .env.example).
"""
from __future__ import annotations

import os

# 64-char hex = 32 bytes = minimum key size accepted by audit_fingerprint.
# All-zeros is intentional for a dev/test placeholder — NOT a production secret.
# Set at module level (not inside a fixture) so it runs before test collection
# imports admin_api modules that trigger the env-var check at module level.
os.environ.setdefault("MINTKEY_AUDIT_HMAC_KEY", "0" * 64)
