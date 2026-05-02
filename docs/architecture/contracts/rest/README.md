# Admin REST API contracts — *iteration 4 placeholder*

This directory will contain the **OpenAPI 3.1** specification for the Admin REST API. Endpoints are catalogued in [`../README.md`](../README.md).

## Coming in iteration 4
- `openapi.yaml` (root document).
- Schema components per resource (`Service`, `Credential`, `Agent`, `Permission`, `AuditEvent`, …).
- Per‑endpoint examples (request + response).
- Error envelope (`Problem Details for HTTP APIs`, RFC 7807).
- Authentication: `BearerAuth` (operator session / API token).

## Conventions (preview)
- Resource collections are paginated using cursor pagination (`?after=…&limit=…`).
- All timestamps are RFC 3339, UTC.
- IDs are ULIDs (`agent_01HX…`, `svc_…`, `cred_…`, `perm_…`).
- The Agent API Key is returned **once** at agent creation and never again — the create response is the only place the plaintext appears.
