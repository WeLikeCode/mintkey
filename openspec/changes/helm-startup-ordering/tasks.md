# Tasks — helm-startup-ordering

- [ ] 1. Change `templates/jobs/seed-job.yaml` hook from `pre-install,pre-upgrade` to `post-install,post-upgrade` (weight/delete-policy unchanged).
- [ ] 2. `helm lint` + `helm template` confirm: seed-job renders as a post-install hook; Keycloak renders as a main StatefulSet (no hook).
- [ ] 3. Live smoke: `helm install` WITHOUT `--wait`/`--atomic` → liquibase (pre-install) completes → Keycloak + apps deploy → post-install seed-job reaches Keycloak and Completes → admin-api/admin-ui self-heal after seeding.
- [ ] 4. `openspec validate helm-startup-ordering --strict` passes.
