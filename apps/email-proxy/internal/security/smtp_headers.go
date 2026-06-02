package security

import (
	"errors"
	"fmt"
	"strings"
)

// maxHeaderNameLen is the maximum number of bytes allowed in a header field name.
// RFC 5322 §2.2 does not define a hard limit; 78 is a practical upper bound
// for standard + X- headers.
const maxHeaderNameLen = 78

// maxHeaderValueLen is the maximum number of bytes allowed in a header field value.
// RFC 5322 §2.1.1 specifies max line length of 998 chars; we enforce the same.
const maxHeaderValueLen = 998

// SanitizeHeader validates and normalises a MIME/SMTP header name+value pair.
//
// Security guarantees (NFR-19, SEC-03):
//   - Rejects any input containing \r or \n (CRLF injection prevention).
//   - Rejects control characters 0x00–0x1F (except \t) and 0x7F in both
//     name and value.
//   - Enforces maximum lengths: name ≤ 78 bytes, value ≤ 998 bytes.
//   - Rejects empty header names (a name is mandatory).
//
// Returns (lowercased-name, trimmed-value, nil) on success.
func SanitizeHeader(name, value string) (string, string, error) {
	if name == "" {
		return "", "", errors.New("security: header name must not be empty")
	}
	if len(name) > maxHeaderNameLen {
		return "", "", fmt.Errorf("security: header name length %d exceeds max %d", len(name), maxHeaderNameLen)
	}
	if len(value) > maxHeaderValueLen {
		return "", "", fmt.Errorf("security: header value length %d exceeds max %d", len(value), maxHeaderValueLen)
	}

	// Scan name for injection chars.
	if err := rejectInjectionChars(name); err != nil {
		return "", "", fmt.Errorf("security: header name: %w", err)
	}
	// Scan value for injection chars.
	if err := rejectInjectionChars(value); err != nil {
		return "", "", fmt.Errorf("security: header value: %w", err)
	}

	return strings.ToLower(name), value, nil
}
