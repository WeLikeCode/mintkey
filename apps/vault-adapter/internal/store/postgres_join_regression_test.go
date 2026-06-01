// postgres_join_regression_test.go — regression guard for the s.id::text = vc.service_id bug.
//
// Bug: commit eb1a2e1 introduced `LEFT JOIN public.services s ON s.id::text = vc.service_id`.
// Both s.id and vc.service_id are uuid columns. The ::text cast on only the LHS produces a
// "text = uuid" comparison that Postgres rejects with SQLSTATE 42883
// ("operator does not exist: text = uuid"), breaking every GetCredential call on the live stack.
//
// Fix: use bare `s.id = vc.service_id` (plain uuid equality, uses the PK index on services.id).
//
// This test runs by default (no build tag) and scans postgres.go to assert the broken form is
// absent and the correct form is present — catching any future re-introduction at `go test ./...` time.
package store

import (
	"os"
	"strings"
	"testing"
)

// TestPostgresGet_JoinDoesNotCastUUID_Regression guards against the re-introduction of the
// `s.id::text = vc.service_id` bug that causes SQLSTATE 42883 on the live stack.
//
// Table-driven: one case per SQL branch in the Get function.
func TestPostgresGet_JoinDoesNotCastUUID_Regression(t *testing.T) {
	src, err := os.ReadFile("postgres.go")
	if err != nil {
		t.Fatalf("cannot read postgres.go for regression check: %v", err)
	}
	content := string(src)

	tests := []struct {
		name        string
		badPattern  string
		goodPattern string
	}{
		{
			name:        "is_current branch",
			badPattern:  "s.id::text = vc.service_id",
			goodPattern: "s.id = vc.service_id",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if strings.Contains(content, tc.badPattern) {
				t.Errorf("regression: postgres.go contains %q — this causes SQLSTATE 42883 "+
					"(operator does not exist: text = uuid) on the live stack; "+
					"fix: use %q (bare uuid equality)", tc.badPattern, tc.goodPattern)
			}
			if !strings.Contains(content, tc.goodPattern) {
				t.Errorf("invariant: postgres.go does not contain expected JOIN form %q — "+
					"the regression fix may be missing", tc.goodPattern)
			}
		})
	}
}
