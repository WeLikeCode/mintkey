#!/bin/sh
# Lint gate (gates.lint): ci.yml "Lint Go", go vet and golangci-lint in every go.work module (`go list -m` lists them
# in workspace mode, as `go work edit -json` does in ci.yml).
R=$PWD
# golangci-lint keeps its own cache under the user cache folder, which the gate sandbox mounts read-only: keep it in
# the worktree's ignored .l4-out (as the setup gate does for GOPATH).
GOLANGCI_LINT_CACHE="$R/.l4-out/golangci-lint-cache"; export GOLANGCI_LINT_CACHE
status=0
for d in $(go list -m -f '{{.Dir}}'); do
  (cd "$d" && go vet ./...) || status=1
  (cd "$d" && "$R/.l4-out/bin/golangci-lint" run --timeout=5m ./...) || status=1
done
exit $status
