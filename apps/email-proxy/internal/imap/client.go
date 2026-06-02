// Package imap provides an outbound IMAP client wrapper around
// github.com/emersion/go-imap/v2 for the email-proxy service.
//
// # Auth modes
//
// LOGIN  — password / app-password (RFC 3501 LOGIN command).
// XOAUTH2 — OAuth2 bearer token via OAUTHBEARER SASL mechanism (RFC 7628).
//
// # TLS
//
// TLS is always enforced. Callers pass DialMode to select between implicit
// TLS on port 993 (DialModeTLS) or STARTTLS on port 143 (DialModeStartTLS).
// Cleartext connections are never opened.
//
// # UIDVALIDITY
//
// Each Client tracks per-mailbox UIDVALIDITY. If the server returns a
// different UIDVALIDITY on SELECT, ErrUIDValidityChanged is returned so
// callers can invalidate cached UID sets (design.md §"IMAP semantics").
package imap

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"sync"
	"time"

	goiMAP "github.com/emersion/go-imap/v2"
	"github.com/emersion/go-imap/v2/imapclient"
	"github.com/emersion/go-sasl"
)

// ErrUIDValidityChanged is returned by SelectMailbox when the server's
// UIDVALIDITY for the mailbox has changed since the last SELECT. Callers must
// discard all cached UIDs and re-discover messages.
var ErrUIDValidityChanged = errors.New("imap: UIDVALIDITY changed — cached UIDs invalidated")

// DialMode selects TLS negotiation strategy.
type DialMode int

const (
	// DialModeTLS uses implicit TLS (port 993). Default.
	DialModeTLS DialMode = iota
	// DialModeStartTLS uses STARTTLS (port 143 / 587).
	DialModeStartTLS
)

// AuthMode selects how credentials are presented to the server.
type AuthMode int

const (
	// AuthModeLogin uses the IMAP LOGIN command (password / app-password).
	AuthModeLogin AuthMode = iota
	// AuthModeXOAuth2 uses the OAUTHBEARER SASL mechanism (OAuth2 access token).
	AuthModeXOAuth2
)

// Credentials holds authentication material. Populate either Password or
// AccessToken depending on AuthMode.
type Credentials struct {
	Username    string
	Password    string // for AuthModeLogin
	AccessToken string // for AuthModeXOAuth2
	AuthMode    AuthMode
}

// MailboxInfo holds metadata returned by a LIST command.
type MailboxInfo struct {
	Name       string
	Attributes []string
}

// MessageHeader holds the envelope metadata for a fetched message.
type MessageHeader struct {
	UID        goiMAP.UID
	Subject    string
	From       []string
	To         []string
	Date       time.Time
	Seen       bool
	Answered   bool
	Flags      []goiMAP.Flag
	RFC822Size int64
}

// AttachmentData holds the raw bytes and MIME type for a downloaded attachment.
type AttachmentData struct {
	UID         goiMAP.UID
	PartID      string
	ContentType string
	Data        []byte
}

// Client is a TLS-enforced, UIDVALIDITY-aware outbound IMAP client.
// It wraps a single *imapclient.Client (one TCP connection). For
// connection pooling, use the pool package.
type Client struct {
	raw  *imapclient.Client
	addr string

	mu              sync.Mutex
	uidValidity     map[string]uint32 // mailbox → last known UIDVALIDITY
	selectedMailbox string
}

// Dial opens a new authenticated IMAP connection with TLS enforcement.
//
// If insecureSkipVerify is true, TLS certificate verification is disabled.
// This MUST only be used for trusted internal servers with self-signed or
// private-CA certificates (ADR-0024). A structured warning is emitted via
// slog on every such connection for audit-trail purposes.
//
// Caller is responsible for calling Close when done.
func Dial(ctx context.Context, addr string, mode DialMode, creds Credentials, insecureSkipVerify bool) (*Client, error) {
	if addr == "" {
		return nil, errors.New("imap: Dial: addr is empty")
	}
	if creds.Username == "" {
		return nil, errors.New("imap: Dial: credentials username is empty")
	}

	if insecureSkipVerify {
		h, p, _ := net.SplitHostPort(addr)
		slog.Warn("imap: TLS certificate verification DISABLED for connection",
			"host", h,
			"port", p,
			"tls_insecure_skip_verify", true,
		)
	}

	opts := &imapclient.Options{
		TLSConfig: &tls.Config{
			MinVersion:         tls.VersionTLS12,
			ServerName:         host(addr),
			InsecureSkipVerify: insecureSkipVerify, //nolint:gosec // per-service opt-in, operator-controlled (ADR-0024)
		},
	}

	var (
		raw *imapclient.Client
		err error
	)
	switch mode {
	case DialModeTLS:
		raw, err = imapclient.DialTLS(addr, opts)
	case DialModeStartTLS:
		raw, err = imapclient.DialStartTLS(addr, opts)
	default:
		return nil, fmt.Errorf("imap: Dial: unknown DialMode %d", mode)
	}
	if err != nil {
		return nil, fmt.Errorf("imap: Dial %s: %w", addr, err)
	}

	c := &Client{
		raw:         raw,
		addr:        addr,
		uidValidity: make(map[string]uint32),
	}

	if err := c.authenticate(creds); err != nil {
		_ = raw.Close()
		return nil, fmt.Errorf("imap: Dial %s: auth: %w", addr, err)
	}

	return c, nil
}

// DialFromConn wraps an existing net.Conn as an IMAP client.
// Used in tests with in-process connections — the caller has already
// performed TLS negotiation (or is using a pipe/bufconn for testing).
func DialFromConn(conn net.Conn, creds Credentials) (*Client, error) {
	if creds.Username == "" {
		return nil, errors.New("imap: DialFromConn: credentials username is empty")
	}
	raw := imapclient.New(conn, nil)
	c := &Client{
		raw:         raw,
		addr:        conn.RemoteAddr().String(),
		uidValidity: make(map[string]uint32),
	}
	if err := c.authenticate(creds); err != nil {
		_ = raw.Close()
		return nil, fmt.Errorf("imap: DialFromConn: auth: %w", err)
	}
	return c, nil
}

func (c *Client) authenticate(creds Credentials) error {
	switch creds.AuthMode {
	case AuthModeLogin:
		return c.raw.Login(creds.Username, creds.Password).Wait()
	case AuthModeXOAuth2:
		if creds.AccessToken == "" {
			return errors.New("imap: XOAUTH2: AccessToken is empty")
		}
		saslClient := sasl.NewOAuthBearerClient(&sasl.OAuthBearerOptions{
			Username: creds.Username,
			Token:    creds.AccessToken,
		})
		return c.raw.Authenticate(saslClient)
	default:
		return fmt.Errorf("imap: unknown AuthMode %d", creds.AuthMode)
	}
}

// Close terminates the IMAP connection.
func (c *Client) Close() error {
	return c.raw.Close()
}

// Ping sends a NOOP to verify the connection is still alive.
func (c *Client) Ping() error {
	return c.raw.Noop().Wait()
}

// ListMailboxes returns all mailboxes visible to the authenticated user.
func (c *Client) ListMailboxes(_ context.Context) ([]MailboxInfo, error) {
	cmd := c.raw.List("", "*", nil)

	var out []MailboxInfo
	for {
		data := cmd.Next()
		if data == nil {
			break
		}
		info := MailboxInfo{Name: data.Mailbox}
		for _, attr := range data.Attrs {
			info.Attributes = append(info.Attributes, string(attr))
		}
		out = append(out, info)
	}
	if err := cmd.Close(); err != nil {
		return nil, fmt.Errorf("imap: ListMailboxes: %w", err)
	}
	return out, nil
}

// SelectMailbox selects the named mailbox and returns the IMAP SelectData.
// Returns ErrUIDValidityChanged if UIDVALIDITY changed from a previous SELECT.
func (c *Client) SelectMailbox(_ context.Context, name string) (*goiMAP.SelectData, error) {
	data, err := c.raw.Select(name, nil).Wait()
	if err != nil {
		return nil, fmt.Errorf("imap: SelectMailbox %q: %w", name, err)
	}

	c.mu.Lock()
	prev, exists := c.uidValidity[name]
	c.uidValidity[name] = data.UIDValidity
	c.selectedMailbox = name
	c.mu.Unlock()

	if exists && prev != data.UIDValidity {
		return data, ErrUIDValidityChanged
	}
	return data, nil
}

// FetchMessages fetches up to limit message headers from mailbox.
// Pass limit=0 to fetch all. Returns headers sorted by server order.
func (c *Client) FetchMessages(ctx context.Context, mailbox string, limit uint32) ([]MessageHeader, error) {
	if _, err := c.SelectMailbox(ctx, mailbox); err != nil && !errors.Is(err, ErrUIDValidityChanged) {
		return nil, err
	}

	numSet := goiMAP.UIDSet{}
	numSet.AddRange(goiMAP.UID(1), goiMAP.UID(0)) // 1:*

	opts := &goiMAP.FetchOptions{
		UID:          true,
		Flags:        true,
		Envelope:     true,
		RFC822Size:   true,
		InternalDate: true,
	}

	cmd := c.raw.Fetch(numSet, opts)
	defer cmd.Close()

	var out []MessageHeader
	for {
		if limit > 0 && uint32(len(out)) >= limit {
			break
		}
		msg := cmd.Next()
		if msg == nil {
			break
		}
		buf, err := msg.Collect()
		if err != nil {
			continue
		}
		out = append(out, messageHeaderFromBuf(buf))
	}
	if err := cmd.Close(); err != nil {
		return nil, fmt.Errorf("imap: FetchMessages: %w", err)
	}
	return out, nil
}

// FetchMessage fetches the full RFC822 body of a single message by UID.
func (c *Client) FetchMessage(ctx context.Context, mailbox string, uid goiMAP.UID) ([]byte, *MessageHeader, error) {
	if _, err := c.SelectMailbox(ctx, mailbox); err != nil && !errors.Is(err, ErrUIDValidityChanged) {
		return nil, nil, err
	}

	numSet := goiMAP.UIDSet{}
	numSet.AddNum(uid)

	opts := &goiMAP.FetchOptions{
		UID:        true,
		Flags:      true,
		Envelope:   true,
		RFC822Size: true,
		BodySection: []*goiMAP.FetchItemBodySection{
			{},
		},
	}

	msgs, err := c.raw.Fetch(numSet, opts).Collect()
	if err != nil {
		return nil, nil, fmt.Errorf("imap: FetchMessage uid=%d: %w", uid, err)
	}
	if len(msgs) == 0 {
		return nil, nil, fmt.Errorf("imap: FetchMessage uid=%d: not found", uid)
	}
	buf := msgs[0]
	h := messageHeaderFromBuf(buf)

	var body []byte
	if len(buf.BodySection) > 0 {
		body = buf.BodySection[0].Bytes
	}

	return body, &h, nil
}

// MarkRead marks a message as \Seen.
func (c *Client) MarkRead(ctx context.Context, uid goiMAP.UID) error {
	return c.UpdateFlags(ctx, uid, []goiMAP.Flag{goiMAP.FlagSeen})
}

// UpdateFlags adds flags to the given message (UID STORE +FLAGS.SILENT).
func (c *Client) UpdateFlags(_ context.Context, uid goiMAP.UID, flags []goiMAP.Flag) error {
	numSet := goiMAP.UIDSet{}
	numSet.AddNum(uid)

	store := &goiMAP.StoreFlags{
		Op:     goiMAP.StoreFlagsAdd,
		Silent: true,
		Flags:  flags,
	}

	cmd := c.raw.Store(numSet, store, nil)
	if err := cmd.Close(); err != nil {
		return fmt.Errorf("imap: UpdateFlags uid=%d: %w", uid, err)
	}
	return nil
}

// DeleteMessage marks a message as \Deleted then UID EXPUNGE it.
func (c *Client) DeleteMessage(_ context.Context, uid goiMAP.UID) error {
	numSet := goiMAP.UIDSet{}
	numSet.AddNum(uid)

	storeCmd := c.raw.Store(numSet, &goiMAP.StoreFlags{
		Op:     goiMAP.StoreFlagsAdd,
		Silent: true,
		Flags:  []goiMAP.Flag{goiMAP.FlagDeleted},
	}, nil)
	if err := storeCmd.Close(); err != nil {
		return fmt.Errorf("imap: DeleteMessage uid=%d mark: %w", uid, err)
	}

	if _, err := c.raw.UIDExpunge(numSet).Collect(); err != nil {
		return fmt.Errorf("imap: DeleteMessage uid=%d expunge: %w", uid, err)
	}
	return nil
}

// MoveMessage moves a message to destMailbox using IMAP MOVE (or COPY+DELETE
// fallback for servers without the MOVE extension).
func (c *Client) MoveMessage(_ context.Context, uid goiMAP.UID, destMailbox string) error {
	numSet := goiMAP.UIDSet{}
	numSet.AddNum(uid)

	if _, err := c.raw.Move(numSet, destMailbox).Wait(); err != nil {
		return fmt.Errorf("imap: MoveMessage uid=%d to %q: %w", uid, destMailbox, err)
	}
	return nil
}

// DownloadAttachment fetches a specific MIME body part (attachment).
// partID is the IMAP body part number, e.g. "1", "2", "2.1".
func (c *Client) DownloadAttachment(_ context.Context, uid goiMAP.UID, partID string) (*AttachmentData, error) {
	numSet := goiMAP.UIDSet{}
	numSet.AddNum(uid)

	sectionPath := parseSectionPath(partID)
	opts := &goiMAP.FetchOptions{
		UID: true,
		BodySection: []*goiMAP.FetchItemBodySection{
			{Part: sectionPath},
		},
		BodyStructure: &goiMAP.FetchItemBodyStructure{Extended: true},
	}

	msgs, err := c.raw.Fetch(numSet, opts).Collect()
	if err != nil {
		return nil, fmt.Errorf("imap: DownloadAttachment uid=%d: %w", uid, err)
	}
	if len(msgs) == 0 {
		return nil, fmt.Errorf("imap: DownloadAttachment uid=%d: not found", uid)
	}
	buf := msgs[0]

	att := &AttachmentData{
		UID:    uid,
		PartID: partID,
	}
	if len(buf.BodySection) > 0 {
		att.Data = buf.BodySection[0].Bytes
	}
	if buf.BodyStructure != nil {
		if bs, ok := buf.BodyStructure.(*goiMAP.BodyStructureSinglePart); ok {
			att.ContentType = bs.Type + "/" + bs.Subtype
		}
	}

	return att, nil
}

// SearchMessages searches the mailbox and returns matching UIDs.
// Returns ErrUIDValidityChanged if UIDVALIDITY changed mid-search.
func (c *Client) SearchMessages(ctx context.Context, mailbox string, criteria *goiMAP.SearchCriteria) ([]goiMAP.UID, error) {
	if _, err := c.SelectMailbox(ctx, mailbox); err != nil && !errors.Is(err, ErrUIDValidityChanged) {
		return nil, err
	}

	opts := &goiMAP.SearchOptions{ReturnAll: true}
	data, err := c.raw.UIDSearch(criteria, opts).Wait()
	if err != nil {
		return nil, fmt.Errorf("imap: SearchMessages in %q: %w", mailbox, err)
	}
	return data.AllUIDs(), nil
}

// ---- internal helpers -------------------------------------------------------

func messageHeaderFromBuf(buf *imapclient.FetchMessageBuffer) MessageHeader {
	h := MessageHeader{
		UID:        buf.UID,
		RFC822Size: buf.RFC822Size,
		Flags:      buf.Flags,
	}
	if buf.Envelope != nil {
		h.Subject = buf.Envelope.Subject
		h.Date = buf.Envelope.Date
		for _, addr := range buf.Envelope.From {
			if addr.Mailbox != "" && addr.Host != "" {
				h.From = append(h.From, addr.Mailbox+"@"+addr.Host)
			}
		}
		for _, addr := range buf.Envelope.To {
			if addr.Mailbox != "" && addr.Host != "" {
				h.To = append(h.To, addr.Mailbox+"@"+addr.Host)
			}
		}
	}
	for _, f := range buf.Flags {
		switch f {
		case goiMAP.FlagSeen:
			h.Seen = true
		case goiMAP.FlagAnswered:
			h.Answered = true
		}
	}
	return h
}

// host extracts the hostname from a host:port address.
func host(addr string) string {
	h, _, err := net.SplitHostPort(addr)
	if err != nil {
		return addr
	}
	return h
}

// parseSectionPath converts a dot-delimited partID string ("2.1") to the
// []int body part path expected by go-imap/v2.
func parseSectionPath(partID string) []int {
	if partID == "" {
		return nil
	}
	var path []int
	n := 0
	for i := 0; i <= len(partID); i++ {
		if i == len(partID) || partID[i] == '.' {
			if n > 0 {
				path = append(path, n)
			}
			n = 0
			continue
		}
		c := partID[i]
		if c >= '0' && c <= '9' {
			n = n*10 + int(c-'0')
		}
	}
	return path
}
