package main

import (
	"net/http"
	"net/url"
	"testing"
)

func reqFor(t *testing.T, target string) (*http.Request, *url.URL) {
	t.Helper()
	u, err := url.Parse(target)
	if err != nil {
		t.Fatal(err)
	}
	r, err := http.NewRequest(http.MethodGet, target+"/v1/x", nil)
	if err != nil {
		t.Fatal(err)
	}
	return r, u
}

func TestEnsureRequestID_ContaboGetsHeaderWhenMissing(t *testing.T) {
	r, u := reqFor(t, "https://api.contabo.com")
	ensureRequestID(r, u)
	if r.Header.Get("X-Request-Id") == "" {
		t.Fatal("contabo request should get X-Request-Id")
	}
}

func TestEnsureRequestID_OtherServiceUntouched(t *testing.T) {
	for _, target := range []string{"https://api.example.com", "https://contabo.example.org", "https://api.contabo.com.evil.io"} {
		r, u := reqFor(t, target)
		ensureRequestID(r, u)
		if got := r.Header.Get("X-Request-Id"); got != "" {
			t.Fatalf("%s: unexpected X-Request-Id %q", target, got)
		}
	}
}

func TestEnsureRequestID_ExistingHeaderNeverOverwritten(t *testing.T) {
	r, u := reqFor(t, "https://api.contabo.com")
	r.Header.Set("X-Request-Id", "caller-supplied")
	ensureRequestID(r, u)
	if got := r.Header.Get("X-Request-Id"); got != "caller-supplied" {
		t.Fatalf("header overwritten: %q", got)
	}
}
