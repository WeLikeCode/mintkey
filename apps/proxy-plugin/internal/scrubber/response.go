// Package scrubber strips credential echoes from backend responses before they
// reach the agent, per ADR-0014.4 and S-SEC-1.
//
// Scope: response headers (Authorization, Cookie, Set-Cookie, X-Auth-Token,
// X-Api-Key) and response body patterns (api_key=<value>, JWT eyJ…, sk_/pk_
// prefixed tokens). Body scan is bounded to the first 256 KiB.
//
// When any credential echo is detected the caller should emit the audit event
// named by AuditEventCredentialEchoDetected.
package scrubber

import (
	"bytes"
	"io"
	"net/http"
	"regexp"
)

// AuditEventCredentialEchoDetected is the audit event type to emit when the
// scrubber fires (proxy.credential_echo_detected).
const AuditEventCredentialEchoDetected = "proxy.credential_echo_detected"

// forbiddenHeaders are response headers that must never reach the agent.
var forbiddenHeaders = []string{
	"Authorization",
	"Cookie",
	"Set-Cookie",
	"X-Auth-Token",
	"X-Api-Key",
}

// Body patterns — order matters: JWT first so the [REDACTED_JWT] replacement
// tokens are not then matched by the credential prefix pattern.
var (
	// Full JWT: eyJ<header>.<payload>.<sig>
	jwtPattern = regexp.MustCompile(`eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+`)
	// api_key=<value> or api-key: <value> (form fields, URL params, JSON values)
	apiKeyPattern = regexp.MustCompile(`(?i)(api[_\-]?key\s*[=:]\s*)([A-Za-z0-9_\-\.]{8,})`)
	// sk_* / pk_* credential prefix tokens (e.g. Stripe-style keys)
	credPrefixPattern = regexp.MustCompile(`\b(sk|pk)_[A-Za-z0-9_\-]{8,}`)
)

const maxBodyScanBytes = 256 * 1024

// ScrubResult is returned by Scrub.
type ScrubResult struct {
	// Response is the (possibly mutated) response to forward to the agent.
	Response *http.Response
	// Detected is true when at least one credential echo was found and removed.
	Detected bool
	// Locations names each site where a credential was detected, e.g.
	// "header:Authorization" or "body".
	Locations []string
}

// Scrub strips credential echoes from a backend HTTP response.
// It mutates resp in place (header deletions) and replaces resp.Body with a
// scrubbed copy. The original Body is always closed before Scrub returns.
//
// Scrub is idempotent: scrub(scrub(r)).body == scrub(r).body.
func Scrub(resp *http.Response) ScrubResult {
	result := ScrubResult{Response: resp}

	// --- Header scrubbing ---
	for _, h := range forbiddenHeaders {
		if resp.Header.Get(h) != "" {
			resp.Header.Del(h)
			result.Detected = true
			result.Locations = append(result.Locations, "header:"+h)
		}
	}

	// --- Body scrubbing (bounded to maxBodyScanBytes) ---
	if resp.Body != nil {
		data, _ := io.ReadAll(io.LimitReader(resp.Body, maxBodyScanBytes))
		resp.Body.Close()

		scrubbed := data
		// Apply patterns in a fixed order so the result is stable on re-application.
		scrubbed = jwtPattern.ReplaceAll(scrubbed, []byte("[REDACTED_JWT]"))
		scrubbed = apiKeyPattern.ReplaceAll(scrubbed, []byte("${1}[REDACTED]"))
		scrubbed = credPrefixPattern.ReplaceAll(scrubbed, []byte("[REDACTED]"))

		if !bytes.Equal(scrubbed, data) {
			result.Detected = true
			result.Locations = append(result.Locations, "body")
		}

		resp.Body = io.NopCloser(bytes.NewReader(scrubbed))
	}

	return result
}
