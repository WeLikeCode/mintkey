"""
Minimal SQLAlchemy Core Table definitions for defense-in-depth SQL refactors.

Only columns referenced in SELECT/WHERE/ORDER BY of the affected callers are
declared — enough for the query-builder to generate safe, parameterised SQL
without any string concatenation.

Source: SI-B refactor; ADR-0008; T-1.0.15.
"""
from __future__ import annotations

from sqlalchemy import Column, DateTime, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

permission_grants = Table(
    "permission_grants",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("agent_id", UUID(as_uuid=True), nullable=False),
    Column("service_id", UUID(as_uuid=True)),
    Column("action", String, nullable=False),
    Column("constraints", JSONB),
    Column("created_at", DateTime(timezone=True)),
    Column("created_by", UUID(as_uuid=True)),
)

services = Table(
    "services",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("name", String),
    Column("slug", String),
)

agents = Table(
    "agents",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tenant_id", UUID(as_uuid=True), nullable=False),
    Column("name", String),
)
