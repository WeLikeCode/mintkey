// Package scrubber strips credential echoes from backend responses before they
// reach the agent, per ADR-0014.4 and S-SEC-1.
//
// Scope: response headers (Authorization, Cookie, Set-Cookie, X-Auth-Token,
// X-Api-Key) and response body patterns (api_key=<value>, JWT eyJ…, sk_/pk_
// prefixed tokens). Those pattern rules are optional: a caller passes patterns
// to choose them. Independently of the pattern rules, the exact value of each
// secret the caller names is redacted in every header value and in the body,
// in its raw, standard-base64 and URL-query-escaped forms. Secrets shorter
// than 8 bytes are skipped.
//
// Body scan is bounded to the first 256 KiB; the bytes past the bound are
// passed on unchanged. A body that changed within the scanned part loses its
// Content-Length header (the length is no longer 307200-style) and reports
// ContentLength -1, while an unchanged body keeps both.
//
// When any credential echo is detected the caller should emit the audit event
// named by AuditEventCredentialEchoDetected.
package scrubber

import (
	"bytes"
	"encoding/base64"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"sort"
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

const (
	maxBodyScanBytes = 256 * 1024
	// minSecretBytes is the shortest secret whose exact value is redacted.
	// Shorter values would also match unrelated text.
	minSecretBytes = 8
	// redactedMarker replaces the matching text of an injected secret.
	redactedMarker = "[REDACTED]"
)

// ScrubResult is returned by Scrub, ScrubWith and ScrubHeaders.
type ScrubResult struct {
	// Response is the (possibly mutated) response to forward to the agent.
	Response *http.Response
	// Detected is true when at least one credential echo was found and removed.
	Detected bool
	// Locations names each site where a credential was detected, e.g.
	// "header:Authorization" or "body".
	Locations []string
	// Err is the error of reading the scanned part of the body, nil otherwise.
	// The body then holds the bytes read so far and must not be forwarded.
	Err error
}

// Scrub strips credential echoes from a backend HTTP response.
// It mutates resp in place (header deletions) and replaces resp.Body with a
// scrubbed copy.
//
// Scrub is idempotent: scrub(scrub(r)).body == scrub(r).body.
func Scrub(resp *http.Response) ScrubResult {
	return ScrubWith(resp, true)
}

// ScrubWith strips credential echoes from a backend HTTP response.
// It applies the pattern rules only when patterns is true; the exact values of
// secrets are redacted for every call. It mutates resp in place and replaces
// resp.Body with the scrubbed head followed by the bytes past the scan bound.
//
// A nil or empty secret is skipped.
func ScrubWith(resp *http.Response, patterns bool, secrets ...[]byte) ScrubResult {
	result := ScrubHeaders(resp, patterns, secrets...)

	if resp.Body == nil {
		return result
	}

	original := resp.Body
	data, err := io.ReadAll(io.LimitReader(original, maxBodyScanBytes))
	if err != nil {
		// The scanned part could not be read: do not forward the bytes read
		// so far, and report the failure to the caller.
		result.Err = err
		original.Close()
		resp.Body = io.NopCloser(bytes.NewReader(data))
		return result
	}

	scrubbed := data
	if patterns {
		// Apply patterns in a fixed order so the result is stable on re-application.
		scrubbed = jwtPattern.ReplaceAll(scrubbed, []byte("[REDACTED_JWT]"))
		scrubbed = apiKeyPattern.ReplaceAll(scrubbed, []byte("${1}[REDACTED]"))
		scrubbed = credPrefixPattern.ReplaceAll(scrubbed, []byte("[REDACTED]"))
	}
	scrubbed = replaceSecrets(scrubbed, secretForms(secrets))

	changed := !bytes.Equal(scrubbed, data)
	if changed {
		result.Detected = true
		result.Locations = append(result.Locations, "body")
		resp.Header.Del("Content-Length")
		resp.ContentLength = -1
	}

	if len(data) < maxBodyScanBytes {
		// The whole body was scanned; nothing remains to stream.
		original.Close()
		resp.Body = io.NopCloser(bytes.NewReader(scrubbed))
		return result
	}

	// The head was scanned; pass the rest of the original body on unchanged.
	resp.Body = &scrubbedBody{
		Reader: io.MultiReader(bytes.NewReader(scrubbed), original),
		closer: original,
	}
	return result
}

// ScrubHeaders applies only the header part of ScrubWith: the forbidden header
// removals (when patterns is true) and the exact-value redaction of secrets in
// every header value. It does not read or replace the body.
func ScrubHeaders(resp *http.Response, patterns bool, secrets ...[]byte) ScrubResult {
	result := ScrubResult{Response: resp}

	// --- Header scrubbing ---
	if patterns {
		for _, h := range forbiddenHeaders {
			if resp.Header.Get(h) != "" {
				resp.Header.Del(h)
				result.Detected = true
				result.Locations = append(result.Locations, "header:"+h)
			}
		}
	}

	// --- Secret redaction in header values ---
	forms := secretForms(secrets)
	if len(forms) == 0 {
		return result
	}
	for name, values := range resp.Header {
		changed := false
		for i, value := range values {
			scrubbed := replaceSecrets([]byte(value), forms)
			if !bytes.Equal(scrubbed, []byte(value)) {
				values[i] = string(scrubbed)
				changed = true
			}
		}
		if changed {
			result.Detected = true
			result.Locations = append(result.Locations, "header:"+name)
		}
	}

	return result
}

// secretForms returns the forms to redact for the given secrets: the raw
// value, its standard base64 encoding and its URL-query-escaped form, longest
// first. Nil, empty and shorter-than-8-byte secrets are skipped, as are
// duplicate forms.
func secretForms(secrets [][]byte) [][]byte {
	seen := make(map[string]struct{})
	var forms [][]byte
	add := func(form []byte) {
		if len(form) == 0 {
			return
		}
		if _, ok := seen[string(form)]; ok {
			return
		}
		seen[string(form)] = struct{}{}
		forms = append(forms, form)
	}
	for _, secret := range secrets {
		if len(secret) < minSecretBytes {
			continue
		}
		add(append([]byte(nil), secret...))
		encoded := make([]byte, base64.StdEncoding.EncodedLen(len(secret)))
		base64.StdEncoding.Encode(encoded, secret)
		add(encoded)
		add([]byte(url.QueryEscape(string(secret))))
	}
	// Longest first: a shorter form must not break a longer one apart.
	sort.SliceStable(forms, func(i, j int) bool { return len(forms[i]) > len(forms[j]) })
	return forms
}

// replaceSecrets replaces every occurrence of each form in data with the
// redaction marker.
func replaceSecrets(data []byte, forms [][]byte) []byte {
	for _, form := range forms {
		data = bytes.ReplaceAll(data, form, []byte(redactedMarker))
	}
	return data
}

// scrubbedBody streams the scrubbed head followed by the untouched tail of the
// original response body, and closes the original when it is closed.
type scrubbedBody struct {
	io.Reader
	closer io.Closer
}

// Close closes the original response body.
func (b *scrubbedBody) Close() error {
	return b.closer.Close()
}
