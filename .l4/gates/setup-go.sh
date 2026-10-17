#!/bin/sh
# Setup gate (gates.setup in .l4/config.yaml): the modules of every go.work module, and the two Go tools the gates run,
# at the versions the repository's CI pins (golangci-lint as in ci.yml "Lint Go"). The tools go to .l4-out/bin (git
# ignores .l4-out/), and the gate scripts call them there: the gate PATH never holds the worktree.
set -e
R=$PWD
go mod download all
for d in $(go list -m -f '{{.Dir}}'); do (cd "$d" && go mod download); done
GOBIN="$R/.l4-out/bin" go install github.com/golangci/golangci-lint/cmd/golangci-lint@v1.64.8
GOBIN="$R/.l4-out/bin" go install gotest.tools/gotestsum@v1.13.0
