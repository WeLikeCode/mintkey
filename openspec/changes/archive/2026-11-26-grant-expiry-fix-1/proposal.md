# Proposal: fix 1 for grant-expiry

## Why
The verifier found problems in `grant-expiry` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-b5f87b40, F-7e9a81fb (blocker): test gate failed (+1 more): `sh .l4/gates/test.sh` failed: exit code 1; failing: apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_discover_filters_expired_grants, apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_list_services_filters_expired_grants | new tests failed: apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_discover_filters_expired_grants, apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_list_services_filters_expired_grants

      Failing tests as the verifier recorded them:
      apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_discover_filters_expired_grants (assertion, test):
        >           assert "pg.expires_at IS NULL OR pg.expires_at > now()" in statement
        E           AssertionError: assert 'pg.expires_at IS NULL OR pg.expires_at > now()' in 'SELECT DISTINCT es.id, es.name, es.imap_host, es.smtp_host, es.auth_scheme, es.allowed_recipient_domains FROM email_s...N email_permission_grants epg ON epg.email_service_id = es.id WHERE epg.agent_id = :agent_id AND es.deleted_at IS NULL'
        tests/test_grant_expiry_discovery.py:141: AssertionError
      apps.mcp-server.tests.test_grant_expiry_discovery::test_C_e07d9989_list_services_filters_expired_grants (assertion, test):
        >           assert "pg.expires_at IS NULL OR pg.expires_at > now()" in statement
        E           AssertionError: assert 'pg.expires_at IS NULL OR pg.expires_at > now()' in 'SELECT DISTINCT es.id, es.name, es.imap_host, es.smtp_host, es.auth_scheme, es.allowed_recipient_domains FROM email_s...N email_permission_grants epg ON epg.email_service_id = es.id WHERE epg.agent_id = :agent_id AND es.deleted_at IS NULL'
        tests/test_grant_expiry_discovery.py:121: AssertionError

## Impact
The code and the tests of `grant-expiry`.
