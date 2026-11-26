// Package store — source-level tests for the egress scope and the stores'
// not-found sentinel.
//
// Source: proxy-public-egress spec, requirement "The vault adapter stores and
// returns the scope"; design D1/D7.
package store

import (
	"context"
	"database/sql"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// targetURLFiles are the non-test Go files that mention the stored target at
// the base of this change. Every one of them must also handle the egress scope.
var targetURLFiles = map[string]bool{
	"cmd/vault-migrate-sqlite-to-pg/main.go":    true,
	"cmd/vault-migrate-pg-to-hashicorp/main.go": true,
	"internal/cache/dek_cache.go":               true,
	"internal/server/grpc.go":                   true,
	"internal/server/vault.go":                  true,
	"internal/store/sqlite.go":                  true,
	"internal/store/postgres.go":                true,
	"internal/store/hashicorp_doc.go":           true,
}

// TestEveryTargetURLFileHandlesEgressScope: every non-test Go file that handles
// the stored target also mentions the egress scope, and the files found are
// exactly the eight that handle the target at the base.
func TestEveryTargetURLFileHandlesEgressScope_C_1971e22f(t *testing.T) {
	t.Run("C-1971e22f", func(t *testing.T) {
		root := filepath.Join("..", "..")
		found := make(map[string]bool)

		err := filepath.WalkDir(root, func(path string, d fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if d.IsDir() {
				return nil
			}
			if !strings.HasSuffix(path, ".go") || strings.HasSuffix(path, "_test.go") {
				return nil
			}

			content, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			text := strings.ToLower(string(content))
			if !strings.Contains(text, "target_url") && !strings.Contains(text, "targeturl") {
				return nil
			}

			rel, err := filepath.Rel(root, path)
			if err != nil {
				return err
			}
			rel = filepath.ToSlash(rel)
			found[rel] = true

			if !strings.Contains(text, "egress_scope") && !strings.Contains(text, "egressscope") {
				t.Errorf("%s handles the stored target but does not mention the egress scope", rel)
			}
			return nil
		})
		if err != nil {
			t.Fatalf("walk %s: %v", root, err)
		}

		for rel := range targetURLFiles {
			if !found[rel] {
				t.Errorf("%s was not found among the files that handle the stored target", rel)
			}
		}
		for rel := range found {
			if !targetURLFiles[rel] {
				t.Errorf("%s handles the stored target but is not one of the eight files", rel)
			}
		}
	})
}

// functionBody returns the text between the braces of the function whose
// signature starts with signaturePrefix.
func functionBody(t *testing.T, src, signaturePrefix string) string {
	t.Helper()
	start := strings.Index(src, signaturePrefix)
	if start < 0 {
		t.Fatalf("function %q not found", signaturePrefix)
	}
	open := strings.Index(src[start:], "{")
	if open < 0 {
		t.Fatalf("function %q has no body", signaturePrefix)
	}
	depth := 0
	for i := start + open; i < len(src); i++ {
		switch src[i] {
		case '{':
			depth++
		case '}':
			depth--
			if depth == 0 {
				return src[start+open+1 : i]
			}
		}
	}
	t.Fatalf("function %q has an unbalanced body", signaturePrefix)
	return ""
}

// TestStoreNotFoundIsSqlErrNoRows: the SQLite store wraps sql.ErrNoRows for an
// absent version and answers the scope of the version it returns from the same
// Get (the requirement's "the SQLite ... store ... SHALL carry the value"), and
// the Get functions of the PostgreSQL and HashiCorp stores wrap sql.ErrNoRows
// with %w on every not-found return.
func TestStoreNotFoundIsSqlErrNoRows_C_0704866f(t *testing.T) {
	t.Run("C-0704866f", func(t *testing.T) {
		s, err := New(":memory:")
		if err != nil {
			t.Fatalf("store.New: %v", err)
		}
		defer func() { _ = s.Close() }()

		if _, err := s.Get(context.Background(), "tenant_missing", "svc_missing", 0); !errors.Is(err, sql.ErrNoRows) {
			t.Fatalf("SQLite Get error = %v, want an error satisfying errors.Is(err, sql.ErrNoRows)", err)
		}

		// The same Get answers the scope of the version it returns (the
		// requirement's "the SQLite ... store ... SHALL carry the value"), so the
		// sentinel and the scope travel through one lookup.
		rec := CredentialRecord{
			CredentialID: "cred_not_found_sentinel",
			TenantID:     "tenant_sentinel",
			ServiceID:    "svc_sentinel",
			AuthScheme:   1,
			WrappedDEK:   []byte{1, 2, 3},
			EncPayload:   []byte{4, 5, 6},
		}
		egressScopeField(t, &rec).SetString("public")
		if _, err := s.Put(context.Background(), rec); err != nil {
			t.Fatalf("Put: %v", err)
		}
		stored, err := s.Get(context.Background(), "tenant_sentinel", "svc_sentinel", 0)
		if err != nil {
			t.Fatalf("Get stored version: %v", err)
		}
		if stored == nil {
			t.Fatalf("Get stored version returned no record")
		}
		if scope := egressScopeField(t, stored).String(); scope != "public" {
			t.Errorf("stored scope = %q, want %q", scope, "public")
		}

		files := []struct {
			path      string
			signature string
		}{
			{path: "postgres.go", signature: "func (s *PostgresStore) Get("},
			{path: "hashicorp.go", signature: "func (s *HashiCorpStore) Get("},
		}
		for _, f := range files {
			content, err := os.ReadFile(f.path)
			if err != nil {
				t.Fatalf("read %s: %v", f.path, err)
			}
			body := functionBody(t, string(content), f.signature)

			notFoundReturns := 0
			for _, line := range strings.Split(body, "\n") {
				code := line
				if idx := strings.Index(code, "//"); idx >= 0 {
					code = code[:idx]
				}
				if !strings.Contains(code, "sql.ErrNoRows") {
					continue
				}
				notFoundReturns++
				if !strings.Contains(code, "%w") {
					t.Errorf("%s: not-found return does not wrap sql.ErrNoRows with %%w: %s", f.path, strings.TrimSpace(line))
				}
			}
			if notFoundReturns == 0 {
				t.Errorf("%s: Get has no not-found return that wraps sql.ErrNoRows", f.path)
			}
		}
	})
}
