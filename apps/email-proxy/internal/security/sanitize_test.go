package security_test

import (
	"fmt"
	"strings"
	"testing"

	"github.com/mintkey/mintkey/services/email-proxy/internal/security"
)

// ---------------------------------------------------------------------------
// Body content sanitizer tests
// ---------------------------------------------------------------------------

func TestScrubBodyForLog_NeverEchoesContent(t *testing.T) {
	sensitive := "My password is hunter2 and my SSN is 123-45-6789"
	result := security.ScrubBodyForLog(sensitive)
	if strings.Contains(result, "hunter2") || strings.Contains(result, "123-45-6789") {
		t.Errorf("scrub should never echo sensitive content; got: %s", result)
	}
}

func TestScrubBodyForLog_Shape(t *testing.T) {
	body := "Hello\nWorld\nLine3"
	result := security.ScrubBodyForLog(body)
	// Must contain byte count and line count.
	if !strings.Contains(result, "bytes") || !strings.Contains(result, "lines") {
		t.Errorf("scrub output should contain 'bytes' and 'lines'; got: %s", result)
	}
	// Must start with <scrubbed:
	if !strings.HasPrefix(result, "<scrubbed:") {
		t.Errorf("scrub output must start with <scrubbed:; got: %s", result)
	}
	// Must end with >
	if !strings.HasSuffix(result, ">") {
		t.Errorf("scrub output must end with >; got: %s", result)
	}
}

func TestScrubBodyForLog_ByteCount(t *testing.T) {
	body := "abcde"
	result := security.ScrubBodyForLog(body)
	expected := fmt.Sprintf("<scrubbed:%d bytes,1 lines>", len(body))
	if result != expected {
		t.Errorf("got %q, want %q", result, expected)
	}
}

func TestScrubBodyForLog_MultiLine(t *testing.T) {
	body := "line1\nline2\nline3\n"
	result := security.ScrubBodyForLog(body)
	if !strings.Contains(result, "3 lines") {
		t.Errorf("expected 3 lines in result; got: %s", result)
	}
}

func TestScrubBodyForLog_Empty(t *testing.T) {
	result := security.ScrubBodyForLog("")
	expected := "<scrubbed:0 bytes,0 lines>"
	if result != expected {
		t.Errorf("empty body: got %q, want %q", result, expected)
	}
}

func TestScrubBodyForLog_LargeBody(t *testing.T) {
	body := strings.Repeat("X", 1<<20) // 1 MiB
	result := security.ScrubBodyForLog(body)
	if strings.Contains(result, "X") {
		t.Error("large body content must not leak into scrubbed output")
	}
	if !strings.Contains(result, "bytes") {
		t.Errorf("large body scrub missing byte count; got: %s", result)
	}
}
