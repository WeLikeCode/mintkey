package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/scrubber"
)

// errEncodedResponse and errBodyUnreadable tell the two unreadable-body causes
// apart from a failed round trip, so ErrorHandler can answer with the text of
// the spec.
var (
	errEncodedResponse = errors.New("encoded response not supported")
	errBodyUnreadable  = errors.New("upstream response unreadable")
)

// serviceIDContextKey holds the service id of the request for the echo log. The
// service id never leaves the process; it is not a credential.
type serviceIDContextKey struct{}

// withServiceID stores the service id of a request in its context.
func withServiceID(ctx context.Context, serviceID string) context.Context {
	return context.WithValue(ctx, serviceIDContextKey{}, serviceID)
}

// serviceIDFromContext returns the service id stored by withServiceID, or "".
func serviceIDFromContext(ctx context.Context) string {
	if serviceID, ok := ctx.Value(serviceIDContextKey{}).(string); ok {
		return serviceID
	}
	return ""
}

// upstreamTransport carries the upstream request. It removes the caller's
// Accept-Encoding before the call so the Go transport asks for gzip itself and
// decodes it, and calls base (or http.DefaultTransport when base is nil).
type upstreamTransport struct {
	base http.RoundTripper
}

// RoundTrip removes the caller's Accept-Encoding and forwards the request
// through base. It clones the request so the caller's copy is untouched.
func (t *upstreamTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	clone := req.Clone(req.Context())
	clone.Header = req.Header.Clone()
	clone.Header.Del("Accept-Encoding")

	base := t.base
	if base == nil {
		base = http.DefaultTransport
	}
	return base.RoundTrip(clone)
}

// newUpstreamProxy returns the reverse proxy of one request. base is the
// transport that carries the request (nil: the default transport). The proxy's
// Transport removes the caller's Accept-Encoding header and calls base;
// ModifyResponse refuses an encoded body, leaves an event stream unbuffered,
// and otherwise scrubs the response with scrubber.ScrubWith, logging a detected
// echo. ErrorHandler answers 502 with the texts of the spec. The flow sets its
// own Director after the call.
func (h *proxyHandler) newUpstreamProxy(target *url.URL, base http.RoundTripper, injected ...[]byte) *httputil.ReverseProxy {
	proxy := httputil.NewSingleHostReverseProxy(target)
	proxy.Transport = &upstreamTransport{base: base}

	proxy.ModifyResponse = func(resp *http.Response) error {
		serviceID := ""
		if resp.Request != nil {
			serviceID = serviceIDFromContext(resp.Request.Context())
		}

		if !bodilessResponse(resp) && hasEncodedBody(resp) {
			resp.Body.Close()
			return errEncodedResponse
		}

		if isEventStream(resp) {
			// A stream is never read ahead: only its headers are scrubbed, so
			// the first event reaches the caller without waiting for 256 KiB or
			// the end of the stream.
			result := scrubber.ScrubHeaders(resp, h.cfg.ScrubPatterns, injected...)
			logDetectedEcho(serviceID, result)
			return nil
		}

		result := scrubber.ScrubWith(resp, h.cfg.ScrubPatterns, injected...)
		logDetectedEcho(serviceID, result)
		if result.Err != nil {
			resp.Body.Close()
			return errBodyUnreadable
		}
		return nil
	}

	proxy.ErrorHandler = func(w http.ResponseWriter, _ *http.Request, err error) {
		switch {
		case errors.Is(err, errEncodedResponse):
			http.Error(w, "bad gateway: encoded response not supported", http.StatusBadGateway)
		case errors.Is(err, errBodyUnreadable):
			http.Error(w, "bad gateway: upstream response unreadable", http.StatusBadGateway)
		default:
			http.Error(w, "bad gateway: upstream unreachable", http.StatusBadGateway)
		}
	}

	return proxy
}

// hasEncodedBody reports whether the response still carries a Content-Encoding
// other than identity.
func hasEncodedBody(resp *http.Response) bool {
	encoding := strings.TrimSpace(resp.Header.Get("Content-Encoding"))
	if encoding == "" {
		return false
	}
	return !strings.EqualFold(encoding, "identity")
}

// bodilessResponse reports whether the response has no body to scan: a HEAD
// answer, 204 or 304. A bodiless answer is not refused for its encoding.
func bodilessResponse(resp *http.Response) bool {
	if resp.Request != nil && resp.Request.Method == http.MethodHead {
		return true
	}
	return resp.StatusCode == http.StatusNoContent || resp.StatusCode == http.StatusNotModified
}

// isEventStream reports whether the response is a server-sent event stream,
// which must not be buffered.
func isEventStream(resp *http.Response) bool {
	contentType := resp.Header.Get("Content-Type")
	if i := strings.IndexByte(contentType, ';'); i >= 0 {
		contentType = contentType[:i]
	}
	return strings.EqualFold(strings.TrimSpace(contentType), "text/event-stream")
}

// logDetectedEcho logs a detected credential echo with the service id and the
// locations only, never a value.
func logDetectedEcho(serviceID string, result scrubber.ScrubResult) {
	if !result.Detected {
		return
	}
	log.Printf("proxy-plugin: credential echo removed (svc=%s locations=%s)",
		safeID(serviceID), strings.Join(result.Locations, ","))
}
