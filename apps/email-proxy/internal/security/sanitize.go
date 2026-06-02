package security

import (
	"fmt"
	"strings"
)

// ScrubBodyForLog returns a safe-to-log representation of a message body.
//
// It NEVER includes any content from the body — only structural metadata
// (byte length and line count). This function must be used wherever body
// content might otherwise reach logs, audit rows, OTel span attributes,
// or error messages (NFR-21, SEC-06, R-1).
//
// Output shape: "<scrubbed:N bytes,M lines>"
func ScrubBodyForLog(body string) string {
	if body == "" {
		return "<scrubbed:0 bytes,0 lines>"
	}
	byteLen := len(body)
	lineCount := strings.Count(body, "\n")
	// A body with no newlines still counts as 1 line.
	if lineCount == 0 && byteLen > 0 {
		lineCount = 1
	}
	return fmt.Sprintf("<scrubbed:%d bytes,%d lines>", byteLen, lineCount)
}
