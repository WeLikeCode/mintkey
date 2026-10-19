#!/bin/sh
# Setup gate (gates.setup in .l4/config.yaml): the modules of every go.work module, and the two Go tools the gates run,
# at the versions the repository's CI pins (golangci-lint as in ci.yml "Lint Go"). The tools go to .l4-out/bin (git
# ignores .l4-out/), and the gate scripts call them there: the gate PATH never holds the worktree.
#
# Every L4 unit worktree runs this gate first, and only this gate has the network, so it downloads every module the
# later gates build and test, and it leaves no tracked file changed (`git status --porcelain` empty): in workspace
# mode Go writes the checksums it adds to the go.work.sum beside the go.work it uses, and in module mode
# (GOWORK=off) to the module's go.sum. The download therefore goes through a copy of go.work outside the worktree,
# which starts from the repository's go.work.sum and keeps whatever it adds to itself.
set -e
R=$PWD
# Go keeps the checksum-database cache under GOPATH/pkg/sumdb, and the gate sandbox mounts the runner's GOPATH
# read-only: the module cache stays where it is (GOMODCACHE, which L4 makes writable for this gate), and GOPATH
# moves to a writable folder of the worktree (.l4-out is ignored), so `go mod download` and `go install pkg@version`
# can verify new modules against sum.golang.org.
GOMODCACHE="$(go env GOMODCACHE)"; export GOMODCACHE
export GOPATH="$R/.l4-out/gopath"
W=$(mktemp -d)
trap 'rm -rf "$W"' EXIT
{ awk '/^go /{print; exit}' go.work; echo "use ("; go list -m -f '	{{.Dir}}'; echo ")"; } > "$W/go.work"
cp go.work.sum "$W/go.work.sum"
GOWORK="$W/go.work" go mod download all
GOBIN="$R/.l4-out/bin" go install github.com/golangci/golangci-lint/cmd/golangci-lint@v1.64.8
GOBIN="$R/.l4-out/bin" go install gotest.tools/gotestsum@v1.13.0
