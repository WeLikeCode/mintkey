"""
OTel middleware setup.

Instruments FastAPI with opentelemetry-instrumentation-fastapi.
SDK-level redaction is wired in configure_otel() per ADR-0017.6.

Source: design §4 middleware/otel.py; ADR-0017.6; T-1.0.14; T-1.3.3.
"""
from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from mintkey_models.otel_redaction import RedactingSpanProcessor


def configure_otel(app: FastAPI, service_name: str = "admin-api") -> None:
    """Wire OTel SDK + FastAPI instrumentation with redaction layer per ADR-0017.6."""
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        RedactingSpanProcessor(BatchSpanProcessor(ConsoleSpanExporter()))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
