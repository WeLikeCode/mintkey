#!/bin/sh
# Lint gate (gates.lint): ci.yml "Lint Go", go vet and golangci-lint in every go.work module (`go list -m` lists them
# in workspace mode, as `go work edit -json` does in ci.yml).
R=$PWD
status=0
for d in $(go list -m -f '{{.Dir}}'); do
  (cd "$d" && go vet ./...) || status=1
  (cd "$d" && "$R/.l4-out/bin/golangci-lint" run --timeout=5m ./...) || status=1
done
exit $status
