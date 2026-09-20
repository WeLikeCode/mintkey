"""
Pydantic v2 request/response models for the agent-access-requests feature.

These mirror the OpenAPI schemas (canonical contract:
docs/architecture/contracts/rest/openapi.yaml) for the five access-request
endpoints:

  GET    /v1/tenants/{tenant_id}/access-requests
  GET    /v1/tenants/{tenant_id}/access-requests/{request_id}
  POST   /v1/tenants/{tenant_id}/access-requests/{request_id}/approve
  POST   /v1/tenants/{tenant_id}/access-requests/{request_id}/reject
  POST   /v1/tenants/{tenant_id}/access-requests/{request_id}/test

Response IDs are ULID-prefixed wire strings (ADR-0017.11); the router
translates the UUID columns of the AccessRequest mapped model to wire form.
Secret material (`credential`) is `x-mintkey-sensitive`: it is forwarded only
to the Vault Adapter and never persisted on the request row, logged, placed in
an audit payload, or set as an OTel span attribute (P-1, S-SEC-1, ADR-0017.6).

Source: T-2.2; design §Wire Contracts; Req 12.6, 13.4;
        OpenAPI schemas AccessRequest / AccessRequestApprove /
        AccessRequestReject / AccessRequestConnectionTest / TestRunResponse.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Wire-form ID patterns (ADR-0017.11) — Crockford base32, 26 chars.
_REQUEST_ID_PATTERN = r"^request_[0-9A-HJKMNP-TV-Z]{26}$"
_AGENT_ID_PATTERN = r"^agent_[0-9A-HJKMNP-TV-Z]{26}$"

AccessRequestKind = Literal["access", "integration", "share"]
AccessRequestStatus = Literal["pending", "approved", "rejected", "expired", "cancelled"]
AccessRequestShareDirection = Literal["outbound", "inbound"]


class AccessRequest(BaseModel):
    """
    Wire response model — mirrors OpenAPI `AccessRequest`.

    One shape covers all three kinds; kind-specific fields are null when not
    applicable. `proposed_config` holds only non-secret fields (P-1).
    """

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=_REQUEST_ID_PATTERN)
    kind: AccessRequestKind
    status: AccessRequestStatus
    requesting_agent_id: str = Field(pattern=_AGENT_ID_PATTERN)
    service_id: Optional[str] = None
    action: Optional[str] = None
    target_agent_id: Optional[str] = None
    share_direction: Optional[AccessRequestShareDirection] = None
    proposed_config: Optional[dict[str, Any]] = None
    reason: Optional[str] = None
    created_at: datetime
    expires_at: datetime
    resolved_at: Optional[datetime] = None


class AccessRequestApprove(BaseModel):
    """
    Approve/finalize body — mirrors OpenAPI `AccessRequestApprove`.

    For `access`/`share` the body may be omitted (all properties optional).
    For an `integration` finalize it carries the operator secret material
    (`credential`, x-mintkey-sensitive) and any edited non-secret `config`.
    """

    model_config = ConfigDict(extra="forbid")

    # x-mintkey-sensitive — never persisted on the row, logged, audited, or spanned.
    credential: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None


class AccessRequestReject(BaseModel):
    """
    Reject body — mirrors OpenAPI `AccessRequestReject`.

    A mandatory, non-empty, non-whitespace-only reason (<= 1000 chars). A
    missing/blank/over-long reason is rejected with `mintkey:code`
    `reason_required`.
    """

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_non_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must be non-empty and non-whitespace-only")
        return v


class AccessRequestConnectionTest(BaseModel):
    """
    Connection_Test body — mirrors OpenAPI `AccessRequestConnectionTest`.

    Carries the operator secret (`credential`, x-mintkey-sensitive) and the
    (possibly edited) non-secret `config` to run an upstream handshake without
    persisting anything. The returned diagnostic contains no secret material.
    """

    model_config = ConfigDict(extra="forbid")

    # x-mintkey-sensitive — used in-memory for the test only.
    credential: Optional[dict[str, Any]] = None
    config: Optional[dict[str, Any]] = None


class TestRunResponse(BaseModel):
    """
    Connection_Test result — mirrors OpenAPI `TestRunResponse`.

    A timeout is reported as `ok: false` with a timeout diagnostic, never an
    error status. The diagnostic contains no secret material (Req 6.3).
    """

    model_config = ConfigDict(extra="forbid")

    ok: bool
    latency_ms: int = Field(ge=0)
    status_code: Optional[int] = Field(default=None, ge=0, le=599)
    response_body_truncated: Optional[str] = None
    error: Optional[str] = None
