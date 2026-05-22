"""
Architecture test: cross-tenant JWT replay must be rejected.

Verifies:
1. verifier.go contains the tenant_mismatch error code and tnt-claim check.
2. VerifyOptions struct has ExpectedTenantID field.
3. The Go test suite (TestVerify_TenantMismatch) passes.

Sources:
  - Req 13 AC3 (cross-tenant token replay rejected)
  - ADR-0008 (multi-tenancy RLS + token tnt claim)
  - T-1.6.1; T-1.12.3
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER_GO = REPO_ROOT / "apps" / "proxy-plugin" / "internal" / "jwt" / "verifier.go"
PROXY_PLUGIN_DIR = REPO_ROOT / "apps" / "proxy-plugin"


# ---------------------------------------------------------------------------
# Structural (text-scan) tests — no compilation required
# ---------------------------------------------------------------------------


def test_verifier_checks_tnt_claim() -> None:
    """
    verifier.go must contain the tenant_mismatch error code string.

    This confirms the tnt-claim enforcement path exists in source.
    ADR-0008; T-1.6.1.
    """
    assert VERIFIER_GO.exists(), f"verifier.go not found at {VERIFIER_GO}"
    source = VERIFIER_GO.read_text(encoding="utf-8")
    assert "tenant_mismatch" in source, (
        "verifier.go does not contain 'tenant_mismatch' error code — "
        "cross-tenant token replay would not be rejected (ADR-0008, T-1.6.1)"
    )


def test_verifier_has_expected_tenant_id_option() -> None:
    """
    VerifyOptions must expose ExpectedTenantID so callers can enforce the
    tnt claim per-request — ADR-0008; T-1.6.1.
    """
    assert VERIFIER_GO.exists(), f"verifier.go not found at {VERIFIER_GO}"
    source = VERIFIER_GO.read_text(encoding="utf-8")
    assert "ExpectedTenantID" in source, (
        "VerifyOptions does not contain ExpectedTenantID field — "
        "callers cannot enforce tenant isolation (ADR-0008, T-1.6.1)"
    )


# ---------------------------------------------------------------------------
# Go test: TestVerify_TenantMismatch (live compilation + execution)
# ---------------------------------------------------------------------------


def test_verifier_rejects_wrong_tenant() -> None:
    """
    Run 'go test ./internal/jwt/... -v -run Tenant' inside services/proxy-plugin/.

    Confirms TestVerify_TenantMismatch passes — a JWT with tnt=tenant_A is
    rejected when VerifyOptions.ExpectedTenantID=tenant_B.

    Sources: Req 13 AC3; ADR-0008; T-1.12.3.
    """
    result = subprocess.run(
        ["go", "test", "./internal/jwt/...", "-v", "-run", "Tenant"],
        cwd=str(PROXY_PLUGIN_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"go test ./internal/jwt/... -run Tenant failed (exit {result.returncode}):\n{output}"
    )
    assert "TestVerify_TenantMismatch" in output, (
        f"TestVerify_TenantMismatch not found in go test output:\n{output}"
    )
    assert "PASS" in output, (
        f"Expected PASS in go test output:\n{output}"
    )
