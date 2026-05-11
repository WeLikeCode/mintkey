// Package health provides the GET /v1/health HTTP handler for kong-syncer.
//
// Source: design §9; T-1.0.6.
package health

import (
	"fmt"
	"net/http"
)

// Handler returns an http.Handler that responds with 200 {"status":"ok"}.
func Handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"status":"ok"}`)
	})
}
