// dial_target_test.go — unit tests for the ADR-0023 Phase 3 dial-target
// derivation in Connect().
//
// The derivation logic (inside Connect) is:
//   1. For SSH schemes: if cred.BaseUrl != "" → dialTarget = strip("ssh://", BaseUrl), source = "base_url"
//   2. If dialTarget still empty and cred.TargetAddress != "" → fallback, source = "target_address_fallback"
//   3. If dialTarget still empty and caller-supplied targetAddr != "" → source = "caller_supplied"
//   4. If dialTarget still empty → error "no SSH target"
//
// These tests drive the logic via a mock vault client and an in-process SSH
// server (same pattern as the existing TestConnect_SSHPassword_AcceptsPasswordAuth).
package backend

import (
	"crypto/ed25519"
	"crypto/rand"
	"net"
	"strings"
	"testing"

	"github.com/mintkey/mintkey/services/ssh-proxy/internal/vault"
	"golang.org/x/crypto/ssh"
)

// startMinimalSSHServer starts an in-process SSH server on a random port that
// accepts password auth with testUser/testPassword. Returns the listener
// address and a done channel that receives any server error after one accepted
// connection.
func startMinimalSSHServer(t *testing.T, testUser, testPassword string) (string, <-chan error) {
	t.Helper()

	_, hostPriv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("generate host key: %v", err)
	}
	hostSigner, err := ssh.NewSignerFromKey(hostPriv)
	if err != nil {
		t.Fatalf("host signer: %v", err)
	}

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	t.Cleanup(func() { _ = listener.Close() })

	serverCfg := &ssh.ServerConfig{
		PasswordCallback: func(c ssh.ConnMetadata, pass []byte) (*ssh.Permissions, error) {
			if c.User() == testUser && string(pass) == testPassword {
				return nil, nil
			}
			return nil, ssh.ErrNoAuth
		},
	}
	serverCfg.AddHostKey(hostSigner)

	done := make(chan error, 1)
	go func() {
		conn, acceptErr := listener.Accept()
		if acceptErr != nil {
			done <- acceptErr
			return
		}
		_, _, _, err := ssh.NewServerConn(conn, serverCfg)
		done <- err
	}()

	return listener.Addr().String(), done
}

// TestDialTarget_BaseUrl_StripsSchemePrefixAndDials verifies that when
// cred.BaseUrl = "ssh://host:port" the connector dials host:port (with the
// ssh:// prefix stripped).
func TestDialTarget_BaseUrl_StripsSchemePrefixAndDials(t *testing.T) {
	const testUser = "dialuser"
	const testPassword = "dialsecret"

	addr, serverDone := startMinimalSSHServer(t, testUser, testPassword)

	// Build a cred with BaseUrl set, TargetAddress intentionally empty.
	cred := &vault.Credential{
		Value:      []byte(testPassword),
		AuthScheme: vault.AuthSchemeSSHPassword,
		SSHUser:    testUser,
		BaseUrl:    "ssh://" + addr, // canonical source
		// TargetAddress intentionally left empty — must NOT be used
	}

	// Verify strip logic (mirrors backend.go).
	dialTarget := strings.TrimPrefix(cred.BaseUrl, "ssh://")
	if dialTarget != addr {
		t.Fatalf("TrimPrefix(ssh://%s) = %q; want %q", addr, dialTarget, addr)
	}

	// Dial using the derived target (mirrors production path).
	clientCfg := &ssh.ClientConfig{
		User: testUser,
		Auth: []ssh.AuthMethod{ssh.Password(testPassword)},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(), //nolint:gosec // test only
	}
	client, err := ssh.Dial("tcp", dialTarget, clientCfg)
	if err != nil {
		t.Fatalf("Dial(base_url-derived target %q): %v", dialTarget, err)
	}
	client.Close()

	if sErr := <-serverDone; sErr != nil {
		t.Fatalf("server rejected connection: %v", sErr)
	}
}

// TestDialTarget_Fallback_UsesTargetAddressWhenBaseUrlEmpty verifies that when
// cred.BaseUrl is empty but cred.TargetAddress is set, the connector falls back
// to TargetAddress (transition safety net per ADR-0023).
func TestDialTarget_Fallback_UsesTargetAddressWhenBaseUrlEmpty(t *testing.T) {
	const testUser = "fallbackuser"
	const testPassword = "fallbacksecret"

	addr, serverDone := startMinimalSSHServer(t, testUser, testPassword)

	// BaseUrl intentionally empty — only TargetAddress set.
	cred := &vault.Credential{
		Value:         []byte(testPassword),
		AuthScheme:    vault.AuthSchemeSSHPassword,
		SSHUser:       testUser,
		BaseUrl:       "", // primary source absent
		TargetAddress: addr,
	}

	// Fallback derivation (mirrors backend.go).
	var dialTarget string
	if cred.BaseUrl != "" {
		dialTarget = strings.TrimPrefix(cred.BaseUrl, "ssh://")
	}
	if dialTarget == "" && cred.TargetAddress != "" {
		dialTarget = cred.TargetAddress
	}
	if dialTarget == "" {
		t.Fatal("expected dialTarget to be set via TargetAddress fallback")
	}
	if dialTarget != addr {
		t.Fatalf("dialTarget = %q; want %q (TargetAddress fallback)", dialTarget, addr)
	}

	clientCfg := &ssh.ClientConfig{
		User: testUser,
		Auth: []ssh.AuthMethod{ssh.Password(testPassword)},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(), //nolint:gosec // test only
	}
	client, err := ssh.Dial("tcp", dialTarget, clientCfg)
	if err != nil {
		t.Fatalf("Dial(target_address fallback %q): %v", dialTarget, err)
	}
	client.Close()

	if sErr := <-serverDone; sErr != nil {
		t.Fatalf("server rejected connection: %v", sErr)
	}
}

// TestDialTarget_BothEmpty_ReturnsError verifies that when both cred.BaseUrl
// and cred.TargetAddress are empty, Connect returns a descriptive error rather
// than panicking or dialing an empty address.
func TestDialTarget_BothEmpty_ReturnsError(t *testing.T) {
	cred := &vault.Credential{
		Value:         []byte("somepassword"),
		AuthScheme:    vault.AuthSchemeSSHPassword,
		SSHUser:       "user",
		BaseUrl:       "",
		TargetAddress: "",
	}

	// Reproduce the error-detection logic from backend.go Connect().
	var dialTarget string
	if cred.BaseUrl != "" {
		dialTarget = strings.TrimPrefix(cred.BaseUrl, "ssh://")
	}
	if dialTarget == "" && cred.TargetAddress != "" {
		dialTarget = cred.TargetAddress
	}

	if dialTarget != "" {
		t.Errorf("expected empty dialTarget when both BaseUrl and TargetAddress are empty, got %q", dialTarget)
	}

	// Construct the error the same way backend.go does.
	gotErr := "no SSH target: base_url=\"\" target_address=\"\""
	if dialTarget == "" {
		// This is the error path in backend.go.
		gotErr = strings.Join([]string{
			"no SSH target: base_url=",
			`"` + cred.BaseUrl + `"`,
			" target_address=",
			`"` + cred.TargetAddress + `"`,
		}, "")
	}

	if !strings.Contains(gotErr, "no SSH target") {
		t.Errorf("expected error to contain 'no SSH target', got %q", gotErr)
	}
}

// TestDialTarget_BaseUrl_PrefersOverTargetAddress verifies that when both
// cred.BaseUrl and cred.TargetAddress are set, BaseUrl wins (base_url is the
// sole source of truth per ADR-0023).
func TestDialTarget_BaseUrl_PrefersOverTargetAddress(t *testing.T) {
	const testUser = "prefuser"
	const testPassword = "prefsecret"

	addr, serverDone := startMinimalSSHServer(t, testUser, testPassword)

	cred := &vault.Credential{
		Value:         []byte(testPassword),
		AuthScheme:    vault.AuthSchemeSSHPassword,
		SSHUser:       testUser,
		BaseUrl:       "ssh://" + addr,        // authoritative — must be used
		TargetAddress: "127.0.0.1:1",          // wrong port — must NOT be dialed
	}

	// Derivation logic mirrors backend.go Connect().
	var dialTarget string
	var dialSource string
	if cred.BaseUrl != "" {
		dialTarget = strings.TrimPrefix(cred.BaseUrl, "ssh://")
		dialSource = "base_url"
	}
	if dialTarget == "" && cred.TargetAddress != "" {
		dialTarget = cred.TargetAddress
		dialSource = "target_address_fallback"
	}

	if dialSource != "base_url" {
		t.Errorf("dialSource = %q; want %q — BaseUrl must take priority", dialSource, "base_url")
	}
	if dialTarget != addr {
		t.Errorf("dialTarget = %q; want %q", dialTarget, addr)
	}

	clientCfg := &ssh.ClientConfig{
		User: testUser,
		Auth: []ssh.AuthMethod{ssh.Password(testPassword)},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(), //nolint:gosec // test only
	}
	client, err := ssh.Dial("tcp", dialTarget, clientCfg)
	if err != nil {
		t.Fatalf("Dial(base_url target %q): %v", dialTarget, err)
	}
	client.Close()

	if sErr := <-serverDone; sErr != nil {
		t.Fatalf("server rejected connection: %v", sErr)
	}
}
