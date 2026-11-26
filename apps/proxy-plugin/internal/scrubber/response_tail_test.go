package scrubber_test

import (
	"bytes"
	"io"
	"net/http"
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/scrubber"
)

// testTailResponse builds a 307200-byte response whose body holds the tail
// markers at the offsets of the scenario, with the length headers set as an
// upstream would set them.
func testTailResponse(body []byte) *http.Response {
	resp := &http.Response{
		StatusCode:    200,
		Header:        make(http.Header),
		Body:          io.NopCloser(bytes.NewReader(body)),
		ContentLength: int64(len(body)),
	}
	resp.Header.Set("Content-Length", "307200")
	return resp
}

func TestScrubKeepsBodyPastScanBound_C_f92ecc35(t *testing.T) {
	// The spec values are built from parts so no secret-shaped literal is
	// written in this file: api_key=<16 lowercase letters and digits> and
	// sk_live_<12 lowercase letters>.
	apiKeyValue := "api_" + "key=" + "abcdefghij012345"
	skeyValue := "sk_" + "live_" + "abcdefghijkl"

	body := bytes.Repeat([]byte(" "), 307200)
	copy(body[100:], []byte(apiKeyValue+"\n"))
	copy(body[296960:], []byte(skeyValue+"\n"))

	resp := testTailResponse(body)
	result := scrubber.Scrub(resp)
	if !result.Detected {
		t.Fatal("expected Detected=true for the api_key echo in the scanned part")
	}

	got, err := io.ReadAll(result.Response.Body)
	if err != nil {
		t.Fatalf("reading scrubbed body: %v", err)
	}

	// <apikey> is 24 bytes and api_key=[REDACTED] is 18, so the body loses 6
	// bytes; the tail past the scan bound is kept.
	const wantLen = 307194
	if len(got) != wantLen {
		t.Fatalf("scrubbed body length = %d, want %d", len(got), wantLen)
	}
	if !bytes.Contains(got, []byte("api_key=[REDACTED]")) {
		t.Fatalf("scrubbed body does not hold api_key=[REDACTED]")
	}

	shortened := len(apiKeyValue) + 1 - (len("api_key=[REDACTED]") + 1)
	skeyAt := 296960 - shortened
	if idx := bytes.Index(got, []byte(skeyValue)); idx != skeyAt {
		t.Fatalf("<skey> found at %d, want its place after the shortened part at %d", idx, skeyAt)
	}

	if _, ok := result.Response.Header["Content-Length"]; ok {
		t.Fatalf("Content-Length header must be removed when the scanned part changed, got %q",
			result.Response.Header.Get("Content-Length"))
	}
	if result.Response.ContentLength != -1 {
		t.Fatalf("ContentLength = %d, want -1", result.Response.ContentLength)
	}
}

func TestScrubUnchangedBodyKeepsLength_C_f92ecc35(t *testing.T) {
	body := bytes.Repeat([]byte(" "), 307200)
	resp := testTailResponse(body)

	result := scrubber.Scrub(resp)
	if result.Detected {
		t.Fatal("expected Detected=false for a body with no credential echo")
	}

	got, err := io.ReadAll(result.Response.Body)
	if err != nil {
		t.Fatalf("reading scrubbed body: %v", err)
	}
	if !bytes.Equal(got, body) {
		t.Fatalf("unchanged body was altered: got %d bytes, want %d", len(got), len(body))
	}
	if len(got) != 307200 {
		t.Fatalf("body length = %d, want 307200", len(got))
	}
	if cl := result.Response.Header.Get("Content-Length"); cl != "307200" {
		t.Fatalf("Content-Length header = %q, want %q", cl, "307200")
	}
	if result.Response.ContentLength != 307200 {
		t.Fatalf("ContentLength = %d, want 307200", result.Response.ContentLength)
	}
}
