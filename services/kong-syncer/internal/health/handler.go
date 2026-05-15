// Package health provides the GET /v1/health HTTP handler for kong-syncer.
//
// The handler reports "ok" when the last Kong push succeeded and "degraded"
// when it failed, allowing operators to detect Kong sync failures via standard
// health checks.
//
// Source: design §9; T-1.0.6.
package health

import (
	"encoding/json"
	"net/http"
)

// StatusChecker is implemented by the changes.Client to report whether the last
// push attempt failed.
type StatusChecker interface {
	LastErr() error
}

// Handler returns an http.Handler that responds with 200 {"status":"ok"} when
// checker.LastErr() == nil, or 200 {"status":"degraded","reason":"..."} when the
// last Kong push failed.
//
// Pass nil to get a plain always-ok handler (backwards-compatible with tests
// that pre-date the checker).
func Handler(checker ...StatusChecker) http.Handler {
	var chk StatusChecker
	if len(checker) > 0 {
		chk = checker[0]
	}

	return http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		if chk != nil {
			if err := chk.LastErr(); err != nil {
				body := map[string]string{
					"status": "degraded",
					"reason": err.Error(),
				}
				_ = json.NewEncoder(w).Encode(body)
				return
			}
		}

		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
}
