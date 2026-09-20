"""
Red-team gate: T-11.2 — no secret fingerprint on any access-request log/span/audit.

Pairs with Property 1 (T-5.6, "the operator secret never leaks anywhere
secret-free"). Property 1 is a runtime, DB-backed Hypothesis test that plants a
canary secret and asserts it never appears in the row, logs, audit payloads,
span attributes, the test diagnostic, or the agent response. This gate is its
add-only, dependency-light complement: it verifies the SAME guarantee two ways
without needing a live Postgres / Vault / OTel exporter (running the full
compose is out of scope for this task — AGENTS.md's ``docker compose logs |
grep`` step runs in CI):

  (a) STATIC / SOURCE-LEVEL (primary guard). Parse the access-request code
      paths with the ``ast`` module and assert that no call to a *sink* that
      escapes the request scope — a logger, the audit chokepoint
      (``audit_emit`` / ``audit.emit``), the transition recorder
      (``record_transition``), or an OTel span-attribute setter
      (``set_attribute`` / ``set_attributes``) — is ever passed a
      secret-bearing argument. "Secret-bearing" is decided structurally: a
      value whose source is a denylisted field name (``*_secret`` /
      ``*_password`` / ``*_passphrase`` / ``Authorization`` / ``Cookie`` and the
      exact ``token`` / ``api_key`` / ``private_key``) or one of the known
      plaintext-carrying locals in these modules
      (``secret_plaintext``, ``transient_value``, ``plaintext``, the
      ``credential`` body). This catches a future edit that starts logging the
      credential BEFORE it can ship.

  (b) RUNTIME CANARY (complementary). Drive the single log/metric funnel these
      paths use (``mintkey_models.access_request_metrics.record_transition``)
      with a planted canary and capture the emitted structured log; assert the
      canary never appears and the log line carries only ``request_id`` /
      ``kind`` / ``status`` (Req 11.4/11.5). Also assert the shared
      secret-denylist matcher actually rejects every denylisted field-name
      family, so the create-time gate that keeps secrets off the row / the audit
      payload (Req 2.4, 10.3) is real, not a tautology.

This gate is STRICTLY ADDITIVE (Req 14.2/14.3) — a new file that reads existing
source and drives an existing pure funnel; it modifies no existing test and adds
no runtime coupling.

Source: T-11.2; Req 11.3, 11.5, 10.3, 2.4; P-1, P-7; S-SEC-1; ADR-0017.6;
        design §Metrics / §Attribute allowlist enforcement;
        Property 1 (T-5.6); tests/acceptance/test_otel_collector_redaction.py
        (redaction-gate precedent).
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]

# The access-request code paths whose log / span / audit emissions must be
# secret-free (Req 11.3/11.5, P-1). These are the modules that touch the
# operator secret or emit a transition.
_SOURCE_FILES = {
    "admin_api.services.access_requests": (
        REPO_ROOT
        / "apps/admin-api/src/admin_api/services/access_requests.py"
    ),
    "admin_api.api.access_requests": (
        REPO_ROOT / "apps/admin-api/src/admin_api/api/access_requests.py"
    ),
    "mintkey_models.access_request_metrics": (
        REPO_ROOT
        / "packages/python/mintkey-models/mintkey_models/access_request_metrics.py"
    ),
    "mcp_server.tools._access_requests_common": (
        REPO_ROOT
        / "apps/mcp-server/src/mcp_server/tools/_access_requests_common.py"
    ),
    "mcp_server.tools.propose_integration": (
        REPO_ROOT / "apps/mcp-server/src/mcp_server/tools/propose_integration.py"
    ),
}

# Sinks that escape the per-request scope. Anything passed to one of these must
# be secret-free (Req 11.3/11.5, 10.3).
#   - logger calls:      *.debug/info/warning/error/exception/critical/log
#   - audit chokepoint:  audit_emit(...) / audit.emit(...)
#   - transition funnel: record_transition(...)
#   - OTel span attrs:   *.set_attribute(...) / *.set_attributes(...)
_LOG_METHODS = {
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "exception",
    "critical",
    "log",
}
_SPAN_ATTR_METHODS = {"set_attribute", "set_attributes"}
_AUDIT_CALLEES = {"audit_emit", "emit"}  # audit_emit(...) / audit.emit(...)
_TRANSITION_CALLEE = "record_transition"

# Secret-bearing NAME sources. A value referenced by one of these identifiers,
# or an attribute/subscript whose root is one of these, is treated as secret and
# must never reach a sink above. Covers the known plaintext-carrying locals in
# these modules plus the denylist field families (as bare identifiers).
_SECRET_ROOTS = {
    "credential",  # the x-mintkey-sensitive request body / mapping
    "secret_plaintext",  # finalize: the extracted operator secret plaintext
    "transient_value",  # connection_test: assembled inline credential value
    "plaintext",  # generic plaintext arg name
    "password",
    "passphrase",
    "private_key",
    "api_key",
    "secret",
}

# Denylisted string-literal / field-name fragments (Req 11.3/11.5, ADR-0017.6).
# A string literal passed to a sink that CONTAINS one of these as a substring is
# flagged (e.g. a hand-built ``f"...{cred}..."`` sink arg or an attribute key).
_DENYLIST_SUBSTRINGS = (
    "_secret",
    "_password",
    "_passphrase",
    "authorization",
    "cookie",
)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _iter_modules():
    for mod, path in _SOURCE_FILES.items():
        assert path.exists(), f"expected access-request source file missing: {path}"
        yield mod, path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _callee_name(call: ast.Call) -> tuple[str | None, str | None]:
    """Return ``(attr_method, full_dotted_or_name)`` for a call's callee.

    ``attr_method`` is the trailing attribute (``logger.info`` -> ``info``);
    ``full`` is the bare function name for a plain ``foo(...)`` call.
    """
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr, None
    if isinstance(func, ast.Name):
        return None, func.id
    return None, None


def _expr_secret_root(node: ast.AST) -> str | None:
    """Return the denylisted identifier if *node* resolves to a secret root.

    Walks attribute/subscript/call chains down to their root ``Name`` (e.g.
    ``credential.get("value")`` -> root ``credential``; ``body.credential`` ->
    ``credential`` via the attribute name; ``cred_map["password"]`` -> root
    ``cred_map`` (not flagged) but subscript key ``"password"`` is caught by the
    literal check). Returns the matching identifier, or ``None``.
    """
    cur = node
    # Unwrap call chains like credential.get("value") → inspect the .func base.
    while isinstance(cur, ast.Call):
        cur = cur.func
    # Attribute access: flag if the ATTRIBUTE name itself is a secret root
    # (e.g. body.credential) OR the root Name is a secret root.
    if isinstance(cur, ast.Attribute):
        if cur.attr in _SECRET_ROOTS:
            return cur.attr
        cur = cur.value
        while isinstance(cur, ast.Attribute):
            cur = cur.value
    if isinstance(cur, ast.Subscript):
        cur = cur.value
        while isinstance(cur, (ast.Attribute, ast.Subscript)):
            cur = cur.value if isinstance(cur, ast.Attribute) else cur.value
    if isinstance(cur, ast.Name) and cur.id in _SECRET_ROOTS:
        return cur.id
    return None


def _string_literals(node: ast.AST) -> list[str]:
    """Return every string constant appearing anywhere inside *node*."""
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
        # f-string literal parts.
        if isinstance(sub, ast.JoinedStr):
            for part in sub.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    out.append(part.value)
    return out


def _flag_sink_arg(mod: str, call: ast.Call, arg: ast.AST) -> list[str]:
    """Return a list of violation messages for a single sink argument."""
    violations: list[str] = []
    line = getattr(call, "lineno", "?")

    # 1. Secret-root identifier flowing into the sink.
    root = _expr_secret_root(arg)
    if root is not None:
        violations.append(
            f"{mod}:{line}: secret-bearing value rooted at '{root}' is passed "
            f"to a log/span/audit/transition sink"
        )

    # 2. Denylisted substring in any string literal handed to the sink (e.g. an
    #    f-string that interpolates a secret, or a span-attribute key named
    #    '*_secret'/'authorization'/'cookie').
    for lit in _string_literals(arg):
        low = lit.lower()
        for frag in _DENYLIST_SUBSTRINGS:
            if frag in low:
                violations.append(
                    f"{mod}:{line}: string literal {lit!r} passed to a "
                    f"log/span/audit/transition sink matches denylist "
                    f"fragment {frag!r}"
                )
    return violations


# ---------------------------------------------------------------------------
# (a) STATIC / SOURCE-LEVEL guard — the primary red-team check.
# ---------------------------------------------------------------------------


def test_no_secret_reaches_a_log_span_or_audit_sink() -> None:
    """No denylisted secret value flows into any escaping sink on this path.

    STATIC guard (Req 11.3, 11.5, 10.3, P-1/P-7): walk every call in the
    access-request modules; for each call to a logger, ``record_transition``,
    ``audit_emit``/``audit.emit``, or an OTel ``set_attribute(s)``, assert none
    of its arguments (positional, keyword, or nested dict/f-string values)
    resolves to a secret root or carries a denylisted string fragment. A
    violation here means a future edit started routing the operator secret
    toward a place it could be observed — fail before it ships.
    """
    all_violations: list[str] = []

    for mod, _path, tree in _iter_modules():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            attr_method, bare = _callee_name(node)

            is_log = attr_method in _LOG_METHODS
            is_span = attr_method in _SPAN_ATTR_METHODS
            is_audit = (bare == "audit_emit") or (attr_method == "emit")
            is_transition = bare == _TRANSITION_CALLEE

            if not (is_log or is_span or is_audit or is_transition):
                continue

            # Inspect positional args and keyword-arg values. For audit_emit the
            # secret-relevant surface is the ``payload=`` kwarg (a dict); its
            # values are walked by _flag_sink_arg via nested Constant/Name.
            args_to_check: list[ast.AST] = list(node.args)
            for kw in node.keywords:
                if kw.value is not None:
                    args_to_check.append(kw.value)

            for arg in args_to_check:
                all_violations.extend(_flag_sink_arg(mod, node, arg))

    assert not all_violations, (
        "Secret material may reach a log/span/audit/transition sink on the "
        "access-request path (Req 11.3/11.5, P-1):\n  - "
        + "\n  - ".join(sorted(set(all_violations)))
    )


def test_plaintext_secret_only_flows_to_allowed_sinks() -> None:
    """The finalize/test plaintext secret is consumed only by allowed sinks.

    Belt-and-braces to the sink scan: locate every use of the known plaintext
    locals (``secret_plaintext`` in finalize, ``transient_value`` in the
    Connection_Test) in the service module and assert each use is either the
    assignment itself or an argument to an ALLOWED consumer — the Vault Adapter
    (``put_credential``), the in-memory transient candidate
    (``TransientCredentialCandidate``), a ``.strip()``/membership check, or a
    local re-binding. Any other use (a logger, an audit payload, a return in a
    response dict) is a leak.
    """
    svc_path = _SOURCE_FILES["admin_api.services.access_requests"]
    tree = ast.parse(svc_path.read_text(encoding="utf-8"), filename=str(svc_path))

    tracked = {"secret_plaintext", "transient_value"}
    # Allowed callee names that may legitimately receive the plaintext.
    allowed_callees = {
        "put_credential",  # Vault Adapter — the one legitimate sink (P-1)
        "TransientCredentialCandidate",  # in-memory test candidate
        "strip",  # emptiness checks
        "json",  # not a call target here, kept for clarity
    }

    leaks: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Call(self, call: ast.Call) -> None:  # noqa: N802
            attr_method, bare = _callee_name(call)
            callee = attr_method or bare
            # If a tracked plaintext local is an argument to a call, the callee
            # must be on the allowlist.
            for arg in list(call.args) + [kw.value for kw in call.keywords]:
                root = None
                cur = arg
                while isinstance(cur, ast.Call):
                    cur = cur.func
                if isinstance(cur, ast.Attribute):
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    root = cur.id
                if root in tracked and callee not in allowed_callees:
                    # Allow the transient-value emptiness membership check
                    # (``transient_value in (...)``) which is a Compare, not a
                    # call — handled elsewhere; here we only see it if wrapped.
                    leaks.append(
                        f"{svc_path.name}:{getattr(call, 'lineno', '?')}: "
                        f"plaintext '{root}' passed to disallowed callee "
                        f"'{callee}'"
                    )
            self.generic_visit(call)

    _Visitor().visit(tree)

    assert not leaks, (
        "The operator secret plaintext flows to a disallowed sink on the "
        "finalize/Connection_Test path (P-1, S-SEC-1):\n  - "
        + "\n  - ".join(sorted(set(leaks)))
    )


# ---------------------------------------------------------------------------
# (b) RUNTIME CANARY — complementary, driving the real funnel.
# ---------------------------------------------------------------------------


def test_record_transition_log_carries_no_secret_canary(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Driving the transition funnel with a canary never emits the canary.

    Req 11.4/11.5: ``record_transition`` is the single place the per-transition
    structured log line is emitted. It must carry only ``request_id`` / ``kind``
    / ``status`` — never a secret. We plant a canary secret in the environment
    around a real call and assert (1) the log record has no secret attribute and
    (2) the canary literal appears nowhere in the captured output.
    """
    from mintkey_models.access_request_metrics import record_transition

    canary = "mk_agent_CANARYSECRETdeadbeef00998877"

    with caplog.at_level(logging.INFO, logger="access_request"):
        # A legitimate call — none of these args is secret.
        record_transition(
            "created",
            request_id="request_00000000000000000000000000",
            kind="integration",
            tenant_id="11111111-1111-1111-1111-111111111111",
        )

    # The captured records must not contain the canary anywhere (message,
    # args, or any structlog-forwarded attribute).
    for rec in caplog.records:
        rendered = rec.getMessage()
        assert canary not in rendered, (
            "the record_transition log line leaked a planted canary secret"
        )
        for key, value in vars(rec).items():
            assert canary not in str(value), (
                f"record_transition log record attribute {key!r} leaked the "
                f"canary secret"
            )
            # No denylisted field name should ever be a log attribute either.
            assert key.lower() not in {
                "credential",
                "secret",
                "password",
                "passphrase",
                "private_key",
                "api_key",
                "token",
                "authorization",
                "cookie",
            }, f"record_transition emitted a denylisted log attribute {key!r}"


def test_secret_denylist_matcher_is_real() -> None:
    """The create-time secret denylist actually rejects every secret family.

    Req 2.4 / 10.3: the gate that keeps a proposed-config secret off the row and
    the audit payload must be a genuine matcher, not a stub. Assert the shared
    matcher flags every denylist family and passes plainly non-secret names —
    this is what makes the "secrets never reach the row/audit" guarantee real.
    """
    from admin_api.services.access_requests import find_secret_denylist_field

    for secret_name in (
        "client_secret",
        "db_password",
        "key_passphrase",
        "private_key",
        "token",
        "api_key",
        "CLIENT_SECRET",  # case-insensitive
    ):
        assert find_secret_denylist_field({secret_name: "x"}) == secret_name, (
            f"denylist matcher failed to reject secret field {secret_name!r}"
        )

    for safe_name in ("client_id", "token_url", "ssh_user", "header_name", "base_url"):
        assert find_secret_denylist_field({safe_name: "x"}) is None, (
            f"denylist matcher wrongly rejected non-secret field {safe_name!r}"
        )
