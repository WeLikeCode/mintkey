// Package smtp provides the Email Proxy's outbound SMTP client.
//
// Design decisions (ADR-0024, design.md §"SMTP semantics"):
//   - Per-operation connect: no connection pool. Each Send() dials fresh.
//     Rationale: send latency is dominated by TLS handshake at scale; pooling
//     would complicate lifetime management and is deferred to a later chunk.
//   - TLS enforced: STARTTLS or implicit TLS (port 465). Plain connections
//     are rejected unless explicitly opted-in for test/internal use.
//   - Auth modes: PLAIN (password / app-password), XOAUTH2 (OAuth2 access token).
//   - MIME construction via stdlib net/mail + mime/multipart.
//   - All header values pass through internal/security.SanitizeHeader before write.
//   - CRLF injection (NFR-19) rejected at the MIME-build layer.
package smtp

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/tls"
	"encoding/base64"
	"fmt"
	"log/slog"
	"mime"
	"mime/multipart"
	"mime/quotedprintable"
	"net"
	"net/smtp"
	"net/textproto"
	"strconv"
	"strings"
	"time"

	"github.com/mintkey/mintkey/services/email-proxy/internal/security"
)

// AuthMode identifies the SMTP authentication mechanism.
type AuthMode string

const (
	// AuthModePLAIN uses the PLAIN SASL mechanism (username + password or app-password).
	AuthModePLAIN AuthMode = "PLAIN"
	// AuthModeXOAUTH2 uses the XOAUTH2 SASL mechanism (OAuth2 access token).
	AuthModeXOAUTH2 AuthMode = "XOAUTH2"
)

// Credential carries the SMTP authentication material for a single send.
// The caller is responsible for zeroing sensitive fields after Send returns.
type Credential struct {
	// AuthMode selects the SASL mechanism. Empty means no auth (test/relay).
	AuthMode AuthMode

	// Username is the SMTP login identity (PLAIN auth).
	// Defaults to the From address if empty.
	Username string

	// Password is the plaintext password or app-password (PLAIN auth).
	Password string

	// AccessToken is the OAuth2 access token (XOAUTH2 auth).
	AccessToken string

	// InsecureSkipVerify disables TLS certificate verification for this send
	// operation. Overrides the client-level Config.InsecureSkipVerify when set
	// on the Credential. Used when the per-service flag from vault is true (ADR-0024).
	// A structured warning log is emitted per connection.
	InsecureSkipVerify bool
}

// Attachment is a single file attachment to include in the outgoing message.
type Attachment struct {
	// Filename is the display filename. Header-injection characters are rejected.
	Filename string
	// ContentType is the MIME content-type, e.g. "application/octet-stream".
	ContentType string
	// Content is the raw (unencoded) attachment bytes.
	Content []byte
}

// EmailSendRequest holds all inputs for a single outbound email.
type EmailSendRequest struct {
	// From is the envelope sender address. Required.
	From string
	// To is the list of primary recipients. At least one required.
	To []string
	// Cc is the list of CC recipients (may be empty).
	Cc []string
	// Bcc is the list of BCC recipients (not exposed in headers).
	Bcc []string
	// Subject is the email subject line.
	Subject string
	// Body is the plain-text message body. May be empty.
	Body string
	// BodyHTML is an optional HTML part (produces multipart/alternative if set).
	BodyHTML string
	// ReplyToMessageID is the Message-ID of the message being replied to.
	// Sets In-Reply-To and References headers when non-empty.
	ReplyToMessageID string
	// Attachments is the list of file attachments. May be empty.
	Attachments []Attachment
}

// Config carries boot-time transport configuration for the Client.
// Host, Port, UseTLS, UseSTARTTLS are intentionally omitted here; they are
// resolved per-send via DialTarget so each send uses the correct per-service
// SMTP routing from the credential response (ADR-0024 Phase 2).
type Config struct {
	// TLSConf overrides the TLS configuration used for dial/STARTTLS.
	// If nil, uses the system default with cert verification enabled.
	// Per-send InsecureSkipVerify is applied on top of this via DialTarget.
	TLSConf *tls.Config
	// DialTimeout is the per-connection dial timeout. Defaults to 30s.
	DialTimeout time.Duration
	// SendTimeout is the per-message send timeout. Defaults to 60s.
	SendTimeout time.Duration
}

// DialTarget carries per-send SMTP connection parameters resolved from the
// per-service email_services row. Constructed fresh on every HandleSendMessage
// call from the vault credential response (ADR-0024 Phase 2).
//
// Port semantics:
//   - 465 → implicit TLS (SMTPS, UseTLS=true, UseSTARTTLS=false)
//   - 587 → STARTTLS upgrade (UseTLS=false, UseSTARTTLS=true)
//   - 25  → rejected (cleartext SMTP; no opt-in flag exists)
//   - other → STARTTLS heuristic (same as 587)
type DialTarget struct {
	// Host is the SMTP server hostname. Required.
	Host string
	// Port is the SMTP server port. Required (must not be 0 or 25).
	Port int
	// InsecureSkipVerify disables TLS certificate verification for this send.
	// Mirrors the per-service tls_insecure_skip_verify vault field (ADR-0024).
	InsecureSkipVerify bool
}

// Client is the SMTP send client. All state is in Config; Clients are safe
// for concurrent use — each call to Send() creates an independent connection.
type Client struct {
	cfg Config
}

// New creates a new Client with the given transport Config.
func New(cfg Config) *Client {
	if cfg.DialTimeout == 0 {
		cfg.DialTimeout = 30 * time.Second
	}
	if cfg.SendTimeout == 0 {
		cfg.SendTimeout = 60 * time.Second
	}
	return &Client{cfg: cfg}
}

// Send constructs a MIME message and delivers it via SMTP using the
// per-send DialTarget (host, port, TLS mode) resolved from the per-service
// email_services credential row (ADR-0024 Phase 2).
//
// Port semantics applied internally (see DialTarget):
//   - 465 → implicit TLS (SMTPS)
//   - 587 or other → STARTTLS
//   - 25  → rejected (cleartext; no opt-in flag)
//
// It performs:
//  1. Input validation (CRLF injection checks via security.SanitizeHeader).
//  2. MIME message construction (multipart if HTML or attachments present).
//  3. Per-operation TCP/TLS dial using target.Host:target.Port.
//  4. SMTP AUTH (PLAIN or XOAUTH2 depending on cred.AuthMode).
//  5. MAIL FROM / RCPT TO / DATA exchange.
//  6. Returns the Message-ID assigned to the message (generated locally,
//     not parsed from server response since not all servers echo it).
//
// Returns an error for any security boundary violation (CRLF injection,
// TLS failure, auth failure, protocol error, cleartext port 25).
func (c *Client) Send(ctx context.Context, cred Credential, req EmailSendRequest, target DialTarget) (string, error) {
	// -----------------------------------------------------------------------
	// 0. Reject port 25 (cleartext SMTP). No opt-in flag exists.
	// -----------------------------------------------------------------------
	if target.Port == 25 {
		return "", fmt.Errorf("smtp: port 25 (cleartext SMTP) is not permitted; configure smtp_port to 465 (implicit TLS) or 587 (STARTTLS)")
	}

	// -----------------------------------------------------------------------
	// 1. Build and validate the MIME message.
	// -----------------------------------------------------------------------
	raw, msgID, err := buildMessage(req)
	if err != nil {
		return "", fmt.Errorf("smtp: build message: %w", err)
	}

	// -----------------------------------------------------------------------
	// 2. Collect all envelope recipients (To + Cc + Bcc).
	// -----------------------------------------------------------------------
	var envRcpts []string
	for _, group := range [][]string{req.To, req.Cc, req.Bcc} {
		envRcpts = append(envRcpts, group...)
	}
	if len(envRcpts) == 0 {
		return "", fmt.Errorf("smtp: no recipients specified")
	}

	// -----------------------------------------------------------------------
	// 3. Dial.
	// Discriminate TLS mode by port:
	//   465 → implicit TLS (SMTPS, UseTLS=true)
	//   587 or other → STARTTLS (UseSTARTTLS=true)
	// -----------------------------------------------------------------------
	addr := fmt.Sprintf("%s:%d", target.Host, target.Port)
	useTLS := target.Port == 465
	useSTARTTLS := !useTLS

	// Per-credential InsecureSkipVerify merges with per-send DialTarget value.
	// This allows per-service TLS bypass from the vault response (ADR-0024).
	effectiveInsecureSkipVerify := target.InsecureSkipVerify || cred.InsecureSkipVerify

	if effectiveInsecureSkipVerify {
		slog.Warn("smtp: TLS certificate verification DISABLED for connection",
			"host", target.Host,
			"port", strconv.Itoa(target.Port),
			"tls_insecure_skip_verify", true,
		)
	}

	slog.Debug("smtp: dialing",
		"host", target.Host,
		"port", strconv.Itoa(target.Port),
		"use_tls", useTLS,
		"use_starttls", useSTARTTLS,
	)

	dialCtx, dialCancel := context.WithTimeout(ctx, c.cfg.DialTimeout)
	defer dialCancel()

	var conn net.Conn
	if useTLS {
		tlsCfg := c.cfg.TLSConf
		if tlsCfg == nil {
			tlsCfg = &tls.Config{
				ServerName:         target.Host,
				MinVersion:         tls.VersionTLS12,
				InsecureSkipVerify: effectiveInsecureSkipVerify, //nolint:gosec // per-service opt-in, operator-controlled (ADR-0024)
			}
		}
		conn, err = tls.DialWithDialer(
			&net.Dialer{},
			"tcp", addr, tlsCfg,
		)
	} else {
		var d net.Dialer
		conn, err = d.DialContext(dialCtx, "tcp", addr)
	}
	if err != nil {
		return "", fmt.Errorf("smtp: dial %s: %w", addr, err)
	}
	defer conn.Close()

	// -----------------------------------------------------------------------
	// 4. SMTP handshake.
	// -----------------------------------------------------------------------
	sendDeadline := time.Now().Add(c.cfg.SendTimeout)
	if err := conn.SetDeadline(sendDeadline); err != nil {
		return "", fmt.Errorf("smtp: set deadline: %w", err)
	}

	sc, err := smtp.NewClient(conn, target.Host)
	if err != nil {
		return "", fmt.Errorf("smtp: new client: %w", err)
	}
	defer sc.Close()

	if useSTARTTLS {
		tlsCfg := c.cfg.TLSConf
		if tlsCfg == nil {
			tlsCfg = &tls.Config{
				ServerName:         target.Host,
				MinVersion:         tls.VersionTLS12,
				InsecureSkipVerify: effectiveInsecureSkipVerify, //nolint:gosec // per-service opt-in, operator-controlled (ADR-0024)
			}
		}
		if err := sc.StartTLS(tlsCfg); err != nil {
			return "", fmt.Errorf("smtp: STARTTLS: %w", err)
		}
	}

	// -----------------------------------------------------------------------
	// 5. Authentication.
	// -----------------------------------------------------------------------
	if err := authenticate(sc, cred, req.From); err != nil {
		return "", fmt.Errorf("smtp: auth: %w", err)
	}

	// -----------------------------------------------------------------------
	// 6. MAIL FROM / RCPT TO / DATA.
	// -----------------------------------------------------------------------
	if err := sc.Mail(req.From); err != nil {
		return "", fmt.Errorf("smtp: MAIL FROM <%s>: %w", req.From, err)
	}
	for _, rcpt := range envRcpts {
		if err := sc.Rcpt(rcpt); err != nil {
			return "", fmt.Errorf("smtp: RCPT TO <%s>: %w", rcpt, err)
		}
	}

	w, err := sc.Data()
	if err != nil {
		return "", fmt.Errorf("smtp: DATA: %w", err)
	}
	if _, err := w.Write(raw); err != nil {
		return "", fmt.Errorf("smtp: write message: %w", err)
	}
	if err := w.Close(); err != nil {
		return "", fmt.Errorf("smtp: close DATA: %w", err)
	}
	if err := sc.Quit(); err != nil {
		// Non-fatal — message was accepted.
		_ = err
	}

	return msgID, nil
}

// ============================================================================
// MIME construction
// ============================================================================

// buildMessage constructs the RFC 5322 / MIME wire bytes for req.
// Returns the raw message bytes and the Message-ID assigned to it.
func buildMessage(req EmailSendRequest) ([]byte, string, error) {
	// Generate a Message-ID before any validation so we can return it on success.
	msgID, err := generateMessageID()
	if err != nil {
		return nil, "", fmt.Errorf("generate message-id: %w", err)
	}

	// Validate and sanitize all user-controlled header values.
	cleanSubject, err := sanitizeHeaderValue("Subject", req.Subject)
	if err != nil {
		return nil, "", err
	}
	cleanFrom, err := sanitizeHeaderValue("From", req.From)
	if err != nil {
		return nil, "", err
	}

	hasHTML := req.BodyHTML != ""
	hasAttachments := len(req.Attachments) > 0

	var buf bytes.Buffer

	// Write top-level RFC 5322 headers.
	writeRFC5322Headers := func(contentType string) error {
		fmt.Fprintf(&buf, "From: %s\r\n", cleanFrom)
		if len(req.To) > 0 {
			toStr, toErr := addressListHeader(req.To)
			if toErr != nil {
				return fmt.Errorf("To: %w", toErr)
			}
			fmt.Fprintf(&buf, "To: %s\r\n", toStr)
		}
		if len(req.Cc) > 0 {
			ccStr, ccErr := addressListHeader(req.Cc)
			if ccErr != nil {
				return fmt.Errorf("Cc: %w", ccErr)
			}
			fmt.Fprintf(&buf, "Cc: %s\r\n", ccStr)
		}
		fmt.Fprintf(&buf, "Subject: %s\r\n", cleanSubject)
		fmt.Fprintf(&buf, "Date: %s\r\n", time.Now().UTC().Format("Mon, 02 Jan 2006 15:04:05 +0000"))
		fmt.Fprintf(&buf, "Message-ID: <%s>\r\n", msgID)
		fmt.Fprintf(&buf, "MIME-Version: 1.0\r\n")
		if req.ReplyToMessageID != "" {
			cleanReplyTo, rErr := sanitizeHeaderValue("In-Reply-To", req.ReplyToMessageID)
			if rErr != nil {
				return rErr
			}
			fmt.Fprintf(&buf, "In-Reply-To: <%s>\r\n", cleanReplyTo)
			fmt.Fprintf(&buf, "References: <%s>\r\n", cleanReplyTo)
		}
		fmt.Fprintf(&buf, "Content-Type: %s\r\n", contentType)
		fmt.Fprintf(&buf, "\r\n")
		return nil
	}

	switch {
	case !hasHTML && !hasAttachments:
		// Simple plain-text message.
		if err := writeRFC5322Headers("text/plain; charset=UTF-8"); err != nil {
			return nil, "", err
		}
		fmt.Fprintf(&buf, "Content-Transfer-Encoding: quoted-printable\r\n")
		fmt.Fprintf(&buf, "\r\n")
		qp := quotedprintable.NewWriter(&buf)
		qp.Write([]byte(req.Body))
		qp.Close()

	case hasHTML && !hasAttachments:
		// multipart/alternative (no attachments).
		var bodyBuf bytes.Buffer
		altW := multipart.NewWriter(&bodyBuf)

		// text/plain part.
		ph := make(textproto.MIMEHeader)
		ph.Set("Content-Type", "text/plain; charset=UTF-8")
		ph.Set("Content-Transfer-Encoding", "quoted-printable")
		pw, _ := altW.CreatePart(ph)
		qp := quotedprintable.NewWriter(pw)
		qp.Write([]byte(req.Body))
		qp.Close()

		// text/html part.
		ph = make(textproto.MIMEHeader)
		ph.Set("Content-Type", "text/html; charset=UTF-8")
		ph.Set("Content-Transfer-Encoding", "quoted-printable")
		pw, _ = altW.CreatePart(ph)
		qp = quotedprintable.NewWriter(pw)
		qp.Write([]byte(req.BodyHTML))
		qp.Close()
		altW.Close()

		ct := fmt.Sprintf("multipart/alternative; boundary=%q", altW.Boundary())
		if err := writeRFC5322Headers(ct); err != nil {
			return nil, "", err
		}
		buf.Write(bodyBuf.Bytes())

	default:
		// multipart/mixed: body (plain or alternative) + attachments.
		var bodyBuf bytes.Buffer
		mixedW := multipart.NewWriter(&bodyBuf)

		// Inner body part.
		if hasHTML {
			var altBuf bytes.Buffer
			altW := multipart.NewWriter(&altBuf)

			ph := make(textproto.MIMEHeader)
			ph.Set("Content-Type", "text/plain; charset=UTF-8")
			ph.Set("Content-Transfer-Encoding", "quoted-printable")
			pw, _ := altW.CreatePart(ph)
			qp := quotedprintable.NewWriter(pw)
			qp.Write([]byte(req.Body))
			qp.Close()

			ph = make(textproto.MIMEHeader)
			ph.Set("Content-Type", "text/html; charset=UTF-8")
			ph.Set("Content-Transfer-Encoding", "quoted-printable")
			pw, _ = altW.CreatePart(ph)
			qp = quotedprintable.NewWriter(pw)
			qp.Write([]byte(req.BodyHTML))
			qp.Close()
			altW.Close()

			altH := make(textproto.MIMEHeader)
			altH.Set("Content-Type", fmt.Sprintf("multipart/alternative; boundary=%q", altW.Boundary()))
			altPart, _ := mixedW.CreatePart(altH)
			altPart.Write(altBuf.Bytes())
		} else {
			ph := make(textproto.MIMEHeader)
			ph.Set("Content-Type", "text/plain; charset=UTF-8")
			ph.Set("Content-Transfer-Encoding", "quoted-printable")
			pw, _ := mixedW.CreatePart(ph)
			qp := quotedprintable.NewWriter(pw)
			qp.Write([]byte(req.Body))
			qp.Close()
		}

		// Attachment parts.
		for _, att := range req.Attachments {
			cleanFilename, attErr := sanitizeHeaderValue("filename", att.Filename)
			if attErr != nil {
				return nil, "", fmt.Errorf("attachment filename: %w", attErr)
			}
			ct := att.ContentType
			if ct == "" {
				ct = "application/octet-stream"
			}
			encodedFilename := mime.QEncoding.Encode("utf-8", cleanFilename)
			ph := make(textproto.MIMEHeader)
			ph.Set("Content-Type", ct)
			ph.Set("Content-Transfer-Encoding", "base64")
			ph.Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, encodedFilename))
			pw, _ := mixedW.CreatePart(ph)
			enc := base64.NewEncoder(base64.StdEncoding, pw)
			enc.Write(att.Content)
			enc.Close()
		}
		mixedW.Close()

		ct := fmt.Sprintf("multipart/mixed; boundary=%q", mixedW.Boundary())
		if err := writeRFC5322Headers(ct); err != nil {
			return nil, "", err
		}
		buf.Write(bodyBuf.Bytes())
	}

	return buf.Bytes(), msgID, nil
}

// ============================================================================
// Authentication
// ============================================================================

// authenticate selects and applies the appropriate SASL auth mechanism.
func authenticate(sc *smtp.Client, cred Credential, fromAddr string) error {
	switch cred.AuthMode {
	case "":
		return nil // no auth
	case AuthModePLAIN:
		user := cred.Username
		if user == "" {
			user = fromAddr
		}
		auth := &plainAuth{identity: "", username: user, password: cred.Password}
		if err := sc.Auth(auth); err != nil {
			return fmt.Errorf("PLAIN auth: %w", err)
		}
	case AuthModeXOAUTH2:
		auth := newXOAUTH2(fromAddr, cred.AccessToken)
		if err := sc.Auth(auth); err != nil {
			return fmt.Errorf("XOAUTH2 auth: %w", err)
		}
	default:
		return fmt.Errorf("unsupported auth mode %q", cred.AuthMode)
	}
	return nil
}

// newXOAUTH2 returns an smtp.Auth implementation for the XOAUTH2 mechanism.
// Wire format: "user=<user>\x01auth=Bearer <token>\x01\x01"
// ref: https://developers.google.com/gmail/imap/xoauth2-protocol
func newXOAUTH2(user, accessToken string) smtp.Auth {
	return &xoauth2Auth{user: user, token: accessToken}
}

type xoauth2Auth struct {
	user  string
	token string
}

func (a *xoauth2Auth) Start(_ *smtp.ServerInfo) (string, []byte, error) {
	payload := fmt.Sprintf("user=%s\x01auth=Bearer %s\x01\x01", a.user, a.token)
	return "XOAUTH2", []byte(payload), nil
}

func (a *xoauth2Auth) Next(_ []byte, more bool) ([]byte, error) {
	if more {
		// Server challenge (error response from Google) — send empty response
		// to terminate the exchange gracefully.
		return []byte{}, nil
	}
	return nil, nil
}

// plainAuth implements smtp.Auth for the PLAIN mechanism without the stdlib's
// host-checking restriction (which would break against test servers and some
// production relays that report a different hostname in the greeting).
// The TLS layer provides transport security; we rely on TLS cert verification
// to establish server identity rather than a name-match on the SMTP greeting.
type plainAuth struct {
	identity string
	username string
	password string
}

func (a *plainAuth) Start(_ *smtp.ServerInfo) (string, []byte, error) {
	payload := a.identity + "\x00" + a.username + "\x00" + a.password
	return "PLAIN", []byte(payload), nil
}

func (a *plainAuth) Next(_ []byte, more bool) ([]byte, error) {
	if more {
		return nil, fmt.Errorf("smtp: PLAIN auth: unexpected server challenge")
	}
	return nil, nil
}

// ============================================================================
// Helpers
// ============================================================================

// sanitizeHeaderValue calls security.SanitizeHeader and returns the clean value.
func sanitizeHeaderValue(name, value string) (string, error) {
	_, clean, err := security.SanitizeHeader(name, value)
	if err != nil {
		return "", fmt.Errorf("smtp: header %q: %w", name, err)
	}
	return clean, nil
}

// addressListHeader joins a list of addresses into a comma-separated header
// value, validating each one through security.ParseAddressList first.
func addressListHeader(addrs []string) (string, error) {
	validated := make([]string, 0, len(addrs))
	for _, addr := range addrs {
		parsed, err := security.ParseAddressList(addr)
		if err != nil {
			return "", fmt.Errorf("invalid address %q: %w", addr, err)
		}
		for _, a := range parsed {
			validated = append(validated, a.String())
		}
	}
	return strings.Join(validated, ", "), nil
}

// generateMessageID generates a RFC 5322 Message-ID value (without angle brackets).
// Format: <timestamp.random@mintkey.email-proxy>
func generateMessageID() (string, error) {
	randBytes := make([]byte, 12)
	if _, err := rand.Read(randBytes); err != nil {
		return "", fmt.Errorf("generate message-id: %w", err)
	}
	ts := time.Now().UTC().UnixNano()
	return fmt.Sprintf("%d.%s@mintkey.email-proxy", ts, base64.RawURLEncoding.EncodeToString(randBytes)), nil
}
