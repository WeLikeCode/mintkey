// tls_test.go — tests for per-service InsecureSkipVerify flag in imap.Dial (ADR-0024).
//
// Verifies that:
//   - Dial with insecureSkipVerify=false against a self-signed cert returns an
//     x509 certificate verification error.
//   - Dial with insecureSkipVerify=true against the same self-signed cert succeeds.
package imap_test

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"errors"
	"math/big"
	"net"
	"testing"
	"time"

	goiMAP "github.com/emersion/go-imap/v2"
	"github.com/emersion/go-imap/v2/imapserver"
	"github.com/emersion/go-imap/v2/imapserver/imapmemserver"

	imapwrap "github.com/mintkey/mintkey/services/email-proxy/internal/imap"
)

// startTLSIMAPServer starts an IMAP server with TLS using a self-signed cert.
// Returns the address and a cleanup function.
func startTLSIMAPServer(t *testing.T) (addr string, cleanup func()) {
	t.Helper()

	cert, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	tmpl := &x509.Certificate{
		SerialNumber: big.NewInt(42),
		Subject:      pkix.Name{CommonName: "imap-test"},
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(24 * time.Hour),
		IPAddresses:  []net.IP{net.ParseIP("127.0.0.1")},
		KeyUsage:     x509.KeyUsageDigitalSignature | x509.KeyUsageCertSign,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		IsCA:         true,
	}
	certDER, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &cert.PublicKey, cert)
	if err != nil {
		t.Fatalf("create cert: %v", err)
	}
	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: certDER})
	keyDER, err := x509.MarshalECPrivateKey(cert)
	if err != nil {
		t.Fatalf("marshal key: %v", err)
	}
	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: keyDER})

	tlsCert, err := tls.X509KeyPair(certPEM, keyPEM)
	if err != nil {
		t.Fatalf("X509KeyPair: %v", err)
	}
	serverTLSCfg := &tls.Config{
		Certificates: []tls.Certificate{tlsCert},
		MinVersion:   tls.VersionTLS12,
	}

	memSrv := imapmemserver.New()
	user := imapmemserver.NewUser(testUser, testPass)
	if err := user.Create("INBOX", nil); err != nil {
		t.Fatalf("create INBOX: %v", err)
	}
	memSrv.AddUser(user)

	srv := imapserver.New(&imapserver.Options{
		NewSession: func(_ *imapserver.Conn) (imapserver.Session, *imapserver.GreetingData, error) {
			return memSrv.NewSession(), nil, nil
		},
		InsecureAuth: true,
		TLSConfig:    serverTLSCfg,
		Caps: goiMAP.CapSet{
			goiMAP.CapIMAP4rev1: {},
		},
	})

	ln, err := tls.Listen("tcp", "127.0.0.1:0", serverTLSCfg)
	if err != nil {
		t.Fatalf("tls.Listen: %v", err)
	}

	go func() {
		_ = srv.Serve(ln)
	}()

	return ln.Addr().String(), func() { _ = srv.Close() }
}

// TestDial_TLS_InsecureSkipVerify_False_FailsWithX509Error verifies that dialing
// a TLS server with a self-signed cert and insecureSkipVerify=false results in
// an x509 certificate verification error.
func TestDial_TLS_InsecureSkipVerify_False_FailsWithX509Error(t *testing.T) {
	addr, cleanup := startTLSIMAPServer(t)
	defer cleanup()

	creds := imapwrap.Credentials{
		Username: testUser,
		Password: testPass,
		AuthMode: imapwrap.AuthModeLogin,
	}

	ctx := context.Background()
	_, err := imapwrap.Dial(ctx, addr, imapwrap.DialModeTLS, creds, false)
	if err == nil {
		t.Fatal("expected x509 error when InsecureSkipVerify=false, got nil")
	}

	// The error must contain an x509 certificate-related message.
	var certErr *tls.CertificateVerificationError
	isCertErr := errors.As(err, &certErr)
	hasX509 := errors.As(err, new(*x509.UnknownAuthorityError)) ||
		errors.As(err, new(*x509.CertificateInvalidError)) ||
		isCertErr
	if !hasX509 {
		// Some Go versions wrap differently; check the message too.
		errMsg := err.Error()
		if !containsAny(errMsg, "x509", "certificate", "unknown authority", "tls") {
			t.Errorf("expected TLS/x509 error, got: %v", err)
		}
	}
}

// TestDial_TLS_InsecureSkipVerify_True_Succeeds verifies that dialing a TLS server
// with a self-signed cert and insecureSkipVerify=true connects and authenticates
// successfully.
func TestDial_TLS_InsecureSkipVerify_True_Succeeds(t *testing.T) {
	addr, cleanup := startTLSIMAPServer(t)
	defer cleanup()

	creds := imapwrap.Credentials{
		Username: testUser,
		Password: testPass,
		AuthMode: imapwrap.AuthModeLogin,
	}

	ctx := context.Background()
	client, err := imapwrap.Dial(ctx, addr, imapwrap.DialModeTLS, creds, true)
	if err != nil {
		t.Fatalf("Dial with InsecureSkipVerify=true failed: %v", err)
	}
	defer client.Close()

	// Verify the connection works.
	if err := client.Ping(); err != nil {
		t.Errorf("Ping failed after InsecureSkipVerify dial: %v", err)
	}
}

// containsAny returns true if s contains any of the substrings.
func containsAny(s string, subs ...string) bool {
	for _, sub := range subs {
		if len(s) >= len(sub) {
			for i := 0; i <= len(s)-len(sub); i++ {
				if s[i:i+len(sub)] == sub {
					return true
				}
			}
		}
	}
	return false
}
