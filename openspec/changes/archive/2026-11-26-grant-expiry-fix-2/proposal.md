# Proposal: fix 2 for grant-expiry

## Why
Requested by CiprianSpot, 2026-11-26T21:31:15Z in FB-001 (refactor, apps/mcp-server/src/mcp_server/tools/discovery.py:420-440, apps/mcp-server/src/mcp_server/tools/discovery.py:516-536): Restore both email_permission_grants queries (list_services and discover) to their form on the base branch: JOIN email_permission_grants epg ON epg.email_service_id = es.id WHERE epg.agent_id = :agent_id AND es.deleted_at IS NULL, and drop the comment above each. The subquery that adds a null expires_at under the alias pg changes no result (email grants carry no expiry) and exists only for a test helper that matched the table name as a substring; that helper is fixed in the same push, so the tests read permission_grants as a whole word and pass with the base form. Behaviour is unchanged.

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

The verifier found problems in `grant-expiry` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-3324c8f4 (major): Feedback FB-001 (refactor): Restore the email grant queries of list_services and discover

## Impact
The code and the tests of `grant-expiry`.
