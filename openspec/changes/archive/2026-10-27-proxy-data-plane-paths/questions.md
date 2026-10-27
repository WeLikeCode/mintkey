# Questions — proxy-data-plane-paths

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
| Q-001 | answered | 1.1, 2.1, 3.1, 4.1 | ambiguous | If `service-token-files` lands after this change, its `*_FILE` variables should be added to the pag… |
<!-- l4:index:end -->

---

## Q-001: If `service-token-files` lands after this change, its `*_FILE` variables should be added to the pag…

- **Status:** answered
- **Answered by:** the delegate (claude-fable-5-1 via claude-code)
- **Blocking tasks:** 1.1, 2.1, 3.1, 4.1
- **Kind:** ambiguous
- **Asked:** intake (open questions in design.md)

### Context
If `service-token-files` lands after this change, its `*_FILE` variables should be added to the page's section 2.

Listed under "Open questions" in design.md.
Open-question-hash: 5fa33d145a0f9c79

### Answer
<!-- write below this line -->
The service-token-files change has not landed. It is still an unarchived proposal under openspec/changes/service-token-files, no code reads any token from a NAME_FILE variable (the proxy config loader still takes MINTKEY_PROXY_SERVICE_TOKEN and MINTKEY_VAULT_PROXY_TOKEN straight from the environment with getEnv, and packages/go/svcid has no FromEnv function), and the only mention of those variables in the repository is that change's own spec. So this unit documents only the variables design.md lists for section 2 (MINTKEY_VAULT_KEK_FILE and MINTKEY_BROKER_SIGNING_KEY_FILE, which exist today, plus the identity ids and token variables as named) and does not add the token *_FILE variables, since the page would then describe behaviour the shipped code does not have. The open question is a note for whoever lands service-token-files later: that change should then extend section 2 of docs/guides/data-plane-only.md. It does not block tasks 1.1, 2.1, 3.1 or 4.1; implement them as the design states.
