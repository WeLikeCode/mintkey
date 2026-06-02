// Package security provides email-proxy security primitives:
// RFC 5322 address parsing, domain allowlist enforcement, body-content
// sanitisation, per-(agent, service) rate limiting, and SMTP header
// injection prevention.
//
// Every function that accepts user-supplied input applies CRLF injection
// checks (NFR-19) before any further processing.
package security

import (
	"errors"
	"fmt"
	"net/mail"
	"strings"
	"unicode"
)

// maxRawListLen is the maximum number of bytes we will attempt to parse in an
// address-list string. Values above this are rejected without parsing.
const maxRawListLen = 998 // RFC 5321 §4.5.3 max line length

// Addr is a parsed RFC 5322 email address.
type Addr struct {
	// DisplayName is the human-readable name, e.g. "Alice Smith" (may be empty).
	DisplayName string
	// Local is the local-part of the address (before @), e.g. "alice+tag".
	Local string
	// Domain is the domain part of the address (after @), e.g. "example.com".
	Domain string
}

// String returns the addr in "local@domain" form.
func (a Addr) String() string { return a.Local + "@" + a.Domain }

// ParseAddressList parses a comma-separated RFC 5322 address list.
//
// Security guarantees (NFR-19, SEC-01):
//   - Rejects any input containing \r or \n (CRLF injection prevention).
//   - Rejects control characters 0x00–0x1F (except \t) and 0x7F.
//   - Enforces length limits: local-part ≤ 64, domain ≤ 255, full addr ≤ 320.
//   - Rejects oversized raw inputs (> maxRawListLen bytes) without parsing.
//   - Rejects empty input.
func ParseAddressList(s string) ([]Addr, error) {
	if s == "" {
		return nil, errors.New("security/addr: empty address list")
	}
	if len(s) > maxRawListLen {
		return nil, fmt.Errorf("security/addr: input too long (%d bytes, max %d)", len(s), maxRawListLen)
	}

	// CRLF injection and control-char check on raw input before any parsing.
	if err := rejectInjectionChars(s); err != nil {
		return nil, fmt.Errorf("security/addr: %w", err)
	}

	parsed, err := mail.ParseAddressList(s)
	if err != nil {
		return nil, fmt.Errorf("security/addr: parse failed: %w", err)
	}
	if len(parsed) == 0 {
		return nil, errors.New("security/addr: no valid addresses found")
	}

	addrs := make([]Addr, 0, len(parsed))
	for _, ma := range parsed {
		// net/mail guarantees addr is "local@domain" after parsing.
		at := strings.LastIndex(ma.Address, "@")
		if at < 0 {
			return nil, fmt.Errorf("security/addr: address %q missing @", ma.Address)
		}
		local := ma.Address[:at]
		domain := ma.Address[at+1:]

		if err := validateAddrParts(local, domain); err != nil {
			return nil, err
		}

		addrs = append(addrs, Addr{
			DisplayName: ma.Name,
			Local:       local,
			Domain:      domain,
		})
	}
	return addrs, nil
}

// rejectInjectionChars rejects any string containing CRLF or control chars
// 0x00–0x1F (except horizontal tab 0x09 which is valid in folded headers)
// or 0x7F (DEL).
func rejectInjectionChars(s string) error {
	for i, r := range s {
		if r == '\r' || r == '\n' {
			return fmt.Errorf("CRLF injection character at byte offset %d", i)
		}
		if r != '\t' && r < 0x20 {
			return fmt.Errorf("control character 0x%02X at byte offset %d", r, i)
		}
		if r == 0x7F {
			return fmt.Errorf("DEL (0x7F) character at byte offset %d", i)
		}
	}
	return nil
}

// validateAddrParts enforces RFC 5321 §4.5.3 length limits.
func validateAddrParts(local, domain string) error {
	if len(local) > 64 {
		return fmt.Errorf("security/addr: local-part %q exceeds 64 chars (got %d)", local, len(local))
	}
	if len(domain) > 255 {
		return fmt.Errorf("security/addr: domain %q exceeds 255 chars (got %d)", domain, len(domain))
	}
	full := len(local) + 1 + len(domain) // local@domain
	if full > 320 {
		return fmt.Errorf("security/addr: full address exceeds 320 chars (got %d)", full)
	}
	// domain must contain at least one non-space character (basic sanity).
	if strings.TrimFunc(domain, unicode.IsSpace) == "" {
		return fmt.Errorf("security/addr: domain %q is blank", domain)
	}
	return nil
}
