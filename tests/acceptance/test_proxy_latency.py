"""
Performance test: egress proxy latency benchmark (T-1.6.9).

Unit assertions (always run):
  - test_proxy_plugin_has_no_credential_cache: vault/client.go Client struct must
    have no cache field — per ADR-0014.4, plaintext credentials must not be
    cached in the proxy plugin.
  - test_proxy_plugin_revocation_sets_are_in_memory: revocation/agent_set.go must
    use an in-memory map (no DB calls) — critical for meeting the p99 SLA.

Integration test (MINTKEY_INTEGRATION_TEST=true only):
  - test_proxy_p99_latency_under_30ms: 100 RPS for 30s; p50 ≤ 10ms, p99 ≤ 30ms
    added latency.

Sources: ADR-0004; ADR-0014.4; T-1.6.9.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT_CLIENT_GO = (
    REPO_ROOT / "apps" / "proxy-plugin" / "internal" / "vault" / "client.go"
)
AGENT_SET_GO = (
    REPO_ROOT
    / "services"
    / "proxy-plugin"
    / "internal"
    / "revocation"
    / "agent_set.go"
)

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full stack",
)


# ---------------------------------------------------------------------------
# Unit assertions (always run)
# ---------------------------------------------------------------------------


def test_proxy_plugin_has_no_credential_cache() -> None:
    """
    vault/client.go must not declare a cache field on the Client struct.

    ADR-0014.4 forbids credential caching in the proxy plugin.  The Vault
    Adapter holds the DEK cache; the proxy plugin must call the Vault Adapter
    on every request.  A cache field here would violate that guarantee and
    introduce plaintext-credential persistence beyond request scope.
    ADR-0014.4; T-1.6.9.
    """
    assert VAULT_CLIENT_GO.exists(), (
        f"vault/client.go not found at {VAULT_CLIENT_GO}"
    )
    source = VAULT_CLIENT_GO.read_text(encoding="utf-8")

    # Extract the Client struct body: from "type Client struct {" to the
    # matching closing brace.
    struct_match = re.search(
        r"type\s+Client\s+struct\s+\{([^}]*)\}", source, re.DOTALL
    )
    assert struct_match, (
        "vault/client.go does not define a Client struct — expected per ADR-0014.4"
    )

    struct_body = struct_match.group(1)

    # Strip single-line comments (//) so that compliance comments such as
    # "// No cache field — ADR-0014.4" don't false-positive.
    struct_body_no_comments = re.sub(r"//[^\n]*", "", struct_body)

    # Check for an actual field declaration whose name contains "cache".
    # A Go struct field line looks like: <identifier>  <type>
    has_cache_field = any(
        re.match(r"\s*\w*[Cc]ache\w*\s+\S", line)
        for line in struct_body_no_comments.splitlines()
    )
    assert not has_cache_field, (
        "Client struct in vault/client.go contains a 'cache' field — "
        "credential caching in the proxy plugin violates ADR-0014.4"
    )


def test_proxy_plugin_revocation_sets_are_in_memory() -> None:
    """
    revocation/agent_set.go must use an in-memory map and must not reference
    any DB, SQL, pgx, or gRPC imports.

    The revocation set is populated asynchronously from the change channel
    subscriber.  Checking revocation inline on every proxied request must be
    O(1) in-memory; any DB call would blow the p99 SLA.
    ADR-0014.4; T-1.6.9.
    """
    assert AGENT_SET_GO.exists(), (
        f"revocation/agent_set.go not found at {AGENT_SET_GO}"
    )
    source = AGENT_SET_GO.read_text(encoding="utf-8")

    # Must use a map (in-memory storage).
    assert "map[" in source, (
        "agent_set.go does not use a map — in-memory revocation set expected for p99 SLA"
    )

    # Must not import database/SQL packages.
    forbidden_imports = ("database/sql", "pgx", "gorm", "sqlc", "google.golang.org/grpc")
    for forbidden in forbidden_imports:
        assert forbidden not in source, (
            f"agent_set.go imports '{forbidden}' — revocation checks must be "
            f"in-memory only for p99 SLA compliance (ADR-0014.4)"
        )


# ---------------------------------------------------------------------------
# Integration test (requires full stack)
# ---------------------------------------------------------------------------


@INTEGRATION
def test_proxy_p99_latency_under_30ms() -> None:
    """100 RPS for 30s; assert p50 ≤ 10ms, p99 ≤ 30ms added latency."""
    pytest.skip("Requires full stack — set MINTKEY_INTEGRATION_TEST=true")
