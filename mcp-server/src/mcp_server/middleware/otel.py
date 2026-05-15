"""
OTel middleware setup for mcp-server.

Instruments FastAPI with opentelemetry-instrumentation-fastapi and exports
spans via OTLP gRPC to the OTel Collector. SDK-level redaction is wired via
RedactingSpanProcessor per ADR-0017.6.

Source: ADR-0017.6; OPS-L.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


def configure_otel(app: "FastAPI", service_name: str = "mcp-server") -> None:
    """Wire OTel SDK + FastAPI instrumentation with OTLP export and redaction layer per ADR-0017.6."""
    # Lazy imports keep the module importable in test environments where the
    # optional OTel gRPC exporter package is not installed on the host.
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from mintkey_models.otel_redaction import RedactingSpanProcessor

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector:4317")
    processor = RedactingSpanProcessor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
