# Questions — agent-service-routes-fix-1

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
| Q-001 | open | 1.4 | ambiguous | Task 1.4 (red) left a clause of C-2a3254e4 unasserted: a display_name, description, base_url or openapi_url longer than the stored column allows |
<!-- l4:index:end -->

---

## Q-001: Task 1.4 (red) left a clause of C-2a3254e4 unasserted: a display_name, description, base_url or openapi_url longer than the stored column allows

- **Status:** open
- **Blocking tasks:** 1.4
- **Kind:** ambiguous
- **Asked:** 2026-11-28T00:31Z by deepseek, run r-20261127T2304Z-99a7, task 1.4
- **Criteria:** C-2a3254e4 (agent-service-credential › Invalid field values answer 422, never 500 or a silent 200 — feedback FB-004 › Invalid field values answer 422, never 500 or a silent 200)

### Context
The red step of task 1.4 did not assert this clause of C-2a3254e4, and listed it in `unasserted`:

> a display_name, description, base_url or openapi_url longer than the stored column allows

Its reason: description, base_url and openapi_url are TEXT columns (004-services.yaml) with no finite length, so no request can be longer than they allow and the requirement names no smaller maximum for them; only display_name is VARCHAR(256) and is tested.

The step was not kept. Answer with what the clause means for this task: the value or behaviour the code must have, or that it stays unasserted. The next step of the task reads the answer, and the judge checks the code against it.

### Answer
<!-- write below this line -->
