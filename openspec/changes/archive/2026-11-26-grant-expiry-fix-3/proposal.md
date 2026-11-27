# Proposal: fix 3 for grant-expiry

## Why
Requested by CiprianSpot, 2026-11-26T22:09:08Z in FB-002 (refactor, apps/admin-api/src/admin_api/api/permissions.py:388-402): The grantor_agent_id filter of the permission listing compares grantor_type and grantor_id with literal_column(f"'...'") built from the value. Compare them with bound parameters instead: grantor_type with the constant GRANTOR_AGENT and grantor_id with the normalised uuid (uuid.UUID(grantor_uuid), so every accepted spelling of the id reaches the database as one canonical value). Behaviour is unchanged for every id the route accepts today; the statement no longer carries the value as SQL text.

        if grantor_agent_id is not None:
            try:
                grantor_uuid = _decode_agent_wire_id(grantor_agent_id, "agent_")
                uuid.UUID(grantor_uuid)
            except (ValueError, AttributeError, TypeError):
                return JSONResponse(
                    status_code=422,
                    content={"mintkey:code": "invalid_id", "title": "Invalid agent_id"},
                )
            # The validated UUID is safe to render: the grantor filter is a
            # constant comparison, and the grant list keeps one statement shape.
            stmt = stmt.where(
                pg_table.c.grantor_type == literal_column(f"'{GRANTOR_AGENT}'"),
                pg_table.c.grantor_id == literal_column(f"'{grantor_uuid}'"),
            )

The verifier found problems in `grant-expiry` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-cf97605d (major): Feedback FB-002 (refactor): Bind the grantor filter values as parameters

## Impact
The code and the tests of `grant-expiry`.
