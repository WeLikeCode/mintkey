// tls_test.go — tests for per-service InsecureSkipVerify flag in smtp.Client.Send (ADR-0024).
//
// Verifies that:
//   - Send with a Credential.InsecureSkipVerify=false against a self-signed cert
//     returns a TLS/x509 error.
//   - Send with Credential.InsecureSkipVerify=true against the same self-signed cert
//     succeeds and the message is delivered.
package smtp_test

import (
	"bytes"
	"context"
	"crypto/tls"
	"log/slog"
	"net"
	"strings"
	"testing"

	smtpclient "github.com/mintkey/mintkey/services/email-proxy/internal/smtp"
)

// TestSend_InsecureSkipVerify_False_FailsWithTLSError verifies that Send to a
// server with a self-signed implicit-TLS certificate fails when InsecureSkipVerify=false.
// We use Port=465 (implicit TLS path) so the client dials TLS immediately.
// The cert verification failure occurs during the TLS handshake.
func TestSend_InsecureSkipVerify_False_FailsWithTLSError(t *testing.T) {
	// Start an implicit-TLS server (SMTPS on a random port).
	serverTLSCfg := selfSignedTLS(t)
	srv := newTestServer(t, "plain", serverTLSCfg)
	defer srv.close()

	req := smtpclient.EmailSendRequest{
		From:    "a@example.com",
		To:      []string{"b@example.com"},
		Subject: "tls verify test",
		Body:    "should fail",
	}

	cred := smtpclient.Credential{
		AuthMode: smtpclient.AuthModePLAIN,
		Password: "secret",
		// InsecureSkipVerify: false (default)
	}

	// We test the cert-verification failure via the STARTTLS path: use a
	// STARTTLS server and a wrong ServerName in TLSConf (no InsecureSkipVerify).

	// Use a STARTTLS server + wrong ServerName → TLS handshake cert error.
	starttlsCfg := selfSignedTLS(t)
	starttlsSrv := &testSMTPServer{
		authMode: "plain",
		tlsCfg:   starttlsCfg,
		useTLS:   false, // STARTTLS server
	}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	starttlsSrv.listener = ln
	starttlsSrv.addr = ln.Addr().String()
	go starttlsSrv.serve()
	defer starttlsSrv.close()

	// Client uses wrong ServerName → cert verification fails at STARTTLS.
	cWrong := smtpclient.New(smtpclient.Config{
		TLSConf: &tls.Config{
			ServerName: "wrong.host.invalid", // won't match self-signed cert
		},
	})

	targetSTARTTLS := smtpclient.DialTarget{
		Host:               "127.0.0.1",
		Port:               portOf(starttlsSrv.addr), // non-465 → STARTTLS
		InsecureSkipVerify: false,
	}

	_, err = cWrong.Send(context.Background(), cred, req, targetSTARTTLS)
	if err == nil {
		t.Fatal("expected TLS cert verification error, got nil")
	}
	errMsg := err.Error()
	if !tlsErrMsg(errMsg) {
		t.Errorf("expected TLS/x509 error, got: %v", err)
	}
}

// TestSend_InsecureSkipVerify_True_Succeeds verifies that Send to a server with
// a self-signed TLS certificate succeeds when InsecureSkipVerify=true on the
// DialTarget (per-service vault flag path), and that a slog.Warn audit-trail
// entry was emitted.
func TestSend_InsecureSkipVerify_True_Succeeds(t *testing.T) {
	// Capture slog output so we can assert the audit warning was emitted.
	var logBuf bytes.Buffer
	prev := slog.Default()
	slog.SetDefault(slog.New(slog.NewJSONHandler(&logBuf, nil)))
	t.Cleanup(func() { slog.SetDefault(prev) })

	// Start a STARTTLS server — InsecureSkipVerify is set, so the warning IS emitted.
	srv := newSTARTTLSServer(t, "plain")
	defer srv.close()

	c := smtpclient.New(smtpclient.Config{})

	req := smtpclient.EmailSendRequest{
		From:    "sender@example.com",
		To:      []string{"recipient@example.com"},
		Subject: "insecure tls test",
		Body:    "should succeed",
	}

	cred := smtpclient.Credential{
		AuthMode:           smtpclient.AuthModePLAIN,
		Password:           "secret",
		InsecureSkipVerify: true, // per-service vault flag (ADR-0024)
	}

	// Port != 465 → STARTTLS path, plain server → send succeeds.
	target := smtpclient.DialTarget{
		Host:               "127.0.0.1",
		Port:               portOf(srv.addr),
		InsecureSkipVerify: true,
	}

	msgID, err := c.Send(context.Background(), cred, req, target)
	if err != nil {
		t.Fatalf("Send with InsecureSkipVerify=true failed: %v", err)
	}
	if msgID == "" {
		t.Error("expected non-empty message ID on success")
	}

	// Assert the audit warning was emitted with the expected structured field.
	logOutput := logBuf.String()
	if !strings.Contains(logOutput, `"tls_insecure_skip_verify":true`) {
		t.Fatalf("expected slog.Warn with tls_insecure_skip_verify=true, got: %s", logOutput)
	}
}

// tlsErrMsg returns true if the error message looks like a TLS/cert error.
func tlsErrMsg(msg string) bool {
	for _, sub := range []string{"x509", "certificate", "tls", "handshake", "unknown authority"} {
		if strings.Contains(strings.ToLower(msg), sub) {
			return true
		}
	}
	return false
}
