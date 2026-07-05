# Tasks — Tailscale Service Template

## 1. Catalog entry

- [ ] 1.1 Append the `tailscale` template entry (see design.md "The exact YAML
  entry to add") to `apps/admin-api/src/admin_api/templates/service_templates.yaml`
  under the `# ── HTTP service templates` section. Fields: `template_id:
  tailscale`, `base_url: https://api.tailscale.com`, `auth_type: bearer_token`,
  `openapi_spec_url: https://tailscale.com/api`, `category: networking`,
  `version: "1.0.0"`, `credential_hint` (field/help/format documenting the
  `tskey-api-...` / `tskey-client-...` prefixes), `test_path:
  /api/v2/tailnet/-/devices`.
- [ ] 1.2 Verify the YAML parses: `python3 -c "import yaml;
  yaml.safe_load(open('apps/admin-api/src/admin_api/templates/service_templates.yaml'))"`
  (exit 0).
- [ ] 1.3 Verify the entry validates against the `ServiceTemplate` model at
  import time: `python3 -c "from admin_api.templates.registry import registry;
  t = registry.get('tailscale'); assert t and t.auth_type == 'bearer_token' and
  t.base_url == 'https://api.tailscale.com'; print('ok')"` (run from the
  admin-api package env; no `template_registry.malformed_entry` warning in logs).

## 2. Test

- [ ] 2.1 Add a case to the existing template-registry unit test asserting the
  `tailscale` template: loads (`registry.get("tailscale")` is not None),
  `auth_type == "bearer_token"`, `base_url == "https://api.tailscale.com"`,
  `category == "networking"`, `test_path == "/api/v2/tailnet/-/devices"`, and
  `credential_hint.field == "token"`.
- [ ] 2.2 Run the admin-api unit suite covering templates and capture exit code:
  `cd apps/admin-api && uv run pytest tests/unit/admin_api/ -k template -q`
  (green, exit 0).

## 3. Docs

- [ ] 3.1 Add one line to the service-template catalog list in `docs/HOW-TO.md`:
  Tailscale — networking — `bearer_token` (`tskey-api-...` access token); note
  the token-expiry rotation caveat and the deferred OAuth2 alternative.

## 4. Verification

- [ ] 4.1 (Optional, live) Instantiate the template on a dev stack
  (`POST /v1/tenants/{tid}/services/from-template` with `template_id=tailscale`),
  supply a real `tskey-api-...` token, and confirm the credential-validation
  call to `test_path` returns 200 (`Via: kong/...` header confirms it went
  through the proxy).
- [ ] 4.2 Re-read the diff: only `service_templates.yaml`, the template test,
  and `docs/HOW-TO.md` change. No `models.py`/`registry.py`/OpenAPI/`vault.proto`/
  Liquibase/proxy edits (Surgical Changes check).
