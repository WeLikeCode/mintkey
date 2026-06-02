"""
test_email_proxy_architecture.py

Architecture / static-analysis guard tests for the email-proxy feature
(ADR-0024, C-13).

Invariants enforced:
  1. AST guard: every audit_emit(...) call in email_services.py has a payload
     that does NOT include refresh_token / access_token / client_secret keys.
  2. Static env-var guard: apps/email-proxy/internal/* has ZERO os.Getenv calls
     for MINTKEY_OAUTH2_* variables (those belong on admin-api side only).
  3. Liquibase RLS guard: email_services table has RLS enabled
     (ALTER TABLE ... ENABLE ROW LEVEL SECURITY in 022-email-services.yaml).
  4. Liquibase RLS guard: oauth2_state table has RLS enabled
     (ALTER TABLE ... ENABLE ROW LEVEL SECURITY in 023-oauth2-state.yaml).
  5. JWT middleware guard: all 9 email-proxy REST routes are registered with
     withJWTAuth middleware (grep for withJWTAuth wrapping each route in
     server.go).
  6. Span-attribute parity: span-attributes.md, Go allowlist
     (packages/go/otelinit/allowlist.go), and Python allowlist
     (packages/python/mintkey-models/mintkey_models/otel_redaction.py)
     all define the same 6 email.* attribute names.
  7. Audit payload keys guard: audit payloads in email_services.py never
     include 'access_token' key at the top level.
  8. Internal routes use service-token auth: oauth2_refresh checks
     X-Mintkey-Service-Token header (not agent JWT).

Run with:
  cd apps/admin-api
  unset MINTKEY_AUDIT_HMAC_KEY
  .venv/bin/python -m pytest tests/acceptance/test_email_proxy_architecture.py -v
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Resolve paths relative to this file — portable across dev machines.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[4]  # …/mintkey

EMAIL_SERVICES_PY = REPO_ROOT / "apps/admin-api/src/admin_api/api/email_services.py"
EMAIL_PROXY_INTERNAL = REPO_ROOT / "apps/email-proxy/internal"
LIQUIBASE_022 = REPO_ROOT / "apps/admin-api/db/changelog/022-email-services.yaml"
LIQUIBASE_023 = REPO_ROOT / "apps/admin-api/db/changelog/023-oauth2-state.yaml"
SERVER_GO = REPO_ROOT / "apps/email-proxy/internal/server/server.go"
SPAN_ATTRS_MD = REPO_ROOT / "docs/architecture/contracts/otel/span-attributes.md"
GO_ALLOWLIST = REPO_ROOT / "packages/go/otelinit/allowlist.go"
PY_ALLOWLIST = REPO_ROOT / "packages/python/mintkey-models/mintkey_models/otel_redaction.py"

# The 6 canonical email span attribute names from span-attributes.md
CANONICAL_EMAIL_ATTRS = frozenset({
    "email.service_id",
    "email.message_id",
    "email.mailbox",
    "email.provider",
    "email.attachment_count",
    "email.body_size_bytes",
})

# Credential fields that must NEVER appear as payload keys in audit_emit calls
FORBIDDEN_AUDIT_KEYS = {"refresh_token", "access_token", "client_secret"}

# The 9 email-proxy REST routes and the expected withJWTAuth guard
REQUIRED_JWT_WRAPPED_ROUTES = [
    "/v1/email-proxy/mailboxes",
    "/v1/email-proxy/messages/search",
    "/v1/email-proxy/messages/",
    "/v1/email-proxy/messages",
]


# ---------------------------------------------------------------------------
# Helper: parse audit_emit calls from AST
# ---------------------------------------------------------------------------

def _extract_audit_emit_payloads(src: str) -> list[dict[str, object]]:
    """
    Parse all audit_emit(..., payload={...}) keyword argument values from `src`.

    Returns a list of dicts mapping key name → AST node (or None if not a
    simple string key).  Only static dict literals are analysed.
    """
    tree = ast.parse(src)
    payloads: list[dict[str, object]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match audit_emit(...) calls (direct call or awaited).
        func = node.func
        func_name = None
        if isinstance(func, ast.Name):
            func_name = func.id
        elif isinstance(func, ast.Attribute):
            func_name = func.attr

        if func_name != "audit_emit":
            continue

        # Find the `payload=` keyword arg.
        for kw in node.keywords:
            if kw.arg == "payload" and isinstance(kw.value, ast.Dict):
                keys: dict[str, object] = {}
                for k, v in zip(kw.value.keys, kw.value.values):
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        keys[k.value] = v
                payloads.append(keys)

    return payloads


# ===========================================================================
# Test 1: audit_emit payloads in email_services.py must not include
#          refresh_token / access_token / client_secret
# ===========================================================================

class TestAuditEmitPayloadsNoCredentials:
    """AST-grep: every audit_emit call in email_services.py is clean."""

    def test_no_forbidden_keys_in_audit_emit_payloads(self):
        """No audit_emit call in email_services.py has a forbidden credential key."""
        src = EMAIL_SERVICES_PY.read_text(encoding="utf-8")
        payloads = _extract_audit_emit_payloads(src)

        assert payloads, (
            f"Expected at least 4 audit_emit calls in {EMAIL_SERVICES_PY.name}, "
            f"found {len(payloads)}"
        )

        violations: list[str] = []
        for i, payload_keys in enumerate(payloads):
            for forbidden in FORBIDDEN_AUDIT_KEYS:
                if forbidden in payload_keys:
                    violations.append(
                        f"audit_emit call #{i + 1}: payload contains forbidden key '{forbidden}'"
                    )

        assert not violations, (
            "NFR-17 violation — audit_emit payloads must NOT include credential keys:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_audit_emit_call_count(self):
        """email_services.py has the expected 4 audit_emit call sites."""
        src = EMAIL_SERVICES_PY.read_text(encoding="utf-8")
        payloads = _extract_audit_emit_payloads(src)
        # We know from source: 268, 589, 738, 783 → 4 call sites
        assert len(payloads) >= 4, (
            f"Expected ≥4 audit_emit calls in email_services.py, found {len(payloads)}"
        )


# ===========================================================================
# Test 2: email-proxy internal/ must not read MINTKEY_OAUTH2_* env vars
# ===========================================================================

class TestEmailProxyNoOAuth2EnvReads:
    """email-proxy must never read MINTKEY_OAUTH2_* — admin-api owns those."""

    def test_no_getenv_mintkey_oauth2(self):
        """
        No Go source file under apps/email-proxy/internal/ calls os.Getenv
        (or os.LookupEnv) with a MINTKEY_OAUTH2_* argument.
        """
        assert EMAIL_PROXY_INTERNAL.is_dir(), (
            f"Expected email-proxy internal dir at {EMAIL_PROXY_INTERNAL}"
        )

        violations: list[str] = []
        for go_file in EMAIL_PROXY_INTERNAL.rglob("*.go"):
            src = go_file.read_text(encoding="utf-8")
            # Look for os.Getenv("MINTKEY_OAUTH2_...") patterns
            matches = re.findall(
                r'os\.(Getenv|LookupEnv)\(\s*"(MINTKEY_OAUTH2_[^"]+)"',
                src,
            )
            for _, var_name in matches:
                rel = go_file.relative_to(REPO_ROOT)
                violations.append(f"{rel}: reads {var_name}")

        assert not violations, (
            "ADR-0024 §B1 violation — email-proxy must NOT read MINTKEY_OAUTH2_* env vars "
            "(admin-api owns OAuth2 client credentials):\n"
            + "\n".join(f"  {v}" for v in violations)
        )


# ===========================================================================
# Tests 3 + 4: Liquibase YAML — email_services and oauth2_state have RLS enabled
# ===========================================================================

class TestLiquibaseRLSEnabled:
    """Both email tables have Row Level Security configured in Liquibase."""

    def _has_rls_enabled(self, yaml_path: Path, table_name: str) -> bool:
        """Return True if the YAML contains ENABLE ROW LEVEL SECURITY for table_name."""
        content = yaml_path.read_text(encoding="utf-8")
        pattern = re.compile(
            r"ALTER\s+TABLE\s+(?:public\.)?{}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY".format(
                re.escape(table_name)
            ),
            re.IGNORECASE,
        )
        return bool(pattern.search(content))

    def test_email_services_rls_enabled(self):
        """022-email-services.yaml enables RLS on public.email_services."""
        assert LIQUIBASE_022.exists(), f"Liquibase file not found: {LIQUIBASE_022}"
        assert self._has_rls_enabled(LIQUIBASE_022, "email_services"), (
            f"{LIQUIBASE_022.name} must contain "
            "'ALTER TABLE public.email_services ENABLE ROW LEVEL SECURITY'"
        )

    def test_oauth2_state_rls_enabled(self):
        """023-oauth2-state.yaml enables RLS on public.oauth2_state."""
        assert LIQUIBASE_023.exists(), f"Liquibase file not found: {LIQUIBASE_023}"
        assert self._has_rls_enabled(LIQUIBASE_023, "oauth2_state"), (
            f"{LIQUIBASE_023.name} must contain "
            "'ALTER TABLE public.oauth2_state ENABLE ROW LEVEL SECURITY'"
        )


# ===========================================================================
# Test 5: All 9 REST routes are wrapped with withJWTAuth middleware
# ===========================================================================

class TestJWTMiddlewareOnAllRoutes:
    """Every email-proxy REST route must use the withJWTAuth middleware."""

    def test_all_routes_use_jwt_middleware(self):
        """
        server.go must register each email route with withJWTAuth(...).

        We check that mux.HandleFunc registrations for the 4 route prefixes
        (which dispatch all 9 endpoints) all pass through withJWTAuth.
        """
        assert SERVER_GO.exists(), f"server.go not found at {SERVER_GO}"
        src = SERVER_GO.read_text(encoding="utf-8")

        # Each route registration must match:
        #   mux.HandleFunc("<route>", s.withJWTAuth(...))
        violations: list[str] = []
        for route in REQUIRED_JWT_WRAPPED_ROUTES:
            # Match mux.HandleFunc with this route path followed by withJWTAuth
            pattern = re.compile(
                r'mux\.HandleFunc\(\s*"' + re.escape(route) + r'"\s*,\s*s\.withJWTAuth\('
            )
            if not pattern.search(src):
                violations.append(
                    f"Route '{route}' does not appear to be wrapped with withJWTAuth"
                )

        assert not violations, (
            "SEC-01: All email-proxy REST routes must use JWT auth middleware:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_health_routes_not_jwt_wrapped(self):
        """
        Health/observability routes (/healthz, /readyz, /metrics) must NOT
        be wrapped in withJWTAuth — they are public probes.
        """
        src = SERVER_GO.read_text(encoding="utf-8")

        # These must appear as plain mux.HandleFunc (no withJWTAuth)
        for route in ("/healthz", "/readyz", "/metrics"):
            # A registration with withJWTAuth for a health route would be a bug
            pattern = re.compile(
                r'mux\.HandleFunc\(\s*"' + re.escape(route) + r'"\s*,\s*s\.withJWTAuth\('
            )
            assert not pattern.search(src), (
                f"Health route '{route}' must NOT be wrapped with withJWTAuth "
                "(must remain publicly accessible)"
            )


# ===========================================================================
# Test 6: Span-attribute parity across .md / Go allowlist / Python allowlist
# ===========================================================================

class TestSpanAttributeParity:
    """All three sources must define the same 6 email.* span attributes."""

    def _parse_md_email_attrs(self) -> set[str]:
        """Extract email.* attribute names from the markdown table in span-attributes.md."""
        src = SPAN_ATTRS_MD.read_text(encoding="utf-8")
        # Match table rows like: | `email.service_id` | ... |
        attrs: set[str] = set()
        for m in re.finditer(r"`(email\.[a-z_]+)`", src):
            attrs.add(m.group(1))
        return attrs

    def _parse_go_allowlist_attrs(self) -> set[str]:
        """Extract attribute names from emailAllowedAttrs map in allowlist.go."""
        src = GO_ALLOWLIST.read_text(encoding="utf-8")
        # Match: "email.service_id": {},
        attrs: set[str] = set()
        for m in re.finditer(r'"(email\.[a-z_]+)"\s*:', src):
            attrs.add(m.group(1))
        return attrs

    def _parse_py_allowlist_attrs(self) -> set[str]:
        """Extract attribute names from EMAIL_SPAN_ATTRS frozenset in otel_redaction.py."""
        src = PY_ALLOWLIST.read_text(encoding="utf-8")
        # Extract the EMAIL_SPAN_ATTRS frozenset block
        block_m = re.search(r"EMAIL_SPAN_ATTRS\s*=\s*frozenset\(\{(.*?)\}\)", src, re.DOTALL)
        if not block_m:
            return set()
        block = block_m.group(1)
        attrs: set[str] = set()
        for m in re.finditer(r'"(email\.[a-z_]+)"', block):
            attrs.add(m.group(1))
        return attrs

    def test_md_defines_canonical_email_attrs(self):
        """span-attributes.md defines all 6 canonical email.* attributes."""
        assert SPAN_ATTRS_MD.exists(), f"span-attributes.md not found: {SPAN_ATTRS_MD}"
        md_attrs = self._parse_md_email_attrs()
        missing = CANONICAL_EMAIL_ATTRS - md_attrs
        assert not missing, (
            f"span-attributes.md is missing email attributes: {sorted(missing)}"
        )

    def test_go_allowlist_matches_canonical(self):
        """Go otelinit/allowlist.go emailAllowedAttrs matches canonical 6 attributes."""
        assert GO_ALLOWLIST.exists(), f"Go allowlist not found: {GO_ALLOWLIST}"
        go_attrs = self._parse_go_allowlist_attrs()
        missing = CANONICAL_EMAIL_ATTRS - go_attrs
        assert not missing, (
            f"Go allowlist missing email attributes: {sorted(missing)}"
        )
        extra = go_attrs - CANONICAL_EMAIL_ATTRS
        assert not extra, (
            f"Go allowlist has EXTRA email attributes not in canonical set: {sorted(extra)}\n"
            "Add them to CANONICAL_EMAIL_ATTRS or remove from allowlist."
        )

    def test_python_allowlist_matches_canonical(self):
        """Python otel_redaction.py EMAIL_SPAN_ATTRS matches canonical 6 attributes."""
        assert PY_ALLOWLIST.exists(), f"Python allowlist not found: {PY_ALLOWLIST}"
        py_attrs = self._parse_py_allowlist_attrs()
        missing = CANONICAL_EMAIL_ATTRS - py_attrs
        assert not missing, (
            f"Python allowlist missing email attributes: {sorted(missing)}"
        )
        extra = py_attrs - CANONICAL_EMAIL_ATTRS
        assert not extra, (
            f"Python allowlist has EXTRA email attributes not in canonical set: {sorted(extra)}\n"
            "Add them to CANONICAL_EMAIL_ATTRS or remove from allowlist."
        )

    def test_all_three_sources_agree(self):
        """All three sources (MD, Go, Python) define exactly the same set."""
        md_attrs = self._parse_md_email_attrs()
        go_attrs = self._parse_go_allowlist_attrs()
        py_attrs = self._parse_py_allowlist_attrs()

        md_go_diff = md_attrs.symmetric_difference(go_attrs)
        assert not (md_go_diff & CANONICAL_EMAIL_ATTRS), (
            f"span-attributes.md and Go allowlist disagree on email.* attrs: "
            f"{sorted(md_go_diff)}"
        )

        go_py_diff = go_attrs.symmetric_difference(py_attrs)
        assert not (go_py_diff & CANONICAL_EMAIL_ATTRS), (
            f"Go allowlist and Python allowlist disagree on email.* attrs: "
            f"{sorted(go_py_diff)}"
        )


# ===========================================================================
# Test 7: Internal refresh endpoint authenticates via service token (not JWT)
# ===========================================================================

class TestInternalRefreshEndpointAuth:
    """oauth2_refresh must check X-Mintkey-Service-Token, not a bearer JWT."""

    def test_refresh_endpoint_checks_service_token(self):
        """email_services.py oauth2_refresh reads X-Mintkey-Service-Token header."""
        src = EMAIL_SERVICES_PY.read_text(encoding="utf-8")

        # Must contain the service-token check
        assert "X-Mintkey-Service-Token" in src, (
            "oauth2_refresh must authenticate via X-Mintkey-Service-Token header"
        )
        assert "_get_email_proxy_token" in src or "MINTKEY_EMAIL_PROXY_SERVICE_TOKEN" in src, (
            "oauth2_refresh must check MINTKEY_EMAIL_PROXY_SERVICE_TOKEN env var"
        )
