# Questions — proxy-grant-revocation

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
| Q-001 | open | 1.1 | technical | grant_revocation_test.go:227 names the first pair again as the third pair |
<!-- l4:index:end -->

---

## Q-001: grant_revocation_test.go:227 names the first pair again as the third pair

- **Status:** open
- **Escalated by:** the delegate (claude-fable-5-1 via claude-code): the answer would unfreeze apps/proxy-plugin/cmd/proxy-plugin/grant_revocation_test.go of task 1.1 (delegate.unfreeze is false)
- **Blocking tasks:** 1.1
- **Kind:** technical
- **Asked:** 2026-11-26T23:42Z by deepseek, run r-20261126T2258Z-5ab7, task 1.1

### Context
The test expects Len()==2 at line 251 after the third Add, but `thirdPairAgent := grantAgentUUID` and `thirdPairSvc := grantServiceUUID` (lines 227-228) canonicalise to the same (agent=6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd, service=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa) pair as the first Add at lines 230-231 (agent_3C7JAGMBGR9EMRS2AVGXDHQXDX / svc_5ANANANANANANANANANANANANA). The scenario says 'a third pair with revokedAt now' and the delta spec says 'every call removes the entries that have expired' and 'A later revokedAt replaces an earlier one'; together those leave only the first/third (same) entry after the second pair expires, so Len() is 1, not 2. The only way to reach 2 as written is for Add not to delete expired entries, contradicting the spec's 'every call removes the entries that have expired' (design D4). All other new tests pass; the gate's only failure is this line.

Harness note: the red tests and test-support files of this task are frozen. To let the next green change `apps/proxy-plugin/cmd/proxy-plugin/grant_revocation_test.go`, set **Status** to `accepted` or `answered` to take option 1, which names the file, or write an answer that names its path or run `l4 questions accept Q-NNN --unit proxy-grant-revocation`, then commit and push. An ignore file is never unfrozen by an answer, whatever it says. An answer that does not name the file leaves it frozen, and an answer edited after a run has used it counts as an override and unfreezes nothing.

### Options
1. Edit `apps/proxy-plugin/cmd/proxy-plugin/grant_revocation_test.go`: change line 227 `thirdPairAgent := grantAgentUUID` to `thirdPairAgent := "cccccccc-cccc-cccc-cccc-cccccccccccc"` so the third Add names a distinct pair.
2. Keep the test as written; implement Add without deleting expired entries (Refuses still ignores them), accepting that the delta spec's 'every call removes the entries that have expired' is not met.

### Clarifier suggestion
Edit `apps/proxy-plugin/cmd/proxy-plugin/grant_revocation_test.go`: change line 227 `thirdPairAgent := grantAgentUUID` to `thirdPairAgent := "cccccccc-cccc-cccc-cccc-cccccccccccc"` so the third Add names a distinct pair.

### Answer
<!-- write below this line -->
