"""
OTel middleware setup.

Instruments FastAPI with opentelemetry-instrumentation-fastapi.
SDK-level redaction is wired in configure_otel() per ADR-0017.6.

Source: design §4 middleware/otel.py; ADR-0017.6; T-1.0.14; T-1.3.3.
"""
from __future__ import annotations

import os

import opentelemetry.instrumentation.fastapi as _otel_fastapi
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from starlette.routing import Match, Route

from mintkey_models.otel_redaction import RedactingSpanProcessor


def _safe_get_route_details(scope: dict) -> str | None:
    """Replacement for OTel's _get_route_details that handles _IncludedRouter.

    The upstream Match.PARTIAL branch lacks the try/except AttributeError guard
    present in the Match.FULL branch, crashing when FastAPI's include_router()
    produces _IncludedRouter objects which have no .path attribute.
    """
    _app = scope["app"]
    route = None
    for starlette_route in _app.routes:
        match, _ = (
            Route.matches(starlette_route, scope)
            if isinstance(starlette_route, Route)
            else starlette_route.matches(scope)
        )
        if match == Match.FULL:
            try:
                route = starlette_route.path
            except AttributeError:
                route = scope.get("path")
            break
        if match == Match.PARTIAL:
            try:
                route = starlette_route.path
            except AttributeError:
                route = scope.get("path")
    return route


def configure_otel(app: FastAPI, service_name: str = "admin-api") -> None:
    """Wire OTel SDK + FastAPI instrumentation with redaction layer per ADR-0017.6."""
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector:4317")
    provider.add_span_processor(
        RedactingSpanProcessor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    )
    trace.set_tracer_provider(provider)

    # Monkey-patch _get_route_details before instrumenting so _IncludedRouter
    # objects (from include_router) don't crash span creation on PARTIAL match.
    _otel_fastapi._get_route_details = _safe_get_route_details

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
