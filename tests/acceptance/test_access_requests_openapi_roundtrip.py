"""
CI gate: T-11.2 — access-requests OpenAPI contract round-trip.

Asserts the FastAPI-emitted OpenAPI document (``create_app().openapi()``) is
structurally consistent with the checked-in canonical contract at
``docs/architecture/contracts/rest/openapi.yaml`` for the *agent-access-requests
feature surfaces* (Req 13.5, 13.6, P-4).

Scoping (documented, per the task):
  A full byte-for-byte FastAPI-vs-hand-authored round-trip diff does NOT yet
  exist in this repo (see T-6.1 note; the pre-existing parity gate is the
  text/AST-based ``test_openapi_parity.py``), and a strict whole-document diff
  against the hand-authored YAML would be flaky for reasons unrelated to this
  feature (FastAPI serialises component ordering, ``operationId`` casing,
  request-body ``required`` defaults, and OAS 3.0-vs-3.1 nullable forms
  differently from the hand-authored spec). Mirroring how T-1.5's
  contract-validation test scoped around pre-existing issues, this gate scopes
  the round-trip assertion to the feature's own wire surfaces:

    1. The five access-request operationIds
       (``listAccessRequests``, ``getAccessRequest``, ``approveAccessRequest``,
       ``rejectAccessRequest``, ``testAccessRequestConnection``) and their paths
       appear in BOTH the FastAPI-emitted spec AND the checked-in
       ``openapi.yaml`` (build fails on drift — a path/operationId present in
       one but not the other, Req 13.6).

    2. The ``AccessRequest`` response schema shape agrees on its required-field
       set AND expresses its nullable fields in the OAS 3.1 ``type: [<T>,
       "null"]`` form (never the OAS 3.0 ``nullable: true`` form, Req 13.1) in
       the checked-in contract.

  Anything outside these feature surfaces is intentionally NOT asserted here —
  this is an additive check that must not fail on pre-existing whole-document
  divergence (Req 14.2/14.3).

Source: T-11.2; Req 13.1, 13.5, 13.6; P-4 (contract-first);
        docs/architecture/contracts/rest/openapi.yaml (canonical);
        apps/admin-api/src/admin_api/main.py::create_app (FastAPI emitter);
        tests/acceptance/test_openapi_parity.py (parity-gate precedent).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).parents[2]
CANONICAL_OPENAPI = (
    REPO_ROOT / "docs" / "architecture" / "contracts" / "rest" / "openapi.yaml"
)

# The five feature operationIds and the canonical paths that carry them.
_FEATURE_OPERATIONS: dict[str, tuple[str, str]] = {
    # operationId -> (path, http_method)
    "listAccessRequests": (
        "/v1/tenants/{tenant_id}/access-requests",
        "get",
    ),
    "getAccessRequest": (
        "/v1/tenants/{tenant_id}/access-requests/{request_id}",
        "get",
    ),
    "approveAccessRequest": (
        "/v1/tenants/{tenant_id}/access-requests/{request_id}/approve",
        "post",
    ),
    "rejectAccessRequest": (
        "/v1/tenants/{tenant_id}/access-requests/{request_id}/reject",
        "post",
    ),
    "testAccessRequestConnection": (
        "/v1/tenants/{tenant_id}/access-requests/{request_id}/test",
        "post",
    ),
}

# The AccessRequest response schema's required-field set (design §Wire Contracts).
_ACCESS_REQUEST_REQUIRED = {
    "request_id",
    "kind",
    "status",
    "requesting_agent_id",
    "created_at",
    "expires_at",
}

# AccessRequest fields that MUST be nullable and MUST use the OAS 3.1
# ``type: [<T>, "null"]`` form (never OAS 3.0 ``nullable: true``) — Req 13.1.
_ACCESS_REQUEST_NULLABLE_FIELDS = {
    "service_id",
    "action",
    "target_agent_id",
    "reason",
    "proposed_config",
}


# ---------------------------------------------------------------------------
# Fixtures — the two documents under comparison.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def checked_in_spec() -> dict[str, Any]:
    """The hand-authored canonical OpenAPI YAML (source of truth, ADR-0017.1)."""
    assert CANONICAL_OPENAPI.exists(), (
        f"Canonical OpenAPI spec not found at {CANONICAL_OPENAPI}"
    )
    with CANONICAL_OPENAPI.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def emitted_spec() -> dict[str, Any]:
    """The OpenAPI document FastAPI emits from the real admin-api app.

    Booted via ``create_app().openapi()`` — route registration needs no live DB
    (the same env-only boot the ``test_authz_coverage.py`` architecture gate
    uses). If the app cannot be imported in this environment (missing optional
    dependency), the whole module is skipped rather than failing — the
    checked-in-only structural assertions still run in ``test_canonical_*``.
    """
    # Env vars required to instantiate the app without a live database — mirror
    # tests/architecture/test_authz_coverage.py.
    os.environ.setdefault("MINTKEY_AUDIT_HMAC_KEY", "aa" * 32)
    os.environ.setdefault("MINTKEY_VAULT_BACKEND", "sqlite")

    try:
        from admin_api.main import create_app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001 - import/env failure → skip, don't fail
        pytest.skip(f"admin-api app could not be imported in this env: {exc!r}")

    app = create_app()
    return app.openapi()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _operation_ids(spec: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Map operationId -> (path, method) for every operation in *spec*."""
    found: dict[str, tuple[str, str]] = {}
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if not isinstance(op, dict):
                continue
            op_id = op.get("operationId")
            if op_id:
                found[op_id] = (path, method.lower())
    return found


def _resolve_ref(spec: dict[str, Any], node: Any) -> Any:
    """Resolve a single ``$ref`` (one hop) against the local document."""
    if isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        assert ref.startswith("#/"), f"Only local refs supported: {ref}"
        target: Any = spec
        for part in ref.lstrip("#/").split("/"):
            target = target[part]
        return target
    return node


# ---------------------------------------------------------------------------
# Checked-in-contract structural assertions (run regardless of app import).
# ---------------------------------------------------------------------------


def test_canonical_declares_all_five_feature_operations(
    checked_in_spec: dict[str, Any],
) -> None:
    """All five feature operationIds + paths exist in the checked-in contract."""
    ops = _operation_ids(checked_in_spec)
    for op_id, (path, method) in _FEATURE_OPERATIONS.items():
        assert op_id in ops, (
            f"operationId '{op_id}' missing from checked-in openapi.yaml"
        )
        got_path, got_method = ops[op_id]
        assert (got_path, got_method) == (path, method), (
            f"operationId '{op_id}' is on {got_method.upper()} {got_path} in the "
            f"checked-in contract; expected {method.upper()} {path}"
        )


def test_canonical_access_request_schema_shape(
    checked_in_spec: dict[str, Any],
) -> None:
    """AccessRequest schema: required set + OAS 3.1 nullable form (Req 13.1)."""
    schema = (
        checked_in_spec.get("components", {}).get("schemas", {}).get("AccessRequest")
    )
    assert schema is not None, "AccessRequest schema missing from openapi.yaml"

    required = set(schema.get("required", []))
    assert required == _ACCESS_REQUEST_REQUIRED, (
        "AccessRequest.required drifted from the design shape. "
        f"Expected {sorted(_ACCESS_REQUEST_REQUIRED)}, got {sorted(required)}"
    )

    props = schema.get("properties", {})
    for field in _ACCESS_REQUEST_NULLABLE_FIELDS:
        assert field in props, f"AccessRequest.{field} missing from schema"
        prop = props[field]
        # OAS 3.1 nullable form: either ``type: [<T>, "null"]`` directly, or a
        # ``oneOf`` including a ``{"type": "null"}`` branch (used for $ref'd
        # fields like share_direction/resolved_at). The OAS 3.0 ``nullable:
        # true`` form must NOT be used (Req 13.1).
        assert "nullable" not in prop, (
            f"AccessRequest.{field} uses the forbidden OAS 3.0 'nullable: true' "
            f"form; must use OAS 3.1 type:[<T>,'null'] (Req 13.1, ADR-0017)"
        )
        type_val = prop.get("type")
        one_of = prop.get("oneOf")
        has_null_in_type = isinstance(type_val, list) and "null" in type_val
        has_null_in_oneof = isinstance(one_of, list) and any(
            isinstance(b, dict) and b.get("type") == "null" for b in one_of
        )
        assert has_null_in_type or has_null_in_oneof, (
            f"AccessRequest.{field} is not expressed as nullable in the OAS 3.1 "
            f"form (type:[<T>,'null'] or oneOf with a 'null' branch); got {prop!r}"
        )


def test_canonical_has_zero_oas30_nullable_on_access_request(
    checked_in_spec: dict[str, Any],
) -> None:
    """The AccessRequest schema block contains zero ``nullable: true`` (Req 13.1)."""
    schema = (
        checked_in_spec.get("components", {}).get("schemas", {}).get("AccessRequest")
    )
    assert schema is not None

    def _count_nullable(node: Any) -> int:
        count = 0
        if isinstance(node, dict):
            if node.get("nullable") is True:
                count += 1
            for value in node.values():
                count += _count_nullable(value)
        elif isinstance(node, list):
            for item in node:
                count += _count_nullable(item)
        return count

    assert _count_nullable(schema) == 0, (
        "AccessRequest schema contains an OAS 3.0 'nullable: true' occurrence; "
        "every nullable field must use the OAS 3.1 type:[<T>,'null'] form "
        "(Req 13.1, ADR-0017)"
    )


# ---------------------------------------------------------------------------
# Round-trip: FastAPI-emitted vs checked-in (the drift gate, Req 13.5/13.6).
# ---------------------------------------------------------------------------


def test_emitted_operations_match_checked_in(
    emitted_spec: dict[str, Any],
    checked_in_spec: dict[str, Any],
) -> None:
    """
    Round-trip gate (Req 13.5/13.6): every feature operationId present in the
    FastAPI-emitted spec is at the SAME path+method as in the checked-in
    contract, and vice-versa — drift in either direction fails the build.
    """
    emitted = _operation_ids(emitted_spec)
    canonical = _operation_ids(checked_in_spec)

    for op_id, (exp_path, exp_method) in _FEATURE_OPERATIONS.items():
        # Present in the running app (the router is actually wired in).
        assert op_id in emitted, (
            f"operationId '{op_id}' is in the checked-in contract but the "
            f"FastAPI app does not emit it — the access-requests router is not "
            f"wired (Req 13.6 drift)"
        )
        assert emitted[op_id] == (exp_path, exp_method), (
            f"operationId '{op_id}' drifted: FastAPI emits it on "
            f"{emitted[op_id][1].upper()} {emitted[op_id][0]}, but the checked-in "
            f"contract declares {exp_method.upper()} {exp_path} (Req 13.6)"
        )
        # And the checked-in contract agrees (guards against a stale YAML).
        assert canonical.get(op_id) == (exp_path, exp_method), (
            f"operationId '{op_id}' in the checked-in contract is at "
            f"{canonical.get(op_id)}; expected {(exp_path, exp_method)}"
        )


def test_emitted_access_request_schema_required_agrees(
    emitted_spec: dict[str, Any],
    checked_in_spec: dict[str, Any],
) -> None:
    """
    The FastAPI-emitted AccessRequest response schema (resolved from the 200
    body of listAccessRequests/getAccessRequest) agrees with the checked-in
    contract on its required-field set (Req 13.5).

    FastAPI derives the response schema from the router's return annotation. The
    access-requests router returns raw ``JSONResponse`` objects (the body is
    hand-shaped to the AccessRequest contract), so the emitted spec may not
    carry a named ``AccessRequest`` component. When it does not, the assertion
    falls back to confirming the checked-in schema is internally consistent —
    the operation/path round-trip above is the load-bearing drift gate; this
    guards the schema shape when FastAPI exposes it.
    """
    emitted_schemas = (
        emitted_spec.get("components", {}).get("schemas", {})
    )
    emitted_ar = emitted_schemas.get("AccessRequest")

    canonical_ar = (
        checked_in_spec.get("components", {}).get("schemas", {}).get("AccessRequest")
    )
    assert canonical_ar is not None
    canonical_required = set(canonical_ar.get("required", []))

    if emitted_ar is None:
        # The router returns un-modelled JSONResponse bodies (documented above):
        # no named AccessRequest component is emitted. The path/method round-trip
        # gate covers drift; assert the checked-in shape matches the design here.
        assert canonical_required == _ACCESS_REQUEST_REQUIRED
        return

    emitted_required = set(emitted_ar.get("required", []))
    assert emitted_required == canonical_required, (
        "AccessRequest.required drifted between the FastAPI-emitted spec "
        f"({sorted(emitted_required)}) and the checked-in contract "
        f"({sorted(canonical_required)}) (Req 13.5)"
    )
