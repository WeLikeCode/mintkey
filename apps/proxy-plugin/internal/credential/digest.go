// Package credential — HTTP Digest (auth_scheme=17) support.
//
// Digest is a 401→challenge→retry handshake, so a static Authorization header
// cannot express it. Instead the proxy attaches a per-request digest.Transport
// (github.com/icholy/digest, MIT) to the reverse proxy: it performs the RFC 2617
// challenge-response using the stored public_key as the username and private_key
// as the password.
//
// Source: ADR-0029; design.md Component 2; vault.proto AUTH_SCHEME_HTTP_DIGEST = 17.
package credential

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/icholy/digest"
)

// errInvalidDigestPayload is returned when the credential payload is not the
// expected {public_key, private_key} envelope. The error text is a fixed
// sentinel — it MUST NOT echo any credential bytes (S-SEC-1).
var errInvalidDigestPayload = errors.New("http_digest: credential payload must contain non-empty public_key and private_key")

// NewDigestTransport parses an http_digest credential payload and returns a
// per-request *digest.Transport that authenticates the upstream via RFC 2617
// Digest challenge-response. PublicKey is the username, PrivateKey the password.
// base is the underlying RoundTripper carrying the request bytes; when nil,
// http.DefaultTransport is used. The returned transport is single-use per proxy
// request — no plaintext credential is cached across requests (ADR-0014.4).
//
// On malformed or incomplete payloads it returns errInvalidDigestPayload, whose
// text never contains submitted credential material.
func NewDigestTransport(payload []byte, base http.RoundTripper) (*digest.Transport, error) {
	var cred HTTPDigestCredential
	if err := json.Unmarshal(payload, &cred); err != nil {
		return nil, errInvalidDigestPayload
	}
	if cred.PublicKey == "" || cred.PrivateKey == "" {
		return nil, errInvalidDigestPayload
	}
	if base == nil {
		base = http.DefaultTransport
	}
	return &digest.Transport{
		Username:  cred.PublicKey,
		Password:  cred.PrivateKey,
		Transport: base,
	}, nil
}
