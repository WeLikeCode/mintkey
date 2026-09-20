"""
Access-request observability — Prometheus counters + structured transition log.

Shared between admin-api and mcp-server (both mint access-request rows against
the shared ``access_requests`` schema, so both must be able to record the
``created`` transition; ``approved`` / ``rejected`` / ``expired`` are emitted
by admin-api only). This is the single place the four transition counters are
declared and the single place the per-transition structured log line is
emitted, so the two services stay in lock-step.

Metrics (Req 11.2; design §Metrics) — each labelled ``kind`` + ``tenant_id``:

  - ``access_request_created_total``
  - ``access_request_approved_total``
  - ``access_request_rejected_total``
  - ``access_request_expired_total``

The idempotent Counter-declaration pattern (try/except ValueError + REGISTRY
lookup) mirrors ``mintkey_models.audit`` so module reimport / shared-registry
scenarios (pytest reload, multiple processes) do not raise ``ValueError`` on a
duplicate registration.

Structured log (Req 11.4, 11.5): on each transition a single JSON log entry is
emitted carrying ONLY ``request_id``, ``kind``, and ``status`` — no secret
material and no denylisted field ever reaches the log. structlog is used when
available (production container JSON handler) with a stdlib ``logging``
fallback, matching ``mcp_server.tools.bootstrap``.

Span attributes (Req 11.3, 11.5): this module sets NO span attributes. The
SDK-level ``mintkey_models.otel_redaction.RedactingSpanProcessor`` already
strips any attribute matching ``*_token`` / ``*_secret`` / ``*_password`` /
``*_passphrase`` / ``Authorization`` / ``Cookie`` (and value-shaped credentials)
from every exported span across all services (ADR-0017.6). The access-request
spans are covered by that global processor; keeping this recorder attribute-free
means no forbidden attribute is ever placed on an access-request span in the
first place — a belt-and-braces complement to the redaction filter, which is
left un-weakened.

Source: T-9.2; design §Metrics / §Attribute allowlist enforcement;
        Req 11.2, 11.3, 11.4, 11.5; P-7; ADR-0017.6.
"""
from __future__ import annotations

from typing import cast

# ---------------------------------------------------------------------------
# Structured transition logger — request_id / kind / status ONLY (Req 11.4/11.5)
# ---------------------------------------------------------------------------
# structlog in the production container (JSON handler); stdlib logging fallback
# elsewhere. Mirrors apps/mcp-server/src/mcp_server/tools/bootstrap.py.
try:
    import structlog as _structlog  # type: ignore[import-not-found]

    _logger = _structlog.get_logger("access_request")
    _STRUCTLOG = True
except ImportError:  # pragma: no cover - exercised only without structlog
    import logging

    _logger = logging.getLogger("access_request")
    _STRUCTLOG = False

# ---------------------------------------------------------------------------
# Prometheus counters — labelled kind + tenant_id (Req 11.2)
# Idempotent declaration (try/except ValueError + REGISTRY lookup) — mirrors
# mintkey_models.audit so reimport / shared-registry scenarios do not raise.
# ---------------------------------------------------------------------------
_PROMETHEUS_AVAILABLE = False
_created_total = None
_approved_total = None
_rejected_total = None
_expired_total = None

try:
    from prometheus_client import REGISTRY, Counter

    def _counter(name: str, doc: str) -> object:
        try:
            return Counter(name, doc, ["kind", "tenant_id"])
        except ValueError:
            # Registry lookup returns Collector; cast to Counter for strict-mode.
            return cast(Counter, REGISTRY._names_to_collectors.get(name))

    _created_total = _counter(
        "access_request_created_total",
        "Total access requests created, by kind and tenant",
    )
    _approved_total = _counter(
        "access_request_approved_total",
        "Total access requests approved, by kind and tenant",
    )
    _rejected_total = _counter(
        "access_request_rejected_total",
        "Total access requests rejected, by kind and tenant",
    )
    _expired_total = _counter(
        "access_request_expired_total",
        "Total access requests expired, by kind and tenant",
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover - prometheus_client always present in svc
    pass


_COUNTERS: dict[str, object] = {
    "created": _created_total,
    "approved": _approved_total,
    "rejected": _rejected_total,
    "expired": _expired_total,
}

# The four transition names, mapped to the resulting request status recorded in
# the structured log's ``status`` field (Req 11.4). ``created`` results in a
# ``pending`` row; the other three name their own terminal status.
_TRANSITION_STATUS: dict[str, str] = {
    "created": "pending",
    "approved": "approved",
    "rejected": "rejected",
    "expired": "expired",
}


def record_transition(transition: str, *, request_id: str, kind: str, tenant_id: str) -> None:
    """Record one access-request state transition — metric + structured log.

    ``transition`` is one of ``created`` / ``approved`` / ``rejected`` /
    ``expired``. Increments the matching ``access_request_<transition>_total``
    counter labelled ``kind`` + ``tenant_id`` (Req 11.2) and emits a single
    structured JSON log entry carrying ONLY ``request_id``, ``kind``, and the
    resulting ``status`` (Req 11.4) — never a secret or denylisted value
    (Req 11.5). Sets no span attribute (the global redaction processor owns
    span hygiene, ADR-0017.6).

    Safe to call from either service and in environments without
    ``prometheus_client`` (the increment is skipped) — it never raises on the
    hot path.
    """
    status = _TRANSITION_STATUS.get(transition, transition)

    counter = _COUNTERS.get(transition)
    if _PROMETHEUS_AVAILABLE and counter is not None:
        counter.labels(kind=kind, tenant_id=tenant_id).inc()  # type: ignore[attr-defined]

    # Structured log carrying request_id / kind / status ONLY (Req 11.4/11.5).
    event = f"access_request.{transition}"
    if _STRUCTLOG:
        _logger.info(event, request_id=request_id, kind=kind, status=status)
    else:  # pragma: no cover - stdlib fallback path
        _logger.info(
            "%s request_id=%s kind=%s status=%s",
            event,
            request_id,
            kind,
            status,
        )
