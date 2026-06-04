package handlers

// Internal (white-box) tests for unexported helpers in email.go.
//
// Lives in package `handlers` (not `handlers_test`) so it can reach
// resolveIMAPAddr directly. The black-box behavioural tests live in
// handlers_email_test.go (`package handlers_test`).

import (
	"testing"

	"github.com/mintkey/mintkey/services/email-proxy/internal/vault"
)

// TestResolveIMAPAddr exercises the priority chain documented on
// resolveIMAPAddr:
//
//  1. cred.IMAPHost:cred.IMAPPort  (primary — ADR-0024 Phase 2)
//  2. payloadIMAPHost              (legacy password-payload fallback)
//  3. cred.BaseUrl                 (legacy fallback; empty for email_services)
//
// The cases mirror the table in the C-1 plan: primary wins, primary
// overrides both fallbacks, payload fallback works for password schemes,
// BaseUrl fallback works when both primary and payload are absent, and
// the "no source" case returns "" so the caller emits the 503.
func TestResolveIMAPAddr(t *testing.T) {
	tests := []struct {
		name            string
		cred            *vault.Credential
		payloadIMAPHost string
		want            string
	}{
		{
			name: "primary IMAPHost+IMAPPort wins",
			cred: &vault.Credential{
				IMAPHost: "imap.gmail.com",
				IMAPPort: 993,
			},
			payloadIMAPHost: "",
			want:            "imap.gmail.com:993",
		},
		{
			name: "primary overrides both fallbacks",
			cred: &vault.Credential{
				IMAPHost: "imap.gmail.com",
				IMAPPort: 993,
				BaseUrl:  "should-not-be-used:1234",
			},
			payloadIMAPHost: "should-not-be-used:5678",
			want:            "imap.gmail.com:993",
		},
		{
			name: "payload imap_host fallback when IMAPHost empty (password scheme)",
			cred: &vault.Credential{
				// IMAPHost / IMAPPort zero values intentionally
				BaseUrl: "",
			},
			payloadIMAPHost: "im.softuraj.solutions:993",
			want:            "im.softuraj.solutions:993",
		},
		{
			name: "BaseUrl fallback when IMAPHost and payload empty",
			cred: &vault.Credential{
				BaseUrl: "legacy:993",
			},
			payloadIMAPHost: "",
			want:            "legacy:993",
		},
		{
			name:            "all sources empty → empty string (caller emits 503)",
			cred:            &vault.Credential{},
			payloadIMAPHost: "",
			want:            "",
		},
		{
			name: "IMAPPort=0 treated as missing → fall through to payload",
			cred: &vault.Credential{
				IMAPHost: "imap.gmail.com",
				IMAPPort: 0,
				BaseUrl:  "legacy:993",
			},
			payloadIMAPHost: "payload-host:993",
			want:            "payload-host:993",
		},
		{
			name: "IMAPHost empty + IMAPPort set → fall through to BaseUrl",
			cred: &vault.Credential{
				IMAPHost: "",
				IMAPPort: 993,
				BaseUrl:  "legacy-fallback:993",
			},
			payloadIMAPHost: "",
			want:            "legacy-fallback:993",
		},
		{
			name:            "nil credential → empty (defensive)",
			cred:            nil,
			payloadIMAPHost: "ignored:993",
			want:            "",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := resolveIMAPAddr(tc.cred, tc.payloadIMAPHost)
			if got != tc.want {
				t.Errorf("resolveIMAPAddr() = %q, want %q", got, tc.want)
			}
		})
	}
}
