# Questions — proxy-revocation-enforced

<!-- l4:questions v1
How to answer: write under "### Answer" and set **Status** to `answered`.
To accept the clarifier's suggestion as-is, set **Status** to `accepted`.
Status values: open · answered · accepted · answered-by-clarifier · dismissed · superseded
Kind values: technical · product · ambiguous · verdict · harness. For a `verdict` question, start the answer with `accept` or
`reject`, then give your reason; for a `harness` question, with `accept` or `retry`.
Do not change question IDs. Commit and push to the l4/… branch to resume the run. -->

<!-- l4:index:start -->
| ID | Status | Blocking | Kind | Question |
|----|--------|----------|------|----------|
| Q-001 | answered | 1.1, 2.1, 3.1, 4.1 | ambiguous | No Go unit has been implemented in this repository through the test gate's red step before; D5 is w… |
| Q-002 | answered | 1.1, 2.1, 3.1, 4.1 | ambiguous | The SSH proxy acts on `agent.revoked` by `target_id`, which admin-api's payload does not carry, and… |
| Q-003 | open | 1.1, 2.1, 3.1, 4.1 | ambiguous | The vault adapter will now act on `credential.rotated` (`InvalidateByService(tenant_id, service_id)… |
| Q-004 | open | 1.1, 2.1, 3.1, 4.1 | ambiguous | A live check (revoke an agent in the admin UI, call the proxy within 2 s) needs the compose stack a… |
<!-- l4:index:end -->

---

## Q-001: No Go unit has been implemented in this repository through the test gate's red step before; D5 is w…

- **Status:** answered
- **Answered by:** the delegate (claude-fable-5-1 via claude-code)
- **Blocking tasks:** 1.1, 2.1, 3.1, 4.1
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
No Go unit has been implemented in this repository through the test gate's red step before; D5 is written for it.

Listed under "Open questions" in design.md.
Open-question-hash: af108a54f5975fa6

### Answer
<!-- write below this line -->
Proceed under D5 as written; nothing in it needs a decision. The premise of the open question is out of date at this unit's head: three Go units have already been implemented and merged through the test gate's red step with the same approach, and their designs and tests are in the repository. broker-service-token-required (D7), vault-service-identity-fast-check (Testing notes) and vault-method-scopes (D10), all archived under openspec/changes/archive/2026-10-26-*, each state that the red step runs the new tests against the base code with every non-Python production file put back, and each reaches the new methods through an interface the test file declares with a type assertion that calls t.Fatal when the method is missing, as top-level test functions without t.Run. The merged tests use exactly that pattern: apps/broker/internal/config/config_test.go asserts *config.Config to a serviceTokenChecker interface, apps/vault-adapter/internal/server/identities_test.go asserts *VaultService to a bootRegistrar interface, apps/vault-adapter/internal/server/method_scopes_test.go asserts *VaultServer to grpcServerBuilder, and apps/proxy-plugin/internal/vault/client_conn_test.go asserts the vault client to interface{ Close() error }. The gate runs every go.work module through gotestsum with one junit report per module, including proxy-plugin, so the four new Go test files are collected as D5 expects. For this unit, write the tests so they name only the existing symbols D5 lists (NewAgentRevocationSet, NewJTIRevocationSet, Add, Contains, Len, changes.NewSubscriber, HandleNotification, testHandler, buildTestJWTWithClaims, ServeHTTP, which exist in the proxy-plugin package today), reach RunEviction and changesSubscriber through test-declared interfaces with a t.Fatal type assertion, and never name wireid, ToUUID, Canonical or JTIRetention in a test: the wire-id behaviour is checked through AgentRevocationSet.Add and Contains, and the eviction scenario uses literal durations. Tasks 1.1, 2.1, 3.1 and 4.1 can start.
---

## Q-002: The SSH proxy acts on `agent.revoked` by `target_id`, which admin-api's payload does not carry, and…

- **Status:** answered
- **Answered by:** the delegate (claude-fable-5-1 via claude-code)
- **Blocking tasks:** 1.1, 2.1, 3.1, 4.1
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
The SSH proxy acts on `agent.revoked` by `target_id`, which admin-api's payload does not carry, and its change
client (`packages/go/changes.Client`, built with a nil connection) does not `LISTEN` yet ("T-1.2.2" in its comments).
The key fix here is necessary for it but not sufficient; it needs its own change.

Listed under "Open questions" in design.md.
Open-question-hash: 5e98db39c9b24795

### Answer
<!-- write below this line -->
The open question records a known gap, not a decision this unit has to make, and it does not block any of the four tasks. The repository confirms it as written: apps/ssh-proxy/internal/revocation/revocation.go decodes only event_type and target_id, acts on agent.revoked by target_id, and builds packages/go/changes.NewClient with a nil connection, while admin-api's revoke_agent and delete_agent publish agent_id and no target_id, and changes.Client.Start only runs the heartbeat loop and still carries the T-1.2.2 LISTEN comments. The proposal puts revocation in the SSH and email proxies out of scope for this change, the specification has no requirement for the SSH proxy, and the proposal's Impact lists no SSH proxy file. So proceed with tasks 1.1 to 4.1 exactly as the specification and design state: do not edit the SSH proxy, packages/go/changes or admin-api's revocation payload beyond adding event_type in notify_change. After this unit the SSH proxy will see event_type on admin-api's agent.revoked notifications once its client LISTENs, but it will still need its own change to read agent_id (or admin-api to carry target_id) and to open the LISTEN; that is a separate proposal, as design.md says.
---

## Q-003: The vault adapter will now act on `credential.rotated` (`InvalidateByService(tenant_id, service_id)…

- **Status:** open
- **Blocking tasks:** 1.1, 2.1, 3.1, 4.1
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
The vault adapter will now act on `credential.rotated` (`InvalidateByService(tenant_id, service_id)`); the payload's
`service_id` is the wire form the request used. Whether its cache is keyed by the same form is not verified here.

Listed under "Open questions" in design.md.
Open-question-hash: a00dcfed513bb5f9

### Answer
<!-- write below this line -->
---

## Q-004: A live check (revoke an agent in the admin UI, call the proxy within 2 s) needs the compose stack a…

- **Status:** open
- **Blocking tasks:** 1.1, 2.1, 3.1, 4.1
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
A live check (revoke an agent in the admin UI, call the proxy within 2 s) needs the compose stack and is a person's
check; the unit tests feed the subscriber the exact payloads admin-api publishes.

Listed under "Open questions" in design.md.
Open-question-hash: d461306d88581c88

### Answer
<!-- write below this line -->
