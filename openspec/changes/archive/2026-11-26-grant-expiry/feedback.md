# Feedback — grant-expiry

<!-- l4:feedback v1
Ask for changes here while the unit's branch is open. The easy way is `l4 feedback add` (see `l4 feedback --help`).
An item is read only when its **Status** is `submitted`; `draft` items wait and `withdrawn` items are ignored.
Kinds: refactor · duplication · tests · config · behaviour (see docs/feedback.md).
Do not change item IDs. Commit and push to the l4/… branch: the harness takes submitted items at its next
verification round, turns them into a fix unit and checks that each one was addressed. -->

<!-- l4:feedback-index:start -->
| ID | Status | Kind | Where | Feedback |
|----|--------|------|-------|----------|
| FB-001 | addressed | refactor | apps/mcp-server/src/mcp_server/tools/discovery.py:420 | Restore the email grant queries of list_services and discover |
| FB-002 | addressed | refactor | apps/admin-api/src/admin_api/api/permissions.py:388 | Bind the grantor filter values as parameters |
<!-- l4:feedback-index:end -->

---

## FB-001: Restore the email grant queries of list_services and discover

- **Status:** addressed
- **Kind:** refactor
- **Where:** `apps/mcp-server/src/mcp_server/tools/discovery.py:420-440`
- **Where:** `apps/mcp-server/src/mcp_server/tools/discovery.py:516-536`
- **Lesson:** no
- **By:** CiprianSpot, 2026-11-26T21:31:15Z

### Code
`apps/mcp-server/src/mcp_server/tools/discovery.py:420-440`
```python
        for r in rows
    ]

    # Email services — union from email_permission_grants + email_services.
    # Email grants carry no expiry yet; the subquery exposes a null `expires_at`
    # so the same live-grant predicate applies to both discovery reads.
    email_result = await session.execute(
        text(
            "SELECT DISTINCT es.id, es.name, es.imap_host, es.smtp_host,"
            " es.auth_scheme, es.allowed_recipient_domains"
            " FROM email_services es"
            " JOIN ("
            "   SELECT eg.*, NULL::timestamptz AS expires_at"
            "   FROM email_permission_grants eg"
            " ) pg ON pg.email_service_id = es.id"
            " WHERE pg.agent_id = :agent_id AND es.deleted_at IS NULL"
            "   AND (pg.expires_at IS NULL OR pg.expires_at > now())"
        ),
        {"agent_id": agent_ctx["agent_id"]},
    )
    email_rows = email_result.fetchall()
```
`apps/mcp-server/src/mcp_server/tools/discovery.py:516-536`
```python
        for r in rows
    ]

    # Email services — union from email_permission_grants + email_services.
    # Email grants carry no expiry yet; the subquery exposes a null `expires_at`
    # so the same live-grant predicate applies to both discovery reads.
    email_result = await session.execute(
        text(
            "SELECT DISTINCT es.id, es.name, es.imap_host, es.smtp_host,"
            " es.auth_scheme, es.allowed_recipient_domains"
            " FROM email_services es"
            " JOIN ("
            "   SELECT eg.*, NULL::timestamptz AS expires_at"
            "   FROM email_permission_grants eg"
            " ) pg ON pg.email_service_id = es.id"
            " WHERE pg.agent_id = :agent_id AND es.deleted_at IS NULL"
            "   AND (pg.expires_at IS NULL OR pg.expires_at > now())"
        ),
        {"agent_id": agent_ctx["agent_id"]},
    )
    email_rows = email_result.fetchall()
```

### Feedback
Restore both email_permission_grants queries (list_services and discover) to their form on the base branch: JOIN email_permission_grants epg ON epg.email_service_id = es.id WHERE epg.agent_id = :agent_id AND es.deleted_at IS NULL, and drop the comment above each. The subquery that adds a null expires_at under the alias pg changes no result (email grants carry no expiry) and exists only for a test helper that matched the table name as a substring; that helper is fixed in the same push, so the tests read permission_grants as a whole word and pass with the base form. Behaviour is unchanged.

### Outcome
<!-- written by the harness -->
Addressed in round 4 at 4b47ca098d: apps/mcp-server/src/mcp_server/tools/discovery.py diff touches only the permission_grants statements; email_permission_grants queries are in base form, with whole-word test helper in test_grant_expiry_discovery.py.

---

## FB-002: Bind the grantor filter values as parameters

- **Status:** addressed
- **Kind:** refactor
- **Where:** `apps/admin-api/src/admin_api/api/permissions.py:388-402`
- **Lesson:** no
- **By:** CiprianSpot, 2026-11-26T22:09:08Z

### Code
```python
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
```

### Feedback
The grantor_agent_id filter of the permission listing compares grantor_type and grantor_id with literal_column(f"'...'") built from the value. Compare them with bound parameters instead: grantor_type with the constant GRANTOR_AGENT and grantor_id with the normalised uuid (uuid.UUID(grantor_uuid), so every accepted spelling of the id reaches the database as one canonical value). Behaviour is unchanged for every id the route accepts today; the statement no longer carries the value as SQL text.

### Outcome
<!-- written by the harness -->
Addressed in round 6 at 3ae84ca15d: apps/admin-api/src/admin_api/api/permissions.py: grantor_uuid = uuid.UUID(...); stmt.where(pg_table.c.grantor_type == GRANTOR_AGENT, pg_table.c.grantor_id == grantor_uuid) — no literal_column.
