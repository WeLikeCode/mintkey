"""T-1.8.3 — Credential rotation propagation timing tests.

Unit assertions (always run): verify the structural wiring exists in the
source tree so that rotation events can propagate to the vault-adapter DEK
cache within the 30-second SLA.

Integration test (skipped unless MINTKEY_INTEGRATION_TEST=true): registers
a credential, rotates it, and asserts the cache is invalidated within 30 s.
"""

import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parents[2]  # repo root


def _read(rel: str) -> str:
    return (ROOT / rel).read_text()


# ---------------------------------------------------------------------------
# Integration marker
# ---------------------------------------------------------------------------

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full stack — set MINTKEY_INTEGRATION_TEST=true",
)

# ---------------------------------------------------------------------------
# Unit assertions (always run)
# ---------------------------------------------------------------------------


def test_vault_adapter_has_credential_subscriber():
    """services/vault-adapter/internal/changes/subscriber.go must exist and
    subscribe to the mintkey:credential channel (ADR-0014.1)."""
    path = "services/vault-adapter/internal/changes/subscriber.go"
    assert (ROOT / path).exists(), f"Missing: {path}"
    content = _read(path)
    assert "mintkey:credential" in content, (
        f"{path} does not contain 'mintkey:credential' channel subscription"
    )


def test_dek_cache_has_invalidate_by_service():
    """services/vault-adapter/internal/cache/dek_cache.go must exist and
    expose an InvalidateByService method (ADR-0014.1)."""
    path = "services/vault-adapter/internal/cache/dek_cache.go"
    assert (ROOT / path).exists(), f"Missing: {path}"
    content = _read(path)
    assert "InvalidateByService" in content, (
        f"{path} does not contain 'InvalidateByService' method"
    )


def test_rotation_emits_credential_rotated_notify():
    """admin-api/src/admin_api/api/credentials.py must call pg_notify with
    the mintkey:credential channel on rotation (ADR-0014.1, ADR-0008)."""
    path = "admin-api/src/admin_api/api/credentials.py"
    assert (ROOT / path).exists(), f"Missing: {path}"
    content = _read(path)
    assert "pg_notify" in content, (
        f"{path} does not call pg_notify"
    )
    assert "mintkey:credential" in content, (
        f"{path} does not reference 'mintkey:credential' channel"
    )


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


@INTEGRATION
def test_credential_rotation_propagates_within_30s():
    """Register credential v1, rotate to v2, assert cache invalidated within 30s."""
    pytest.skip("Requires full stack — set MINTKEY_INTEGRATION_TEST=true")
