# Proposal: fix 2 for proxy-stored-target

## Why
The verifier found problems in `proxy-stored-target` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-b0296656 (major): existing tests are skipped in a changed test file: tests.acceptance.test_classical_key::test_classical_key_full_flow, tests.acceptance.test_data_plane_smoke::test_broker_smoke, tests.acceptance.test_data_plane_smoke::test_kong_smoke, tests.acceptance.test_data_plane_smoke::test_proxy_plugin_smoke, tests.acceptance.test_data_plane_smoke::test_vault_adapter_smoke and 3 more

## Impact
The code and the tests of `proxy-stored-target`.
