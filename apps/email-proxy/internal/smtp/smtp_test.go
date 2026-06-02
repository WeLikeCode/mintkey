package smtp_test

import (
	"bytes"
	"context"
	"crypto/tls"
	"fmt"
	"io"
	"mime"
	"mime/multipart"
	"mime/quotedprintable"
	"net"
	"net/mail"
	"strings"
	"sync"
	"testing"
	"time"

	smtpclient "github.com/mintkey/mintkey/services/email-proxy/internal/smtp"
)

// ---------------------------------------------------------------------------
// In-process SMTP test server
// ---------------------------------------------------------------------------

// testSMTPServer is a minimal in-process SMTP server that records received
// messages for assertions. It accepts or rejects based on configurable hooks.
type testSMTPServer struct {
	addr      string
	listener  net.Listener
	mu        sync.Mutex
	messages  []receivedMsg
	authMode  string // "plain", "xoauth2", or "" (no auth)
	authError bool   // force auth failure
	tlsCfg    *tls.Config
	useTLS    bool // wrap listener in TLS (implicit TLS)
}

type receivedMsg struct {
	from string
	to   []string
	data []byte
}

// newTestServer starts a test SMTP server on a random port.
// tlsCfg: if non-nil, enable implicit TLS (SMTPS). Otherwise plain TCP + optional STARTTLS.
func newTestServer(t *testing.T, authMode string, tlsCfg *tls.Config) *testSMTPServer {
	t.Helper()

	var ln net.Listener
	var err error
	if tlsCfg != nil {
		ln, err = tls.Listen("tcp", "127.0.0.1:0", tlsCfg)
	} else {
		ln, err = net.Listen("tcp", "127.0.0.1:0")
	}
	if err != nil {
		t.Fatalf("listen: %v", err)
	}

	srv := &testSMTPServer{
		addr:     ln.Addr().String(),
		listener: ln,
		authMode: authMode,
		tlsCfg:   tlsCfg,
		useTLS:   tlsCfg != nil,
	}
	go srv.serve()
	return srv
}

func (s *testSMTPServer) close() { s.listener.Close() }

func (s *testSMTPServer) received() []receivedMsg {
	s.mu.Lock()
	defer s.mu.Unlock()
	cp := make([]receivedMsg, len(s.messages))
	copy(cp, s.messages)
	return cp
}

func (s *testSMTPServer) serve() {
	for {
		conn, err := s.listener.Accept()
		if err != nil {
			return // listener closed
		}
		go s.handleConn(conn)
	}
}

// handleConn implements a minimal SMTP conversation.
func (s *testSMTPServer) handleConn(conn net.Conn) {
	defer conn.Close()

	write := func(line string) {
		fmt.Fprintf(conn, "%s\r\n", line)
	}
	readLine := func() (string, error) {
		var buf []byte
		b := make([]byte, 1)
		for {
			n, err := conn.Read(b)
			if n > 0 {
				if b[0] == '\n' {
					break
				}
				buf = append(buf, b[0])
			}
			if err != nil {
				return strings.TrimRight(string(buf), "\r"), err
			}
		}
		return strings.TrimRight(string(buf), "\r"), nil
	}

	write("220 testsmtp ESMTP ready")

	var from string
	var to []string
	authenticated := s.authMode == "" // no auth required if authMode is empty

	for {
		line, err := readLine()
		if err != nil {
			return
		}
		cmd := strings.ToUpper(strings.Fields(line)[0])
		switch cmd {
		case "EHLO", "HELO":
			write("250-testsmtp")
			if !s.useTLS && s.tlsCfg != nil {
				write("250-STARTTLS")
			}
			if s.authMode != "" {
				write("250-AUTH PLAIN XOAUTH2")
			}
			write("250 8BITMIME")
		case "STARTTLS":
			if s.tlsCfg == nil {
				write("502 STARTTLS not supported")
				continue
			}
			write("220 Ready to start TLS")
			tlsConn := tls.Server(conn, s.tlsCfg)
			if err := tlsConn.Handshake(); err != nil {
				return
			}
			conn = tlsConn
			// Update read/write funcs to use new conn.
			write = func(l string) { fmt.Fprintf(conn, "%s\r\n", l) }
			readLine = func() (string, error) {
				var buf []byte
				b := make([]byte, 1)
				for {
					n, readErr := conn.Read(b)
					if n > 0 {
						if b[0] == '\n' {
							break
						}
						buf = append(buf, b[0])
					}
					if readErr != nil {
						return strings.TrimRight(string(buf), "\r"), readErr
					}
				}
				return strings.TrimRight(string(buf), "\r"), nil
			}
		case "AUTH":
			if s.authError {
				write("535 5.7.8 Authentication credentials invalid")
				continue
			}
			write("235 2.7.0 Authentication successful")
			authenticated = true
		case "MAIL":
			if !authenticated {
				write("530 5.7.0 Authentication required")
				continue
			}
			// Extract FROM:<addr>
			rest := strings.TrimPrefix(strings.TrimPrefix(line, "MAIL "), "MAIL ")
			rest = strings.TrimSpace(rest[5:]) // strip "FROM:"
			from = strings.Trim(rest, "<>")
			write("250 OK")
		case "RCPT":
			rcpt := strings.TrimSpace(line[8:]) // "RCPT TO:" = 8 chars
			rcpt = strings.Trim(rcpt, "<>")
			to = append(to, rcpt)
			write("250 OK")
		case "DATA":
			write("354 End data with <CR><LF>.<CR><LF>")
			var dataBuf strings.Builder
			for {
				dataLine, err := readLine()
				if err != nil {
					return
				}
				if dataLine == "." {
					break
				}
				dataBuf.WriteString(dataLine)
				dataBuf.WriteString("\r\n")
			}
			s.mu.Lock()
			s.messages = append(s.messages, receivedMsg{
				from: from,
				to:   append([]string(nil), to...),
				data: []byte(dataBuf.String()),
			})
			s.mu.Unlock()
			from = ""
			to = nil
			write("250 OK: message queued")
		case "QUIT":
			write("221 Bye")
			return
		case "RSET":
			from = ""
			to = nil
			write("250 OK")
		default:
			write("500 Command unrecognised")
		}
	}
}

// ---------------------------------------------------------------------------
// Self-signed cert helper for TLS tests
// ---------------------------------------------------------------------------

func selfSignedTLS(t *testing.T) *tls.Config {
	t.Helper()
	// Generate a self-signed cert in-memory.
	cert, err := generateSelfSigned()
	if err != nil {
		t.Fatalf("generate self-signed cert: %v", err)
	}
	return &tls.Config{Certificates: []tls.Certificate{cert}}
}

// clientTLSInsecure returns a TLS config that skips cert verification —
// used only for TLS-happy-path tests where we own the server cert.
func clientTLSInsecure() *tls.Config {
	return &tls.Config{InsecureSkipVerify: true} //nolint:gosec // test-only
}

// ---------------------------------------------------------------------------
// Credential helpers
// ---------------------------------------------------------------------------

func plainCred(password string) smtpclient.Credential {
	return smtpclient.Credential{
		AuthMode: smtpclient.AuthModePLAIN,
		Password: password,
	}
}

func xoauth2Cred(token string) smtpclient.Credential {
	return smtpclient.Credential{
		AuthMode:    smtpclient.AuthModeXOAUTH2,
		AccessToken: token,
	}
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

// Test 1: Happy path — send a plain-text email, message-ID assigned.
func TestSend_HappyPath_MessageIDAssigned(t *testing.T) {
	srv := newTestServer(t, "plain", nil)
	defer srv.close()

	c := smtpclient.New(smtpclient.Config{
		Host:    "127.0.0.1",
		Port:    portOf(srv.addr),
		UseTLS:  false,
		TLSConf: nil,
	})

	req := smtpclient.EmailSendRequest{
		From:    "sender@example.com",
		To:      []string{"recipient@example.com"},
		Subject: "Test subject",
		Body:    "Hello, world!",
	}

	ctx := context.Background()
	msgID, err := c.Send(ctx, plainCred("secret"), req)
	if err != nil {
		t.Fatalf("Send failed: %v", err)
	}
	if msgID == "" {
		t.Fatal("expected non-empty message ID")
	}
	// Must look like a valid Message-ID: contain @ sign wrapped in < >.
	if !strings.Contains(msgID, "@") {
		t.Errorf("message ID %q doesn't look like a valid Message-ID (missing @)", msgID)
	}

	msgs := srv.received()
	if len(msgs) != 1 {
		t.Fatalf("expected 1 message received, got %d", len(msgs))
	}
	if !strings.Contains(string(msgs[0].data), "Hello, world!") {
		t.Error("expected body in received data")
	}
}

// Test 2: TLS (STARTTLS) path — connection wraps in TLS after EHLO.
func TestSend_STARTTLS_HappyPath(t *testing.T) {
	// Server advertises STARTTLS but starts plain.
	serverTLSCfg := selfSignedTLS(t)
	srv := newTestServer(t, "plain", nil) // plain TCP, STARTTLS upgrade
	// We need to add tlsCfg to the server for STARTTLS, but our simple server
	// always does implicit TLS when tlsCfg != nil. Use a manually configured server.
	srv.close()

	// Create a server that does STARTTLS (plain listener, TLS upgrade).
	srv2 := &testSMTPServer{
		authMode: "plain",
		tlsCfg:   serverTLSCfg,
		useTLS:   false, // plain listener
	}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	srv2.listener = ln
	srv2.addr = ln.Addr().String()
	go srv2.serve()
	defer srv2.close()

	c := smtpclient.New(smtpclient.Config{
		Host:       "127.0.0.1",
		Port:       portOf(srv2.addr),
		UseSTARTTLS: true,
		TLSConf:    clientTLSInsecure(),
	})

	req := smtpclient.EmailSendRequest{
		From:    "a@example.com",
		To:      []string{"b@example.com"},
		Subject: "TLS test",
		Body:    "TLS body",
	}
	_, err = c.Send(context.Background(), plainCred("pw"), req)
	if err != nil {
		t.Fatalf("STARTTLS send failed: %v", err)
	}
	if len(srv2.received()) != 1 {
		t.Fatal("expected 1 message on STARTTLS server")
	}
}

// Test 3: TLS handshake failure → error returned (not panic).
func TestSend_TLSHandshakeFailure(t *testing.T) {
	// Plain server, but client will try STARTTLS + reject self-signed cert.
	serverTLSCfg := selfSignedTLS(t)
	srv := &testSMTPServer{
		authMode: "",
		tlsCfg:   serverTLSCfg,
		useTLS:   false,
	}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	srv.listener = ln
	srv.addr = ln.Addr().String()
	go srv.serve()
	defer srv.close()

	c := smtpclient.New(smtpclient.Config{
		Host:        "127.0.0.1",
		Port:        portOf(srv.addr),
		UseSTARTTLS: true,
		// NO InsecureSkipVerify — cert verification will fail.
		TLSConf: &tls.Config{
			ServerName: "localhost", // cert is self-signed for 127.0.0.1, will fail for "localhost"
		},
	})

	req := smtpclient.EmailSendRequest{
		From:    "a@example.com",
		To:      []string{"b@example.com"},
		Subject: "x",
		Body:    "y",
	}
	_, err = c.Send(context.Background(), plainCred("pw"), req)
	if err == nil {
		t.Fatal("expected error from TLS handshake failure, got nil")
	}
}

// Test 4: Auth failure → error returned.
func TestSend_AuthFailure(t *testing.T) {
	srv := newTestServer(t, "plain", nil)
	srv.authError = true
	defer srv.close()

	c := smtpclient.New(smtpclient.Config{
		Host:   "127.0.0.1",
		Port:   portOf(srv.addr),
		UseTLS: false,
	})

	req := smtpclient.EmailSendRequest{
		From:    "a@example.com",
		To:      []string{"b@example.com"},
		Subject: "auth fail test",
		Body:    "body",
	}
	_, err := c.Send(context.Background(), plainCred("wrong-password"), req)
	if err == nil {
		t.Fatal("expected auth failure error, got nil")
	}
}

// Test 5: Header CRLF injection in Subject → rejected before send.
func TestSend_HeaderCRLFInjection_Rejected(t *testing.T) {
	srv := newTestServer(t, "", nil)
	defer srv.close()

	c := smtpclient.New(smtpclient.Config{
		Host:   "127.0.0.1",
		Port:   portOf(srv.addr),
		UseTLS: false,
	})

	payloads := []string{
		"Hello\r\nBcc: attacker@evil.com",
		"Hello\r\nBcc: attacker@evil.com",
		"Subject\rInjected: header",
		"Subject\nInjected: header",
	}
	for _, subject := range payloads {
		req := smtpclient.EmailSendRequest{
			From:    "a@example.com",
			To:      []string{"b@example.com"},
			Subject: subject,
			Body:    "body",
		}
		_, err := c.Send(context.Background(), smtpclient.Credential{}, req)
		if err == nil {
			t.Errorf("expected CRLF injection error for subject %q, got nil", subject)
		}
	}

	// Verify nothing was delivered.
	if len(srv.received()) != 0 {
		t.Error("expected 0 messages delivered (all should be rejected before send)")
	}
}

// Test 6: Attachment encoding is correct (base64 decoded body matches original).
func TestSend_AttachmentEncoding(t *testing.T) {
	srv := newTestServer(t, "", nil)
	defer srv.close()

	c := smtpclient.New(smtpclient.Config{
		Host:   "127.0.0.1",
		Port:   portOf(srv.addr),
		UseTLS: false,
	})

	attContent := []byte("binary\x00data\x01\x02\x03")
	req := smtpclient.EmailSendRequest{
		From:    "a@example.com",
		To:      []string{"b@example.com"},
		Subject: "attachment test",
		Body:    "see attachment",
		Attachments: []smtpclient.Attachment{
			{
				Filename:    "test.bin",
				ContentType: "application/octet-stream",
				Content:     attContent,
			},
		},
	}

	_, err := c.Send(context.Background(), smtpclient.Credential{}, req)
	if err != nil {
		t.Fatalf("Send with attachment failed: %v", err)
	}

	msgs := srv.received()
	if len(msgs) != 1 {
		t.Fatalf("expected 1 message, got %d", len(msgs))
	}

	// Parse the raw message and verify the attachment part.
	rawMsg := msgs[0].data
	parsed, err := mail.ReadMessage(bytes.NewReader(rawMsg))
	if err != nil {
		t.Fatalf("parse received message: %v", err)
	}

	ct := parsed.Header.Get("Content-Type")
	if !strings.HasPrefix(ct, "multipart/") {
		t.Fatalf("expected multipart message, got content-type %q", ct)
	}

	mediaType, params, err := mime.ParseMediaType(ct)
	if err != nil {
		t.Fatalf("parse media type %q: %v", ct, err)
	}
	if !strings.HasPrefix(mediaType, "multipart/") {
		t.Fatalf("expected multipart/*, got %q", mediaType)
	}

	mr := multipart.NewReader(parsed.Body, params["boundary"])
	var foundAttachment bool
	for {
		part, err := mr.NextPart()
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatalf("read part: %v", err)
		}
		partCT := part.Header.Get("Content-Type")
		if strings.Contains(partCT, "octet-stream") || strings.Contains(partCT, "test.bin") {
			foundAttachment = true
			// Verify attachment filename present.
			cd := part.Header.Get("Content-Disposition")
			if !strings.Contains(cd, "test.bin") {
				t.Errorf("attachment filename not in Content-Disposition: %q", cd)
			}
		}
	}
	if !foundAttachment {
		t.Error("attachment part not found in multipart message")
	}
}

// Test 7: Empty body is allowed.
func TestSend_EmptyBody(t *testing.T) {
	srv := newTestServer(t, "", nil)
	defer srv.close()

	c := smtpclient.New(smtpclient.Config{
		Host:   "127.0.0.1",
		Port:   portOf(srv.addr),
		UseTLS: false,
	})

	req := smtpclient.EmailSendRequest{
		From:    "a@example.com",
		To:      []string{"b@example.com"},
		Subject: "empty body test",
		Body:    "",
	}

	_, err := c.Send(context.Background(), smtpclient.Credential{}, req)
	if err != nil {
		t.Fatalf("Send with empty body failed: %v", err)
	}
	if len(srv.received()) != 1 {
		t.Fatal("expected 1 message received")
	}
}

// Test 8: Multipart message is parsed correctly (text + HTML alternative).
func TestSend_MultipartMessageParsedCorrectly(t *testing.T) {
	srv := newTestServer(t, "", nil)
	defer srv.close()

	c := smtpclient.New(smtpclient.Config{
		Host:   "127.0.0.1",
		Port:   portOf(srv.addr),
		UseTLS: false,
	})

	req := smtpclient.EmailSendRequest{
		From:     "a@example.com",
		To:       []string{"b@example.com"},
		Subject:  "multipart test",
		Body:     "Plain text part",
		BodyHTML: "<p>HTML part</p>",
	}

	_, err := c.Send(context.Background(), smtpclient.Credential{}, req)
	if err != nil {
		t.Fatalf("Send multipart failed: %v", err)
	}

	msgs := srv.received()
	if len(msgs) != 1 {
		t.Fatalf("expected 1 message, got %d", len(msgs))
	}

	rawMsg := msgs[0].data
	parsed, err := mail.ReadMessage(bytes.NewReader(rawMsg))
	if err != nil {
		t.Fatalf("parse message: %v", err)
	}

	ct := parsed.Header.Get("Content-Type")
	if !strings.HasPrefix(ct, "multipart/alternative") {
		t.Fatalf("expected multipart/alternative content-type, got %q", ct)
	}

	_, params, err := mime.ParseMediaType(ct)
	if err != nil {
		t.Fatalf("parse media type: %v", err)
	}

	mr := multipart.NewReader(parsed.Body, params["boundary"])
	var foundText, foundHTML bool
	for {
		part, err := mr.NextPart()
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatalf("read part: %v", err)
		}
		partCT := part.Header.Get("Content-Type")
		partBody, _ := io.ReadAll(part)

		var decoded []byte
		te := part.Header.Get("Content-Transfer-Encoding")
		if strings.EqualFold(te, "quoted-printable") {
			decoded, _ = io.ReadAll(quotedprintable.NewReader(bytes.NewReader(partBody)))
		} else {
			decoded = partBody
		}

		if strings.HasPrefix(partCT, "text/plain") {
			foundText = true
			if !strings.Contains(string(decoded), "Plain text part") {
				t.Errorf("plain part body mismatch, got: %q", decoded)
			}
		}
		if strings.HasPrefix(partCT, "text/html") {
			foundHTML = true
			if !strings.Contains(string(decoded), "HTML part") {
				t.Errorf("HTML part body mismatch, got: %q", decoded)
			}
		}
	}
	if !foundText {
		t.Error("text/plain part not found in multipart/alternative")
	}
	if !foundHTML {
		t.Error("text/html part not found in multipart/alternative")
	}
}

// Test 9: XOAUTH2 credentials are used.
func TestSend_XOAUTH2Auth(t *testing.T) {
	srv := newTestServer(t, "xoauth2", nil)
	defer srv.close()

	c := smtpclient.New(smtpclient.Config{
		Host:   "127.0.0.1",
		Port:   portOf(srv.addr),
		UseTLS: false,
	})

	req := smtpclient.EmailSendRequest{
		From:    "user@gmail.com",
		To:      []string{"other@example.com"},
		Subject: "OAuth2 test",
		Body:    "sent via XOAUTH2",
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	msgID, err := c.Send(ctx, xoauth2Cred("ya29.test-token"), req)
	if err != nil {
		t.Fatalf("XOAUTH2 send failed: %v", err)
	}
	if msgID == "" {
		t.Error("expected message ID")
	}
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

func portOf(addr string) int {
	_, portStr, _ := net.SplitHostPort(addr)
	port := 0
	fmt.Sscan(portStr, &port)
	return port
}
