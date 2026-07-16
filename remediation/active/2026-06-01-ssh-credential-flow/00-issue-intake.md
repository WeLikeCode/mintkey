# Issue Intake — SSH credential flow remediation

Session: 2026-06-01-ssh-credential-flow
Repo: /Users/alexandruiacobescu/gooseProjects/mintkey
Orchestrator: Opus 4.7 (dispatches Sonnet IMPLEMENTERs + fresh Opus REVIEWERs)

## 1. Problem statement
The end-to-end credential flow for SSH services (and likely all 5 "special" auth
schemes: apple_jwt, google_service_account, ssh_private_key, ssh_ca, ssh_password,
oauth2_password_grant) is broken across UI, API, and data layers. Operators cannot
register a working credential via Admin UI. Owner has separately patched the
immediate routing issue via SQL, but the underlying bugs remain.

## 2. User-visible symptom
Registering an `ssh_password` credential via Admin UI → form filled correctly
(svc id, ssh_user=root, target=172.24.1.234:22, password) → submit returns
generic "validation error" with no detail. Admin-api logs show pydantic
complaining the inner JSON has empty `username`, `password`, `target_address`.

## 3. Expected behavior
Operator fills the Register Credential form for any of the 5 special schemes →
fields reach admin-api unchanged → credential lands with correct
`target_address`/`ssh_user`/etc. → ssh-proxy dials the right upstream with
the right user/credential. Field-level validation errors surface in the UI.

## 4. Evidence
- admin-api log (2026-06-01 17:05:17): `ssh_password credential validation
  failed: 3 validation errors for SSHPasswordPayload: username must be
  non-empty (input_value=''), string_too_short (password), target_address
  must be 'host:port' (input_value='')` → returns 400.
- Frontend code `apps/admin-ui/src/components/actions/CredentialNewForm.tsx:244-254`
  correctly builds `{auth_scheme, service_id, value: JSON.stringify({scheme:
  "ssh_password", username, password, target_address})}` from form fields.
- AdminJS handler `apps/admin-ui/src/resources/credentials.ts:79-115` calls
  `buildCredentialPayload(scheme, request.payload)` — but
  `buildCredentialPayload` (`apps/admin-ui/src/lib/auth-scheme.ts:146-203`)
  reads `formData.username`, `formData.target_address` as TOP-LEVEL fields,
  which the frontend nested inside `value`. Handler overwrites the frontend's
  correct `value` with one containing all empty strings, then POSTs to admin-api.
- ssh-proxy log: bastion dialed `target=ssh-target:2222 user=testuser` for
  `service_id=019e8353-...` even though `services.base_url='ssh://172.24.1.234:22'`.
  Proxy reads `vault.credentials.target_address`/`ssh_user`, never
  `services.base_url`. Two sources of truth that drift.
- `Show` page's "Rotate Credential" button does NOT carry forward
  `target_address`/`ssh_user` from prior `is_current` row — last invocation
  created `cred_XWBWSS5NW8E6T2CEYQED0KZKQG` with empty `target_address`/`ssh_user`
  (verified in DB). Already rolled back manually.
- `services.current_key_version` lags `vault.credentials.is_current` (UI shows
  v1 while DB has v2 current).
- `Register Credential` form's "Service ID" field is plain text — operator must
  paste raw `svc_01KT...` wire ID. Permissions resource already has a
  `ServiceCombobox` typeahead (`apps/admin-ui/src/resources/permissions.ts:88-90`).
- `CredentialNewForm.tsx:307-310` only surfaces `result.notice.message` — admin-api
  returns structured 400 with field-level details; the AdminJS handler at
  `credentials.ts:102-107` drops them (`err.title ?? "Failed to register credential"`).

## 5. Scope
- `apps/admin-ui/src/resources/credentials.ts`
- `apps/admin-ui/src/lib/auth-scheme.ts`
- `apps/admin-ui/src/components/actions/CredentialNewForm.tsx`
- `apps/admin-api/src/admin_api/api/credentials.py` (rotate carry-forward + structured errors)
- `apps/admin-api/src/admin_api/api/services.py` (Phase 2: base_url → target_address cascade)
- `apps/ssh-proxy/internal/backend/backend.go` + vault-adapter (Phase 3: base_url canonical)
- New ADR-0023 file under `docs/architecture/01-architecture/adr/`

## 6. Out of scope
- ssh-proxy session/JWT routing logic (works correctly)
- bastion's own SSH server / sshd config
- Liquibase migrations 020/021 (already applied)
- Canonical agent rows (Claudiu_1, Hermes_agent1, Hermes_2, Codex_1,
  spotus-test-agent) — DO NOT TOUCH. Use `scripts/with-test-agent.sh` for any
  e2e verification needing an `mk_agent_*` key.

## 7. Risk level
Medium-high. Touches credential write paths + bastion routing. Must not regress
the other auth schemes (bearer_token, basic_auth, oauth2_password_grant,
apple_jwt, google_service_account). Phase 3 includes a code-level read-source
change but NOT a column drop (safety net — column drop deferred to follow-up).

## 8. Verification target (DoD)
- AC-1: Register `ssh_password` credential for `svc_01KT1N7PPVENMQE6QHW51H3D1S`
  via Admin UI with valid `root@172.24.1.234:22` form data → admin-api returns 201,
  `vault.credentials` row has correct `key_version=N+1`, `is_current=true`,
  `target_address='172.24.1.234:22'`, `ssh_user='root'`.
- AC-2: Bastion-routed SSH from a throw-away test agent succeeds with the new JWT
  → ssh-proxy log shows `connecting to backend target=172.24.1.234:22 user=root` →
  handshake reaches the upstream (auth success OR a SPECIFIC backend reason, not
  "attempted methods [none password]" due to missing material).
- AC-3: "Rotate Credential" on the new credential's Show page → new row has
  `key_version=N+2`, `is_current=true`, AND `target_address`/`ssh_user` carried
  over from the predecessor (NOT empty).
- AC-4: Submit Register form with invalid input (blank password) → UI surfaces
  the SPECIFIC pydantic field error(s), not generic "validation error".
- AC-5: Register Credential form's Service ID renders the `ServiceCombobox`
  typeahead with the service name visible (not raw `svc_01K...`).
- AC-6: Edit `services.base_url` of `ssh-bastion-password` via Admin UI →
  cascade updates `vault.credentials.target_address` of the current credential
  in the same transaction (Phase 2). OR (Phase 3) ssh-proxy reads
  `services.base_url` directly; no DB drift possible.
- AC-7: All 8 auth schemes still register cleanly (bearer_token, basic_auth,
  oauth2_password_grant, apple_jwt, google_service_account, ssh_private_key,
  ssh_ca, ssh_password). Regression suite green:
  `apps/admin-api/.venv/bin/python -m pytest tests/unit/admin_api/ -x -q`.
- AC-8: ssh-proxy Go tests pass: `cd apps/ssh-proxy && go test ./... -short`.
- AC-9: `services.current_key_version` synced with `vault.credentials.is_current`
  after each register/rotate (no drift).

## 9. Owner decisions made
- Phase ordering: Phase 2 (defensive cascade) FIRST, then Phase 3 (base_url canonical).
  Do not skip Phase 2.
- Phase 3 includes new ADR-0023 ("SSH upstream addressing — base_url is canonical").
- No `Co-Authored-By: Claude` trailers in commits.
- New branch `fix/ssh-credential-flow` (not reusing `fix/ssh-proxy-integration`).
- "No half-baked solutions" — each chunk must pass DoD + reviewer before next chunk.

## Open decisions (to confirm with owner mid-flight)
- Phase 3 sub-option: (a) extend vault-adapter `GetCredential` to JOIN
  `services.base_url`, vs (b) ssh-proxy hits admin-api `/v1/services/{id}`.
  Intake leans (a). Confirm before C-7 dispatches.
- New branch base: `origin/main` vs current HEAD `fix/ssh-proxy-integration`
  (since PR #138 may not be merged yet on origin/main per `git log`).
