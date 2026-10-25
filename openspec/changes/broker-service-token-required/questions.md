# Questions — broker-service-token-required

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
| Q-001 | answered | 1.1, 2.1, 3.1 | ambiguous | D4 picks the proxy and admin identities as the ones production requires. An owner may prefer a conf… |
<!-- l4:index:end -->

---

## Q-001: D4 picks the proxy and admin identities as the ones production requires. An owner may prefer a conf…

- **Status:** answered
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): Which vault identities production must have is a deployment-policy decision the repository does not make. deploy/helm/mintkey/README.md:24 says every secret key is required unless noted optional and notes none of the five vault tokens optional; the chart (templates/stateful/vault-adapter.yaml:61-105
- **Blocking tasks:** 1.1, 2.1, 3.1
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
D4 picks the proxy and admin identities as the ones production requires. An owner may prefer a configurable list
(for a stack that runs the SSH proxy as its main component). Recorded here as a decision taken unattended.

Listed under "Open questions" in design.md.
Open-question-hash: d273702d4bb108ec

### Answer
<!-- write below this line -->
The owner's delegate (2026-10-25): keep D4 as designed. With MINTKEY_ENV=production the vault adapter refuses to start without the proxy and the admin identity tokens; the SSH-proxy, email-proxy and MCP identities stay optional, because a stack may not run those components, and an identity whose token is set is registered exactly as before. No configurable list in this change. The Helm chart's own rule (every secret key required unless noted optional) is a deployment check and is not changed here.
