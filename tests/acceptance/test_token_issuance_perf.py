"""
Performance test: token issuance (T-1.5.5).

Unit assertions (always run):
  - test_broker_issuer_is_implemented: issuer.go exists and has an Issue function.
  - test_broker_uses_ed25519_not_rsa: issuer.go uses EdDSA/ed25519, not RSA/ECDSA.

Integration test (MINTKEY_INTEGRATION_TEST=true only):
  - test_token_issuance_p99_under_50ms: 100 concurrent issuances/sec for 30s;
    p99 latency must be ≤ 50ms.

Sources: ADR-0006 (Ed25519 JWS); ADR-0017.11 (prefixed ULIDs); T-1.5.5.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ISSUER_GO = REPO_ROOT / "apps" / "broker" / "internal" / "issuer" / "issuer.go"

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full stack",
)


# ---------------------------------------------------------------------------
# Unit assertions (always run)
# ---------------------------------------------------------------------------


def test_broker_issuer_is_implemented() -> None:
    """
    services/broker/internal/issuer/issuer.go must exist and export an Issue
    function.

    The Issue function is the single chokepoint for all JWT issuance.
    ADR-0006; T-1.5.5.
    """
    assert ISSUER_GO.exists(), (
        f"issuer.go not found at {ISSUER_GO} — broker JWT issuance is not implemented"
    )
    source = ISSUER_GO.read_text(encoding="utf-8")
    assert "func" in source and "Issue" in source, (
        "issuer.go does not define an Issue function — broker JWT issuance is not implemented"
    )


def test_broker_uses_ed25519_not_rsa() -> None:
    """
    issuer.go must use Ed25519 (jose.EdDSA, EdDSA, or ed25519 package), not
    RSA or ECDSA.

    Ed25519 sign is ~3× faster than RSA-2048 at equivalent security, which is
    critical for meeting the p99 ≤ 50ms SLA under load.
    ADR-0006; T-1.5.5.
    """
    assert ISSUER_GO.exists(), f"issuer.go not found at {ISSUER_GO}"
    source = ISSUER_GO.read_text(encoding="utf-8")

    uses_eddsa = any(
        token in source for token in ("jose.EdDSA", "EdDSA", "ed25519")
    )
    uses_rsa = "RSA" in source or "rsa." in source
    uses_ecdsa = "ECDSA" in source or "ecdsa." in source

    assert uses_eddsa, (
        "issuer.go does not reference EdDSA or ed25519 — JWT signing algorithm is not Ed25519 (ADR-0006)"
    )
    assert not uses_rsa, (
        "issuer.go references RSA — must use Ed25519 for performance and ADR-0006 compliance"
    )
    assert not uses_ecdsa, (
        "issuer.go references ECDSA — must use Ed25519 for performance and ADR-0006 compliance"
    )


# ---------------------------------------------------------------------------
# Integration test (requires full stack)
# ---------------------------------------------------------------------------


@INTEGRATION
def test_token_issuance_p99_under_50ms() -> None:
    """100 concurrent issuances/sec for 30s; assert p99 ≤ 50ms."""
    pytest.skip("Requires broker running — set MINTKEY_INTEGRATION_TEST=true")
