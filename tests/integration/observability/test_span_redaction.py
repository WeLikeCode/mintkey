"""
Integration test: span-attribute redaction via RedactingSpanProcessor.

Verifies the SDK-level redaction layer (T-1.0.14 / ADR-0017.6):

OTEL-SEC-1  No span attribute VALUE contains an injected plaintext credential.
OTEL-SEC-2  No span attribute VALUE contains Mintkey token prefixes
            (mk_agent_, mk_svckey_, Bearer ...).
OTEL-SEC-3  Exact-match forbidden attribute names are absent from exported spans.
OTEL-SEC-4  Safe, non-sensitive attributes (tenant_id, key_version, etc.) survive.
OTEL-SEC-5  The allowlisted attributes (_key_id, _key_version, _key_fingerprint)
            are NOT redacted by the suffix filter.

Strategy: Build a TracerProvider backed by InMemorySpanExporter, wrapped with
RedactingSpanProcessor.  Emit spans programmatically and via FastAPI HTTP
requests, then assert on the captured spans.  No running collector, Jaeger, or
docker-compose stack required.

Source: WS-6; ADR-0017.6; T-1.0.14.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure source trees are importable (mirrors tests/conftest.py).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
for _src in (
    _REPO_ROOT / "admin-api" / "src",
    _REPO_ROOT / "mintkey-models",
):
    _s = str(_src)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.resources import Resource

from mintkey_models.otel_redaction import RedactingSpanProcessor


# ---------------------------------------------------------------------------
# Secret values injected into spans / requests that MUST NOT appear in output.
# ---------------------------------------------------------------------------
_INJECTED_CREDENTIAL = "leakme-secret-12345"
_INJECTED_AGENT_KEY  = "mk_agent_testkey_shouldnotleak_0987"
_INJECTED_SVC_KEY    = "mk_svckey_testkey_shouldnotleak_0987"
_INJECTED_BEARER     = f"Bearer {_INJECTED_AGENT_KEY}"

_ALL_INJECTED_SECRETS = (
    _INJECTED_CREDENTIAL,
    _INJECTED_AGENT_KEY,
    _INJECTED_SVC_KEY,
    _INJECTED_BEARER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_string_attr_values(spans) -> list[str]:
    """Collect every string-typed attribute value across a list of finished spans."""
    out: list[str] = []
    for span in spans:
        for v in (span.attributes or {}).values():
            if isinstance(v, str):
                out.append(v)
    return out


def _all_attr_names(spans) -> set[str]:
    """Return all attribute keys across spans as a set."""
    out: set[str] = set()
    for span in spans:
        out.update((span.attributes or {}).keys())
    return out


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def exporter() -> InMemorySpanExporter:
    """Fresh InMemorySpanExporter per test."""
    return InMemorySpanExporter()


@pytest.fixture
def redacting_provider(exporter) -> TracerProvider:
    """TracerProvider with RedactingSpanProcessor wrapping the in-memory exporter."""
    resource = Resource.create({"service.name": "test-service"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        RedactingSpanProcessor(SimpleSpanProcessor(exporter))
    )
    return provider


# ===========================================================================
# OTEL-SEC-1: Plaintext credential value absent from spans
# ===========================================================================

def test_plaintext_credential_value_absent_from_spans(redacting_provider, exporter):
    """
    A span whose attributes would carry plaintext credentials via known-risky
    attribute names (db.statement, credential_secret, mintkey.token) or via
    known credential-prefix values (sk_live_...) must be stripped.

    The two redaction mechanisms are:
      (a) Attribute NAME matches exact-match or suffix rules  → key+value dropped.
      (b) Attribute VALUE matches a credential-prefix pattern → key+value dropped.

    Simulates the scenarios closest to real leaks in the Mintkey stack:
      - FastAPI / SQLAlchemy might record db.statement with parameterized queries.
      - A service might record a Stripe sk_live_ key it just fetched from vault.
      - A service might accidentally set credential_secret with the raw value.
    """
    tracer = redacting_provider.get_tracer("test")

    # Use the real credential sentinel value to stand for a Stripe key shape.
    _sk_credential = f"sk_live_{_INJECTED_CREDENTIAL}"
    # The value "leakme-secret-12345" placed as the db.statement body.
    _db_stmt_with_secret = f"INSERT INTO credentials (value) VALUES ('{_INJECTED_CREDENTIAL}')"

    with tracer.start_as_current_span("register-credential") as span:
        # (a) Exact name: db.statement containing the plaintext value.
        span.set_attribute("db.statement", _db_stmt_with_secret)
        # (a) Suffix name: credential_secret contains the plaintext.
        span.set_attribute("credential_secret", _INJECTED_CREDENTIAL)
        # (b) Value pattern: sk_live_ prefix — caught by value-pattern rule.
        span.set_attribute("mintkey.fetched_value", _sk_credential)
        # Safe attr alongside — must survive.
        span.set_attribute("http.status_code", 201)

    spans = exporter.get_finished_spans()
    assert spans, "No spans exported"

    attrs = (spans[-1].attributes or {})
    string_values = [v for v in attrs.values() if isinstance(v, str)]
    attr_names = set(attrs.keys())

    # db.statement must be fully absent (exact-name rule).
    assert "db.statement" not in attr_names, (
        "Exact-match forbidden attribute 'db.statement' appeared in exported spans"
    )

    # credential_secret must be absent (suffix _secret rule).
    assert "credential_secret" not in attr_names, (
        "Suffix-match attribute 'credential_secret' appeared in exported spans"
    )

    # The sk_live_ value must be absent (value-pattern rule).
    matched_sk = [v for v in string_values if _sk_credential in v]
    assert not matched_sk, (
        f"sk_live_ credential {_sk_credential!r} found in exported span values: {attrs}"
    )

    # Safe attribute must survive.
    assert attrs.get("http.status_code") == 201, (
        "Safe attribute http.status_code was incorrectly stripped"
    )


# ===========================================================================
# OTEL-SEC-2: mk_agent_ / mk_svckey_ / Bearer absent from spans
# ===========================================================================

def test_mk_agent_key_absent_from_spans(redacting_provider, exporter):
    """A span attribute set to an mk_agent_ value must be stripped."""
    tracer = redacting_provider.get_tracer("test")

    with tracer.start_as_current_span("token-exchange") as span:
        span.set_attribute("mintkey.presented_key", _INJECTED_AGENT_KEY)
        span.set_attribute("http.request.header.authorization", _INJECTED_BEARER)

    spans = exporter.get_finished_spans()
    string_values = _all_string_attr_values(spans)

    for secret in (_INJECTED_AGENT_KEY, _INJECTED_BEARER):
        matched = [v for v in string_values if secret in v]
        assert not matched, (
            f"Secret {secret!r} found in exported span attribute values: {matched}"
        )


def test_mk_svckey_absent_from_spans(redacting_provider, exporter):
    """A span attribute set to a mk_svckey_ value must be stripped."""
    tracer = redacting_provider.get_tracer("test")

    with tracer.start_as_current_span("api-key-resolve") as span:
        span.set_attribute("mintkey.presented_key", _INJECTED_SVC_KEY)

    spans = exporter.get_finished_spans()
    string_values = _all_string_attr_values(spans)

    matched = [v for v in string_values if _INJECTED_SVC_KEY in v]
    assert not matched, (
        f"Service key {_INJECTED_SVC_KEY!r} found in exported span attribute values: {matched}"
    )


def test_bearer_token_in_authorization_attr_absent(redacting_provider, exporter):
    """
    http.request.header.authorization set with a Bearer <mk_agent_...> value
    must be stripped by the exact-name rule (independent of value pattern).
    """
    tracer = redacting_provider.get_tracer("test")

    with tracer.start_as_current_span("auth-check") as span:
        span.set_attribute("http.request.header.authorization", _INJECTED_BEARER)

    spans = exporter.get_finished_spans()
    attr_names = _all_attr_names(spans)
    string_values = _all_string_attr_values(spans)

    assert "http.request.header.authorization" not in attr_names, (
        "Exact-match forbidden attribute 'http.request.header.authorization' "
        "appeared in exported spans"
    )
    matched = [v for v in string_values if _INJECTED_BEARER in v]
    assert not matched, (
        f"Bearer secret {_INJECTED_BEARER!r} found in exported span values: {matched}"
    )


# ===========================================================================
# OTEL-SEC-3: Exact-match forbidden attribute names absent from spans
# ===========================================================================

@pytest.mark.parametrize("forbidden_attr,value", [
    ("http.request.header.authorization", "Bearer super-secret"),
    ("db.statement", "SELECT * FROM credentials WHERE value = 'sec'"),
    ("messaging.message.payload", '{"credential": "sk_live_abc"}'),
    ("mintkey.token", "eyJhbGciOiJFZERTQSJ9.payload.sig"),
])
def test_exact_match_forbidden_attrs_absent(redacting_provider, exporter, forbidden_attr, value):
    """Exact-match forbidden attribute names must not appear in exported spans."""
    tracer = redacting_provider.get_tracer("test")

    with tracer.start_as_current_span("exact-match-check") as span:
        span.set_attribute(forbidden_attr, value)
        span.set_attribute("http.status_code", 200)  # safe attr alongside

    spans = exporter.get_finished_spans()
    attr_names = _all_attr_names(spans)

    assert forbidden_attr not in attr_names, (
        f"Exact-match forbidden attribute {forbidden_attr!r} appeared in spans"
    )
    # Verify the safe attr was not collateral damage.
    assert "http.status_code" in attr_names, (
        "Safe attribute http.status_code was incorrectly stripped"
    )


# ===========================================================================
# OTEL-SEC-4: Safe attributes preserved (no over-redaction)
# ===========================================================================

def test_safe_attributes_preserved(redacting_provider, exporter):
    """Non-sensitive attributes must survive redaction unchanged."""
    tracer = redacting_provider.get_tracer("test")

    safe_attrs = {
        "http.method": "POST",
        "http.status_code": 201,
        "http.route": "/v1/tenants/{tenant_id}/services/{service_id}/credentials",
        "mintkey.tenant_id": "tenant_01HX_safe",
        "mintkey.agent_id": "agent_01HX_safe",
        "mintkey.service_id": "svc_01HX_safe",
    }

    with tracer.start_as_current_span("safe-attr-check") as span:
        for k, v in safe_attrs.items():
            span.set_attribute(k, v)

    spans = exporter.get_finished_spans()
    target = [s for s in spans if s.name == "safe-attr-check"]
    assert target, "Expected to find safe-attr-check span"

    attrs = target[0].attributes or {}
    for k, v in safe_attrs.items():
        assert attrs.get(k) == v, (
            f"Safe attribute {k!r} was incorrectly removed or changed. "
            f"Expected {v!r}, got {attrs.get(k)!r}"
        )


# ===========================================================================
# OTEL-SEC-5: Allowlisted _key_id / _key_version / _key_fingerprint not redacted
# ===========================================================================

def test_key_id_and_key_version_not_redacted(redacting_provider, exporter):
    """
    Attributes ending with _key_id, _key_version, _key_fingerprint do NOT
    end with any of the forbidden suffixes (_key, _token, etc.) and must
    pass through redaction unchanged.
    """
    tracer = redacting_provider.get_tracer("test")

    with tracer.start_as_current_span("allowlist-check") as span:
        span.set_attribute("mintkey.api_key_id", "apikey_01HX_safe_value")
        span.set_attribute("mintkey.key_version", 3)
        span.set_attribute("mintkey.key_fingerprint", "abc123def456")

    spans = exporter.get_finished_spans()
    target = [s for s in spans if s.name == "allowlist-check"]
    assert target, "Expected to find allowlist-check span"

    attrs = target[0].attributes or {}
    assert attrs.get("mintkey.api_key_id") == "apikey_01HX_safe_value", (
        "mintkey.api_key_id should NOT be redacted (ends with _id, not _key)"
    )
    assert attrs.get("mintkey.key_version") == 3, (
        "mintkey.key_version should NOT be redacted"
    )
    assert attrs.get("mintkey.key_fingerprint") == "abc123def456", (
        "mintkey.key_fingerprint should NOT be redacted"
    )


# ===========================================================================
# Combined scenario: mixed span with secrets and safe attrs
# ===========================================================================

def test_mixed_span_leaks_only_safe_attrs(redacting_provider, exporter):
    """
    A single span with a mix of sensitive and safe attributes must export
    only the safe subset.  All injected secrets must be absent.
    """
    tracer = redacting_provider.get_tracer("test")

    with tracer.start_as_current_span("mixed-span") as span:
        # Sensitive — should be stripped:
        span.set_attribute("http.request.header.authorization", _INJECTED_BEARER)
        span.set_attribute("mintkey.api_key", _INJECTED_SVC_KEY)       # ends with _key
        span.set_attribute("credential_secret", _INJECTED_CREDENTIAL)  # ends with _secret
        span.set_attribute("mintkey.access_token", _INJECTED_AGENT_KEY) # ends with _token

        # Safe — must survive:
        span.set_attribute("http.status_code", 200)
        span.set_attribute("mintkey.tenant_id", "t_safe_001")
        span.set_attribute("mintkey.api_key_id", "apikey_safe_id")

    spans = exporter.get_finished_spans()
    target = [s for s in spans if s.name == "mixed-span"]
    assert target, "Expected to find mixed-span"

    attrs = target[0].attributes or {}
    string_values = list(v for v in attrs.values() if isinstance(v, str))

    # All secrets absent.
    for secret in _ALL_INJECTED_SECRETS:
        matched = [v for v in string_values if secret in v]
        assert not matched, f"Secret {secret!r} found in exported attrs: {attrs}"

    # Safe attrs present.
    assert attrs.get("http.status_code") == 200
    assert attrs.get("mintkey.tenant_id") == "t_safe_001"
    assert attrs.get("mintkey.api_key_id") == "apikey_safe_id"
