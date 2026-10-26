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
| Q-001 | open | 1.1, 2.1, 3.1, 4.1 | ambiguous | No Go unit has been implemented in this repository through the test gate's red step before; D5 is w… |
| Q-002 | open | 1.1, 2.1, 3.1, 4.1 | ambiguous | The SSH proxy acts on `agent.revoked` by `target_id`, which admin-api's payload does not carry, and… |
| Q-003 | open | 1.1, 2.1, 3.1, 4.1 | ambiguous | The vault adapter will now act on `credential.rotated` (`InvalidateByService(tenant_id, service_id)… |
| Q-004 | open | 1.1, 2.1, 3.1, 4.1 | ambiguous | A live check (revoke an agent in the admin UI, call the proxy within 2 s) needs the compose stack a… |
<!-- l4:index:end -->

---

## Q-001: No Go unit has been implemented in this repository through the test gate's red step before; D5 is w…

- **Status:** open
- **Blocking tasks:** 1.1, 2.1, 3.1, 4.1
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
No Go unit has been implemented in this repository through the test gate's red step before; D5 is written for it.

Listed under "Open questions" in design.md.
Open-question-hash: af108a54f5975fa6

### Answer
<!-- write below this line -->
---

## Q-002: The SSH proxy acts on `agent.revoked` by `target_id`, which admin-api's payload does not carry, and…

- **Status:** open
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
