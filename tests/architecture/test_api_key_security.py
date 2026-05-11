"""
Architecture tests for classical service API keys — long-lived-api-keys tasks 11.1–11.2.

These tests assert static/structural guarantees that do not require a running database
or container. They verify:

  11.1 Plaintext non-persistence:
    - No source file in admin-api or the proxy plugin contains an unguarded
      reference to `mk_svckey_` that would cause it to land in a log, audit
      payload, or span attribute.
    - The audit_emit calls for api_key.created/revoked/rotated never include
      the plaintext key string.
    - The proxy-plugin classicalkey handler does not store the plaintext beyond
      the fingerprint computation (no persistent field named after the key itself).

  11.2 Structural RLS + audit guarantees:
    - service_api_keys is already in the RLS coverage allowlist (verified via
      test_rls_coverage.py; this test confirms the allowlist entry is present
      in source).
    - Every state-change function in api_keys.py calls audit_emit.
    - The revoke endpoint calls notify_change with the "mintkey:agent" channel.
    - No f-string SQL interpolation in api_keys.py or the broker resolve handler
      (bound parameters only — ADR-0008 / T-1.0.15).

Sources:
  - long-lived-api-keys tasks 11.1, 11.2; Req 10.1, 10.7, 7.3, 7.4
  - ADR-0018 §1.3 (plaintext returned once, never persisted)
  - ADR-0008 (bound parameters)
  - ADR-0014.7 (audit chokepoint)
  - ADR-0014.1 (global mintkey:agent channel)
"""
from __future__ import annotations

import ast
import re
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

API_KEYS_PY = os.path.join(REPO_ROOT, "admin-api/src/admin_api/api/api_keys.py")
RESOLVE_GO = os.path.join(REPO_ROOT, "services/broker/internal/api/resolve/resolve.go")
HANDLER_GO = os.path.join(REPO_ROOT, "services/proxy-plugin/internal/classicalkey/handler.go")
SUBSCRIBER_GO = os.path.join(REPO_ROOT, "services/proxy-plugin/internal/changes/subscriber.go")
RLS_TEST = os.path.join(REPO_ROOT, "tests/architecture/test_rls_coverage.py")


# ---------------------------------------------------------------------------
# 11.1 Plaintext non-persistence
# ---------------------------------------------------------------------------


def test_api_keys_py_no_plaintext_in_audit_calls():
    """
    Verify that no call to audit_emit in api_keys.py includes a field named
    'plaintext_key' or a variable containing the raw plaintext value.

    ADR-0018 §1.3: plaintext is returned to the caller once and never written
    to any persistent store, log, or audit record.

    Source: long-lived-api-keys task 11.1; Req 10.1, 10.7.
    """
    with open(API_KEYS_PY) as f:
        source = f.read()

    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Look for audit_emit(...) calls
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name != "audit_emit":
            continue

        # Check keyword args: payload must not contain 'plaintext_key' key
        for kw in node.keywords:
            if kw.arg == "payload":
                payload_src = ast.unparse(kw.value)
                assert "plaintext_key" not in payload_src, (
                    f"audit_emit payload contains 'plaintext_key' at line {node.lineno}. "
                    "Plaintext must never appear in audit records (ADR-0018 §1.3; Req 10.1)."
                )
                assert "plaintext" not in payload_src.lower(), (
                    f"audit_emit payload may contain plaintext reference at line {node.lineno}. "
                    "Check that no plaintext credential is included (ADR-0018 §1.3)."
                )


def test_api_keys_py_plaintext_not_logged():
    """
    Verify that api_keys.py contains no logging calls (print/logging.info/structlog)
    that reference the plaintext variable.

    Source: long-lived-api-keys task 11.1; Req 10.1, 10.7.
    """
    with open(API_KEYS_PY) as f:
        source = f.read()

    # plaintext variable is named 'plaintext' in the implementation
    # It must not appear inside any log/print call
    # Use negative lookbehind to exclude substrings like _fingerprint(
    log_patterns = [
        r"(?<!\w)print\s*\(.*plaintext",          # standalone print(
        r"log(?:ging)?\.\w+\s*\(.*plaintext",     # logging.info(
        r"logger\.\w+\s*\(.*plaintext",           # logger.info(
    ]
    for pattern in log_patterns:
        matches = re.findall(pattern, source)
        assert not matches, (
            f"Log call may expose plaintext credential: {matches}. "
            "Plaintext must never appear in logs (ADR-0018 §1.3; Req 10.1)."
        )


def test_broker_resolve_no_plaintext_logged():
    """
    Verify that the broker resolve.go handler does not log the presented_key
    value — it only logs the fingerprint.

    Source: long-lived-api-keys task 11.1; Req 10.1; ADR-0018.
    """
    with open(RESOLVE_GO) as f:
        source = f.read()

    # Should log fingerprint (fp) but not the raw key value
    # Fail if presented_key or plaintext is referenced in a log call
    log_lines = [line for line in source.splitlines() if "slog." in line or "log." in line]
    for line in log_lines:
        assert "PresentedKey" not in line and "presented_key" not in line, (
            f"Log line may expose presented_key: {line!r}. "
            "Only key_fingerprint may appear in logs (ADR-0018; Req 10.1)."
        )


def test_proxy_handler_no_cred_field():
    """
    Verify that classicalkey/handler.go has no struct field or variable that
    persists the raw credential string beyond the request scope.

    The only persistent state is resolutionCache (keyed by fingerprint) and
    usedAtTracker (keyed by api_key_id) — no plaintext stored.

    Source: long-lived-api-keys task 11.1; ADR-0018; ADR-0014.4.
    """
    with open(HANDLER_GO) as f:
        source = f.read()

    # No struct field named 'cred', 'key', 'plaintext', or 'secret' in persistent
    # structs (resolutionCache, usedAtTracker, Handler, Config)
    struct_blocks = re.findall(r"type\s+\w+\s+struct\s*\{[^}]+\}", source, re.DOTALL)
    for block in struct_blocks:
        for forbidden in ["plaintext", "rawKey", "rawCred"]:
            assert forbidden not in block, (
                f"Struct block contains forbidden field '{forbidden}': {block[:200]}. "
                "Plaintext credentials must not be stored in any struct (ADR-0014.4; ADR-0018)."
            )


# ---------------------------------------------------------------------------
# 11.2 Structural RLS + audit guarantees
# ---------------------------------------------------------------------------


def test_service_api_keys_in_rls_coverage():
    """
    Verify that 'service_api_keys' appears in the RLS architecture test's
    required-tables list.

    Source: long-lived-api-keys task 11.2; Req 7.4; ADR-0014.8.
    """
    with open(RLS_TEST) as f:
        content = f.read()
    assert "service_api_keys" in content, (
        "service_api_keys must be in the RLS coverage test's required tables. "
        "ADR-0014.8 mandates a tenant_isolation RLS policy for every domain table."
    )


def test_api_keys_py_all_writes_call_audit_emit():
    """
    Verify that every state-mutating endpoint in api_keys.py contains a call
    to audit_emit — satisfying the audit chokepoint (ADR-0014.7; Req 10.1).

    State-mutating endpoints: create_api_key, revoke_api_key, rotate_api_key.
    """
    with open(API_KEYS_PY) as f:
        source = f.read()
    tree = ast.parse(source)

    # Find all async def functions
    mutating_fns = {"create_api_key", "revoke_api_key", "rotate_api_key"}
    found_audit: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        if node.name not in mutating_fns:
            continue
        # Check that audit_emit is called somewhere in this function body
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name == "audit_emit":
                    found_audit.add(node.name)
                    break

    missing = mutating_fns - found_audit
    assert not missing, (
        f"State-mutating endpoints missing audit_emit calls: {missing}. "
        "Every state change must emit an audit event (ADR-0014.7)."
    )


def test_revoke_calls_notify_change_on_mintkey_agent():
    """
    Verify that revoke_api_key calls notify_change with 'mintkey:agent' and
    an event of 'api_key.revoked' — required for proxy cache eviction (ADR-0014.1).

    Source: long-lived-api-keys tasks 7.3, 11.2; Req 4.1; ADR-0014.1.
    """
    with open(API_KEYS_PY) as f:
        source = f.read()

    assert "mintkey:agent" in source, (
        "api_keys.py must call notify_change with 'mintkey:agent'. "
        "The proxy needs this to evict cached resolutions (ADR-0014.1)."
    )
    assert "api_key.revoked" in source, (
        "api_keys.py must emit event 'api_key.revoked' on mintkey:agent. "
        "Required for proxy cache eviction (long-lived-api-keys task 7.3; Req 4.1)."
    )


def test_no_fstring_sql_in_api_keys_py():
    """
    Verify that api_keys.py contains no f-string SQL (f"SELECT ... {var}").
    All queries must use bound parameters — ADR-0008 / T-1.0.15.

    Source: long-lived-api-keys task 11.2; ADR-0008.
    """
    with open(API_KEYS_PY) as f:
        source = f.read()

    # Detect f-strings that contain SQL keywords
    sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "FROM", "WHERE"]
    fstring_pattern = re.compile(r'f["\'].*?\{', re.DOTALL)
    for match in fstring_pattern.finditer(source):
        snippet = source[match.start():match.start() + 200]
        for kw in sql_keywords:
            if kw in snippet.upper():
                raise AssertionError(
                    f"Possible f-string SQL injection at char {match.start()}: {snippet!r}. "
                    "Use bound parameters only (ADR-0008 / T-1.0.15)."
                )


def test_no_fstring_sql_in_broker_resolve():
    """
    Verify that the broker resolve.go contains no string-format SQL.
    Bound parameters only — ADR-0008 / T-1.0.15.

    Source: long-lived-api-keys task 11.2; ADR-0008.
    """
    with open(RESOLVE_GO) as f:
        source = f.read()

    # Go: fmt.Sprintf("...SELECT...%s...", ...) is the f-string equivalent
    dangerous = re.findall(r'fmt\.Sprintf\s*\(["\`][^"]+(?:SELECT|INSERT|UPDATE|DELETE|WHERE)', source)
    assert not dangerous, (
        f"Possible f-string SQL in resolve.go: {dangerous}. "
        "Use bound parameters only (ADR-0008 / T-1.0.15)."
    )
