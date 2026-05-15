"""
SDK-level OTel span attribute redaction filter.

First of two redaction layers (SDK + Collector per ADR-0017.6).
Redacts attributes matching exact names, suffixes, or credential-value patterns
before they are exported to the Collector.

Source: ADR-0017.6; T-1.0.14.
"""
from __future__ import annotations

import re
from typing import Any

# Exact attribute names to always redact
EXACT_REDACT = frozenset({
    "http.request.header.authorization",
    "db.statement",
    "messaging.message.payload",
    "mintkey.token",
})

# Attribute name suffixes that trigger redaction
SUFFIX_REDACT = (
    "_token", "_secret", "_password", "_passphrase", "_key", "_hash",
)

# Value patterns that indicate a credential (checked on string values)
_CREDENTIAL_PATTERNS = [
    re.compile(r"^sk_"),
    re.compile(r"^pk_"),
    re.compile(r"^eyJ"),       # JWT shape
    re.compile(r"^mk_agent_"), # Mintkey agent API keys
    re.compile(r"^mk_svckey_"), # Mintkey service API keys
]


def _is_redacted_name(name: str) -> bool:
    if name in EXACT_REDACT:
        return True
    return any(name.endswith(suffix) for suffix in SUFFIX_REDACT)


def _is_redacted_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return any(p.match(value) for p in _CREDENTIAL_PATTERNS)


def redact_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of attrs with sensitive entries removed."""
    return {
        k: v for k, v in attrs.items()
        if not _is_redacted_name(k) and not _is_redacted_value(v)
    }


class RedactingSpanProcessor:
    """
    OpenTelemetry SpanProcessor that redacts sensitive attributes on export.

    Wraps another SpanProcessor and strips sensitive span attributes
    before passing the span to the downstream processor.

    Usage:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(
            RedactingSpanProcessor(SimpleSpanProcessor(exporter))
        )
    """

    def __init__(self, wrapped: Any) -> None:
        self._wrapped = wrapped

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        self._wrapped.on_start(span, parent_context)

    def _scrub_span(self, span: Any) -> None:
        """Mutate span._attributes in-place, removing any sensitive entries."""
        if hasattr(span, "_attributes") and span._attributes:
            keys_to_delete = [
                k for k, v in span._attributes.items()
                if _is_redacted_name(k) or _is_redacted_value(v if isinstance(v, str) else "")
            ]
            for k in keys_to_delete:
                del span._attributes[k]

    def _on_ending(self, span: Any) -> None:
        # Called by the real SDK's BatchSpanProcessor while the span is still
        # mutable (before it becomes a ReadOnlySpan).  Redact here for early
        # defence-in-depth, then forward to the wrapped processor.
        self._scrub_span(span)
        if hasattr(self._wrapped, "_on_ending"):
            self._wrapped._on_ending(span)

    def on_end(self, span: Any) -> None:
        # Public SpanProcessor interface — scrub any remaining sensitive attrs
        # (covers spans that never went through _on_ending, e.g. in tests with
        # mutable mock spans, or when a SimpleSpanProcessor is the delegate).
        self._scrub_span(span)
        self._wrapped.on_end(span)

    def shutdown(self) -> None:
        self._wrapped.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._wrapped.force_flush(timeout_millis)
