# CI Go Coverage

## ADDED Requirements

### Requirement: CI vets, lints, and unit-tests every workspace Go module
The `ci.yml` `lint-go` and `test-go-unit` jobs SHALL run `go vet`, golangci-lint, and `go test -short` against every module listed in `go.work` (not only the repo-root module), and SHALL fail if any module produces a vet error, a golangci-lint finding, or a test failure.

#### Scenario: A proxy-plugin vet/lint regression fails CI
- **WHEN** a change introduces a `go vet` or golangci-lint finding in `apps/proxy-plugin` (or any app module)
- **THEN** the `lint-go` job exits non-zero and CI is red (previously it stayed green because root `./...` never covered the app modules)

#### Scenario: New workspace modules are covered automatically
- **WHEN** a new module is added to `go.work`
- **THEN** the lint-go and test-go-unit jobs include it without editing a hard-coded module list

### Requirement: The app Go modules are vet- and lint-clean
Every module in `go.work` SHALL pass `go vet ./...` and golangci-lint (v1.64.8 defaults) with zero findings, and `go test ./... -short` SHALL pass.

#### Scenario: Metrics WriteTo no longer trips stdmethods
- **WHEN** `go vet ./...` runs in `apps/broker` and `apps/proxy-plugin`
- **THEN** it reports no `WriteTo ... should have signature ...` finding, and the `/metrics` output is byte-identical to before the rename
