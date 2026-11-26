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
| FB-001 | taken | refactor | apps/mcp-server/src/mcp_server/tools/discovery.py:420 | Restore the email grant queries of list_services and discover |
<!-- l4:feedback-index:end -->

---

## FB-001: Restore the email grant queries of list_services and discover

- **Status:** taken
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
Taken in round 3 into grant-expiry-fix-2
