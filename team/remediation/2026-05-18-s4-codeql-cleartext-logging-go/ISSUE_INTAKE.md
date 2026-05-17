# Issue Intake — S4 codeql-cleartext-logging-go

## Problem statement

Four high-severity CodeQL `go/clear-text-logging` alerts in `services/proxy-plugin/cmd/proxy-plugin/main.go`. JWT-derived claim values (`serviceID`, `tenantID`) and request-header-derived values flow from tainted sources directly into `log.Printf` calls without redaction, creating a data-flow path from potentially sensitive user-controlled input to the log sink (CWE-312).

## User-visible symptom

GitHub Advanced Security reports 4 high alerts on the `go/clear-text-logging` rule; CI code-scanning gate blocks merge.

## Expected behavior

All log lines should carry only structured identifiers (UUID-shaped values) or static strings. Any value that does not conform to the expected UUID shape should be replaced with `[redacted]` before reaching the log sink. Inject errors (which provably don't carry credential values) should flow through a named sanitizing wrapper to break the CodeQL data-flow path.

## Evidence

- `main.go:272` — `log.Printf` with `urlSvcID` (from `r.URL.Path`) and `serviceID` (from JWT `aud` claim)
- `main.go:310` — `log.Printf` with `serviceID` / `tenantID` (from JWT claims) on vault error
- `main.go:462` — `log.Printf` with `serviceID` / `tenantID` (from `X-Mintkey-*` headers) on vault error
- `main.go:506` — `log.Printf` with `injectErr` return value tainted by `backendCred.Value` (credential plaintext) dataflow

## Scope

- `services/proxy-plugin/cmd/proxy-plugin/main.go`
- `services/proxy-plugin/cmd/proxy-plugin/proxy_test.go`

## Out of scope

All other Go services, admin-api, admin-ui.

## Risk level

Security / compliance.

## Verification target

```
cd /Users/alexandruiacobescu/gooseProjects/mintkey-s4-codeql-cleartext-logging-go/services/proxy-plugin
go vet ./cmd/proxy-plugin/...
go test -race ./... -timeout 60s
gofmt -l ./cmd/proxy-plugin/
```

All three commands must produce no error output; `gofmt -l` must print nothing.

## Owner decisions needed

None — fix is entirely within the four named log sites using stdlib-only helpers.
