// Package handlers implements the 9 email-proxy REST endpoint handlers.
//
// Each handler follows this sequence (design.md §"REST API Design"):
//  1. JWT claims are already validated and attached to the request context by
//     the withJWTAuth + withClaims middleware in the parent server package.
//  2. Scope authorisation — claims.Has("<verb>:email").
//  3. Rate-limit check via security.RateLimiter.Allow.
//  4. Credential / connection fetch from the IMAP pool or SMTP client.
//  5. Call the appropriate internal/imap or internal/smtp method.
//  6. Scrub bodies via security.ScrubBodyForLog before any logging/audit emit.
//  7. Emit audit event via the injected AuditEmitter (DI — C-8 plugs in the
//     real auditq.Queue; this package accepts any AuditEmitter implementation).
//  8. Return per openapi.yaml response shapes.
//
// Security (NFR-17 / NFR-19 / NFR-21 / SEC-01..06):
//   - Attachment content is never included in audit payloads.
//   - Message bodies are summarised via ScrubBodyForLog.
//   - refresh_token / access_token / client_secret NEVER appear in payloads.
//   - Rate limit: 60 req/min per (agent_id, service_id).
package handlers

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	goiMAP "github.com/emersion/go-imap/v2"
	"github.com/mintkey/mintkey/services/email-proxy/internal/auth"
	imapwrap "github.com/mintkey/mintkey/services/email-proxy/internal/imap"
	"github.com/mintkey/mintkey/services/email-proxy/internal/oauth2"
	"github.com/mintkey/mintkey/services/email-proxy/internal/permissions"
	"github.com/mintkey/mintkey/services/email-proxy/internal/pool"
	"github.com/mintkey/mintkey/services/email-proxy/internal/security"
	"github.com/mintkey/mintkey/services/email-proxy/internal/smtp"
	"github.com/mintkey/mintkey/services/email-proxy/internal/vault"
)

const (
	// rateLimitPerMin is the default per-(agent, service) request rate limit.
	rateLimitPerMin = 60

	// contextKeyClaimsType is the type used to key Claims in request contexts.
	contextKeyClaimsType = contextKey("claims")

	// defaultMailbox is used when no mailbox query param is provided.
	defaultMailbox = "INBOX"

	// defaultListLimit is used when no limit query param is provided.
	defaultListLimit = 50

	// maxListLimit is the maximum allowed limit for list endpoints.
	maxListLimit = 200

	// maxSearchQueryLen is the maximum allowed search query length.
	maxSearchQueryLen = 500
)

// contextKey is a private type to prevent key collisions on context values.
type contextKey string

// ClaimsContextKey is exported so the server package can set claims on the context.
const ClaimsContextKey = contextKeyClaimsType

// AuditEmitter is the interface for emitting email audit events.
// The production implementation is provided by C-8 (auditq.Queue).
// This package accepts a no-op by default — C-8 wires the real queue in main.go.
//
// TODO(C-8): replace the noop default with the real auditq.Queue wire-up.
type AuditEmitter interface {
	Emit(ctx context.Context, event AuditEvent) error
}

// AuditEvent is a single email-proxy audit event. Payload MUST NOT contain
// refresh_token / access_token / client_secret / raw body / attachment content.
type AuditEvent struct {
	EventType  string // e.g. "email.message.read"
	TenantID   string
	AgentID    string // actor
	ServiceID  string // target
	TargetID   string // message UID, attachment id, etc.
	TargetType string // "email_message", "email_mailbox", etc.
	Payload    map[string]interface{}
}

// noopAuditEmitter discards all events. Used as default until C-8 wires in the
// real auditq.Queue.
type noopAuditEmitter struct{}

func (n *noopAuditEmitter) Emit(_ context.Context, event AuditEvent) error {
	slog.Debug("audit event (noop sink — C-8 TODO)",
		"event_type", event.EventType,
		"tenant_id", event.TenantID,
		"agent_id", event.AgentID,
	)
	return nil
}

// NoopAuditEmitter returns a no-op AuditEmitter for use until C-8 lands.
func NoopAuditEmitter() AuditEmitter {
	return &noopAuditEmitter{}
}

// PoolGetter is the subset of pool.Pool used by handlers.
type PoolGetter interface {
	Get(ctx context.Context, cfg pool.ServiceConfig) (*imapwrap.Client, error)
	Release(cfg pool.ServiceConfig, c *imapwrap.Client)
}

// OAuth2Manager is the subset of oauth2.Manager used by handlers.
type OAuth2Manager interface {
	GetAccessToken(ctx context.Context, tenantID, serviceID string) (string, error)
}

// VaultGetter is the subset of vault.Client used by handlers.
type VaultGetter interface {
	GetCredential(ctx context.Context, tenantID, serviceID string, scheme vault.AuthScheme) (*vault.Credential, error)
}

// SMTPSender is the subset of smtp.Client used by handlers.
// The DialTarget carries per-service SMTP routing resolved from the vault
// credential response (host, port, TLS mode) — ADR-0024 Phase 2.
type SMTPSender interface {
	Send(ctx context.Context, cred smtp.Credential, req smtp.EmailSendRequest, target smtp.DialTarget) (string, error)
}

// PermissionChecker checks whether an (agent_id, email_service_id) pair has a
// row in email_permission_grants for the given tenant.
type PermissionChecker interface {
	CheckGrant(ctx context.Context, tenantID, agentID, emailServiceID string) error
}

// EmailHandlers groups all email endpoint handler functions and their
// shared dependencies.
type EmailHandlers struct {
	pool        PoolGetter
	oauth2Mgr   OAuth2Manager
	vaultClient VaultGetter
	smtpClient  SMTPSender
	rateLimiter *security.RateLimiter
	audit       AuditEmitter
	permChecker PermissionChecker
}

// New creates an EmailHandlers instance.
//
// Parameters:
//   - p: IMAP connection pool (from pool.New)
//   - o: OAuth2 manager (from oauth2.NewManager)
//   - v: vault client (from vault.NewClient)
//   - s: SMTP client (from smtp.New)
//   - rl: rate limiter (from security.NewRateLimiter)
//   - ae: audit emitter (C-8 injects the real queue; pass NoopAuditEmitter() for now)
//   - pc: email permission checker (from permissions.NewChecker); if nil, a deny-all
//     noop is used so callers that don't inject one fail safely.
func New(
	p PoolGetter,
	o OAuth2Manager,
	v VaultGetter,
	s SMTPSender,
	rl *security.RateLimiter,
	ae AuditEmitter,
	pc PermissionChecker,
) *EmailHandlers {
	if ae == nil {
		ae = NoopAuditEmitter()
	}
	if pc == nil {
		pc = &denyAllPermissionChecker{}
	}
	return &EmailHandlers{
		pool:        p,
		oauth2Mgr:   o,
		vaultClient: v,
		smtpClient:  s,
		rateLimiter: rl,
		audit:       ae,
		permChecker: pc,
	}
}

// denyAllPermissionChecker is a safe default that denies all grants when
// no real checker is injected (fail-closed).
type denyAllPermissionChecker struct{}

func (d *denyAllPermissionChecker) CheckGrant(_ context.Context, _, _, _ string) error {
	return permissions.ErrPermissionDenied
}

// checkEmailPermission verifies that the agent in claims has an email_permission_grant
// for the given service_id (which is the email_service_id in email_permission_grants).
// Returns true on success; writes a 403 response and returns false on denial.
func (h *EmailHandlers) checkEmailPermission(w http.ResponseWriter, r *http.Request, claims *auth.Claims, serviceID string) bool {
	if err := h.permChecker.CheckGrant(r.Context(), claims.TenantID, claims.Subject, serviceID); err != nil {
		if errors.Is(err, permissions.ErrPermissionDenied) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusForbidden)
			_, _ = w.Write([]byte(`{"mintkey:code":"permission_denied","title":"agent has no email_permission_grant for this email_service"}`))
			return false
		}
		slog.Warn("checkEmailPermission: transient error checking grant",
			"tenant_id", claims.TenantID,
			"agent_id", claims.Subject,
			"service_id", serviceID,
			"error", err,
		)
		writeError(w, http.StatusServiceUnavailable, "failed to verify email permission grant")
		return false
	}
	return true
}

// ============================================================================
// 1. List mailboxes   GET /v1/email-proxy/mailboxes
// ============================================================================

// HandleListMailboxes handles GET /v1/email-proxy/mailboxes.
// Required scope: read:email.
func (h *EmailHandlers) HandleListMailboxes(w http.ResponseWriter, r *http.Request) {
	claims, ok := claimsFromContext(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing claims in context")
		return
	}
	if !claims.Has("read:email") {
		writeError(w, http.StatusForbidden, "scope read:email required")
		return
	}

	serviceID := r.URL.Query().Get("service_id")
	if serviceID == "" {
		writeError(w, http.StatusBadRequest, "service_id query parameter is required")
		return
	}

	if !h.checkEmailPermission(w, r, claims, serviceID) {
		return
	}

	if err := h.rateLimiter.Allow(r.Context(), claims.Subject, serviceID, rateLimitPerMin); err != nil {
		writeError(w, http.StatusTooManyRequests, "rate limit exceeded")
		return
	}

	imapClient, cfg, err := h.leaseIMAPClient(r.Context(), claims, serviceID)
	if err != nil {
		if errors.Is(err, oauth2.ErrRefreshTokenRevoked) {
			writeError(w, http.StatusUnauthorized, "email service authorization expired")
			return
		}
		slog.Warn("list_mailboxes: failed to lease IMAP client", "error", err, "service_id", serviceID)
		writeError(w, http.StatusServiceUnavailable, "failed to connect to email service")
		return
	}
	defer h.pool.Release(cfg, imapClient)

	mailboxes, err := imapClient.ListMailboxes(r.Context())
	if err != nil {
		slog.Warn("list_mailboxes: IMAP ListMailboxes failed", "error", err)
		writeError(w, http.StatusServiceUnavailable, "IMAP operation failed")
		return
	}

	_ = h.audit.Emit(r.Context(), AuditEvent{
		EventType:  "email.mailboxes.listed",
		TenantID:   claims.TenantID,
		AgentID:    claims.Subject,
		ServiceID:  serviceID,
		TargetID:   serviceID,
		TargetType: "email_service",
		Payload: map[string]interface{}{
			"agent_id":      claims.Subject,
			"service_id":    serviceID,
			"mailbox_count": len(mailboxes),
		},
	})

	resp := struct {
		Mailboxes []mailboxJSON `json:"mailboxes"`
	}{
		Mailboxes: toMailboxJSON(mailboxes),
	}
	writeJSON(w, http.StatusOK, resp)
}

// ============================================================================
// 2. List messages   GET /v1/email-proxy/messages
// ============================================================================

// HandleListMessages handles GET /v1/email-proxy/messages.
// Required scope: read:email.
func (h *EmailHandlers) HandleListMessages(w http.ResponseWriter, r *http.Request) {
	claims, ok := claimsFromContext(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing claims in context")
		return
	}
	if !claims.Has("read:email") {
		writeError(w, http.StatusForbidden, "scope read:email required")
		return
	}

	serviceID := r.URL.Query().Get("service_id")
	if serviceID == "" {
		writeError(w, http.StatusBadRequest, "service_id query parameter is required")
		return
	}

	if !h.checkEmailPermission(w, r, claims, serviceID) {
		return
	}

	if err := h.rateLimiter.Allow(r.Context(), claims.Subject, serviceID, rateLimitPerMin); err != nil {
		writeError(w, http.StatusTooManyRequests, "rate limit exceeded")
		return
	}

	mailbox := r.URL.Query().Get("mailbox")
	if mailbox == "" {
		mailbox = defaultMailbox
	}

	limit := defaultListLimit
	if lStr := r.URL.Query().Get("limit"); lStr != "" {
		l, err := strconv.Atoi(lStr)
		if err != nil || l < 1 || l > maxListLimit {
			writeError(w, http.StatusBadRequest, "limit must be an integer between 1 and 200")
			return
		}
		limit = l
	}

	imapClient, cfg, err := h.leaseIMAPClient(r.Context(), claims, serviceID)
	if err != nil {
		if errors.Is(err, oauth2.ErrRefreshTokenRevoked) {
			writeError(w, http.StatusUnauthorized, "email service authorization expired")
			return
		}
		slog.Warn("list_messages: failed to lease IMAP client", "error", err)
		writeError(w, http.StatusServiceUnavailable, "failed to connect to email service")
		return
	}
	defer h.pool.Release(cfg, imapClient)

	messages, err := imapClient.FetchMessages(r.Context(), mailbox, uint32(limit))
	if err != nil {
		slog.Warn("list_messages: FetchMessages failed", "error", err)
		writeError(w, http.StatusServiceUnavailable, "IMAP operation failed")
		return
	}

	_ = h.audit.Emit(r.Context(), AuditEvent{
		EventType:  "email.messages.listed",
		TenantID:   claims.TenantID,
		AgentID:    claims.Subject,
		ServiceID:  serviceID,
		TargetID:   serviceID,
		TargetType: "email_service",
		Payload: map[string]interface{}{
			"agent_id":      claims.Subject,
			"service_id":    serviceID,
			"mailbox":       mailbox,
			"message_count": len(messages),
		},
	})

	resp := struct {
		Messages   []messageHeaderJSON `json:"messages"`
		NextCursor interface{}         `json:"next_cursor"`
	}{
		Messages:   toMessageHeaderJSON(messages, mailbox),
		NextCursor: nil,
	}
	writeJSON(w, http.StatusOK, resp)
}

// ============================================================================
// 3. Send email   POST /v1/email-proxy/messages
// ============================================================================

// HandleSendMessage handles POST /v1/email-proxy/messages.
// Required scope: send:email.
func (h *EmailHandlers) HandleSendMessage(w http.ResponseWriter, r *http.Request) {
	claims, ok := claimsFromContext(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing claims in context")
		return
	}
	if !claims.Has("send:email") {
		writeError(w, http.StatusForbidden, "scope send:email required")
		return
	}

	serviceID := r.URL.Query().Get("service_id")
	if serviceID == "" {
		writeError(w, http.StatusBadRequest, "service_id query parameter is required")
		return
	}

	if !h.checkEmailPermission(w, r, claims, serviceID) {
		return
	}

	if err := h.rateLimiter.Allow(r.Context(), claims.Subject, serviceID, rateLimitPerMin); err != nil {
		writeError(w, http.StatusTooManyRequests, "rate limit exceeded")
		return
	}

	var body sendEmailRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	// Security: validate and sanitize addresses (CRLF injection + RFC 5322).
	for _, addr := range append(append(body.To, body.Cc...), body.Bcc...) {
		if _, err := security.ParseAddressList(addr); err != nil {
			writeError(w, http.StatusBadRequest, fmt.Sprintf("invalid recipient address: %v", err))
			return
		}
	}

	// Security: sanitize subject header.
	if _, _, err := security.SanitizeHeader("Subject", body.Subject); err != nil {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("invalid subject: %v", err))
		return
	}

	// Fetch SMTP credential.
	smtpCred, smtpCfg, err := h.getSMTPCredential(r.Context(), claims, serviceID)
	if err != nil {
		if errors.Is(err, oauth2.ErrRefreshTokenRevoked) {
			writeError(w, http.StatusUnauthorized, "email service authorization expired")
			return
		}
		slog.Warn("send_message: failed to get SMTP credential", "error", err)
		writeError(w, http.StatusServiceUnavailable, "failed to get email credentials")
		return
	}

	// Build per-send SMTP DialTarget from vault credential metadata.
	// Port 465 → implicit TLS (SMTPS); 587 or other → STARTTLS; 25 → rejected.
	// smtpPort from vault is int32; convert to int for smtp.DialTarget.
	smtpPort := int(smtpCfg.smtpPort)
	if smtpPort == 0 {
		// Fall back to STARTTLS on 587 if the service has no smtp_port configured.
		// This preserves pre-existing behaviour for services that don't yet have
		// smtp_port set in email_services.
		smtpPort = 587
		slog.Warn("send_message: smtp_port not configured for service; falling back to 587 (STARTTLS)",
			"service_id", serviceID,
		)
	}
	dialTarget := smtp.DialTarget{
		Host:               smtpCfg.smtpHost,
		Port:               smtpPort,
		InsecureSkipVerify: smtpCfg.insecureSkipVerify,
	}
	if dialTarget.Host == "" {
		slog.Warn("send_message: smtp_host not configured for service",
			"service_id", serviceID,
			"smtp_port", smtpPort,
		)
	}

	req := smtp.EmailSendRequest{
		From:             smtpCfg.fromAddr,
		To:               body.To,
		Cc:               body.Cc,
		Bcc:              body.Bcc,
		Subject:          body.Subject,
		Body:             body.Body,
		BodyHTML:         body.BodyHTML,
		ReplyToMessageID: body.ReplyToMessageID,
	}

	msgID, err := h.smtpClient.Send(r.Context(), smtpCred, req, dialTarget)
	if err != nil {
		slog.Warn("send_message: SMTP Send failed",
			"error", err,
			"host", dialTarget.Host,
			"port", strconv.Itoa(smtpPort),
			"body_summary", security.ScrubBodyForLog(body.Body),
		)
		writeError(w, http.StatusServiceUnavailable, "failed to send email")
		return
	}

	_ = h.audit.Emit(r.Context(), AuditEvent{
		EventType:  "email.message.sent",
		TenantID:   claims.TenantID,
		AgentID:    claims.Subject,
		ServiceID:  serviceID,
		TargetID:   msgID,
		TargetType: "email_message",
		Payload: map[string]interface{}{
			"agent_id":          claims.Subject,
			"service_id":        serviceID,
			"message_id":        msgID,
			"recipient_count":   len(body.To) + len(body.Cc) + len(body.Bcc),
			"subject_truncated": truncateSubject(body.Subject),
			"body_summary":      security.ScrubBodyForLog(body.Body),
			// NOTE: no body content, no refresh_token, no access_token, no client_secret.
		},
	})

	writeJSON(w, http.StatusAccepted, map[string]string{"message_id": msgID})
}

// ============================================================================
// 4. Search messages   GET /v1/email-proxy/messages/search
// ============================================================================

// HandleSearchMessages handles GET /v1/email-proxy/messages/search.
// Required scope: read:email.
func (h *EmailHandlers) HandleSearchMessages(w http.ResponseWriter, r *http.Request) {
	claims, ok := claimsFromContext(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing claims in context")
		return
	}
	if !claims.Has("read:email") {
		writeError(w, http.StatusForbidden, "scope read:email required")
		return
	}

	serviceID := r.URL.Query().Get("service_id")
	if serviceID == "" {
		writeError(w, http.StatusBadRequest, "service_id query parameter is required")
		return
	}

	if !h.checkEmailPermission(w, r, claims, serviceID) {
		return
	}

	if err := h.rateLimiter.Allow(r.Context(), claims.Subject, serviceID, rateLimitPerMin); err != nil {
		writeError(w, http.StatusTooManyRequests, "rate limit exceeded")
		return
	}

	query := r.URL.Query().Get("query")
	if query == "" {
		writeError(w, http.StatusBadRequest, "query parameter is required")
		return
	}
	if len(query) > maxSearchQueryLen {
		writeError(w, http.StatusBadRequest, "query exceeds maximum length of 500 characters")
		return
	}

	mailbox := r.URL.Query().Get("mailbox")
	if mailbox == "" {
		mailbox = defaultMailbox
	}

	limit := defaultListLimit
	if lStr := r.URL.Query().Get("limit"); lStr != "" {
		l, err := strconv.Atoi(lStr)
		if err != nil || l < 1 || l > maxListLimit {
			writeError(w, http.StatusBadRequest, "limit must be an integer between 1 and 200")
			return
		}
		limit = l
	}

	imapClient, cfg, err := h.leaseIMAPClient(r.Context(), claims, serviceID)
	if err != nil {
		if errors.Is(err, oauth2.ErrRefreshTokenRevoked) {
			writeError(w, http.StatusUnauthorized, "email service authorization expired")
			return
		}
		slog.Warn("search_messages: failed to lease IMAP client", "error", err)
		writeError(w, http.StatusServiceUnavailable, "failed to connect to email service")
		return
	}
	defer h.pool.Release(cfg, imapClient)

	// Build parameterised IMAP search criteria from the text query.
	// The query string is used as an IMAP TEXT search (body + headers).
	// CRLF/injection characters are stripped before passing to IMAP.
	sanitizedQuery := sanitizeSearchQuery(query)
	criteria := &goiMAP.SearchCriteria{
		Text: []string{sanitizedQuery},
	}

	uids, err := imapClient.SearchMessages(r.Context(), mailbox, criteria)
	if err != nil {
		slog.Warn("search_messages: SearchMessages failed", "error", err)
		writeError(w, http.StatusServiceUnavailable, "IMAP search failed")
		return
	}

	// Fetch envelopes for matching UIDs (capped at limit).
	messages := make([]messageHeaderJSON, 0, len(uids))
	for i, uid := range uids {
		if i >= limit {
			break
		}
		_, hdr, err := imapClient.FetchMessage(r.Context(), mailbox, uid)
		if err != nil {
			slog.Debug("search_messages: FetchMessage failed for UID", "uid", uid, "error", err)
			continue
		}
		messages = append(messages, messageHeaderToJSON(*hdr, mailbox))
	}

	_ = h.audit.Emit(r.Context(), AuditEvent{
		EventType:  "email.messages.listed",
		TenantID:   claims.TenantID,
		AgentID:    claims.Subject,
		ServiceID:  serviceID,
		TargetID:   serviceID,
		TargetType: "email_service",
		Payload: map[string]interface{}{
			"agent_id":     claims.Subject,
			"service_id":   serviceID,
			"mailbox":      mailbox,
			"query_length": len(query), // length only, not content (NFR-21)
			"result_count": len(messages),
		},
	})

	resp := struct {
		Messages []messageHeaderJSON `json:"messages"`
	}{Messages: messages}
	writeJSON(w, http.StatusOK, resp)
}

// ============================================================================
// 5. Read message   GET /v1/email-proxy/messages/{message_id}
// ============================================================================

// HandleReadMessage handles GET /v1/email-proxy/messages/{message_id}.
// Required scope: read:email.
func (h *EmailHandlers) HandleReadMessage(w http.ResponseWriter, r *http.Request) {
	claims, ok := claimsFromContext(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing claims in context")
		return
	}
	if !claims.Has("read:email") {
		writeError(w, http.StatusForbidden, "scope read:email required")
		return
	}

	serviceID := r.URL.Query().Get("service_id")
	if serviceID == "" {
		writeError(w, http.StatusBadRequest, "service_id query parameter is required")
		return
	}

	if !h.checkEmailPermission(w, r, claims, serviceID) {
		return
	}

	messageID := pathSegment(r.URL.Path, "messages", 0)
	if messageID == "" {
		writeError(w, http.StatusBadRequest, "message_id path parameter is required")
		return
	}
	// Strip any sub-path suffix (e.g. /flags, /move, /attachments/...)
	messageID = strings.Split(messageID, "/")[0]

	uid, err := parseUID(messageID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "message_id must be a valid IMAP UID")
		return
	}

	mailbox := r.URL.Query().Get("mailbox")
	if mailbox == "" {
		mailbox = defaultMailbox
	}

	if err := h.rateLimiter.Allow(r.Context(), claims.Subject, serviceID, rateLimitPerMin); err != nil {
		writeError(w, http.StatusTooManyRequests, "rate limit exceeded")
		return
	}

	imapClient, cfg, err := h.leaseIMAPClient(r.Context(), claims, serviceID)
	if err != nil {
		if errors.Is(err, oauth2.ErrRefreshTokenRevoked) {
			writeError(w, http.StatusUnauthorized, "email service authorization expired")
			return
		}
		slog.Warn("read_message: failed to lease IMAP client", "error", err)
		writeError(w, http.StatusServiceUnavailable, "failed to connect to email service")
		return
	}
	defer h.pool.Release(cfg, imapClient)

	body, hdr, err := imapClient.FetchMessage(r.Context(), mailbox, uid)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			writeError(w, http.StatusNotFound, "message not found")
			return
		}
		slog.Warn("read_message: FetchMessage failed", "error", err)
		writeError(w, http.StatusServiceUnavailable, "IMAP operation failed")
		return
	}

	// NFR-17: body content MUST NOT appear in audit payload.
	bodySummary := security.ScrubBodyForLog(string(body))

	_ = h.audit.Emit(r.Context(), AuditEvent{
		EventType:  "email.message.read",
		TenantID:   claims.TenantID,
		AgentID:    claims.Subject,
		ServiceID:  serviceID,
		TargetID:   fmt.Sprintf("%d", uid),
		TargetType: "email_message",
		Payload: map[string]interface{}{
			"agent_id":     claims.Subject,
			"service_id":   serviceID,
			"message_uid":  fmt.Sprintf("%d", uid),
			"mailbox":      mailbox,
			"body_summary": bodySummary,
			// NOTE: no body content, no refresh_token, no access_token, no client_secret.
		},
	})

	msg := messageHeaderToJSON(*hdr, mailbox)
	msg.Body = string(body)

	writeJSON(w, http.StatusOK, msg)
}

// ============================================================================
// 6. Delete message   DELETE /v1/email-proxy/messages/{message_id}
// ============================================================================

// HandleDeleteMessage handles DELETE /v1/email-proxy/messages/{message_id}.
// Required scope: delete:email.
func (h *EmailHandlers) HandleDeleteMessage(w http.ResponseWriter, r *http.Request) {
	claims, ok := claimsFromContext(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing claims in context")
		return
	}
	if !claims.Has("delete:email") {
		writeError(w, http.StatusForbidden, "scope delete:email required")
		return
	}

	serviceID := r.URL.Query().Get("service_id")
	if serviceID == "" {
		writeError(w, http.StatusBadRequest, "service_id query parameter is required")
		return
	}

	if !h.checkEmailPermission(w, r, claims, serviceID) {
		return
	}

	messageID := pathSegment(r.URL.Path, "messages", 0)
	if messageID == "" {
		writeError(w, http.StatusBadRequest, "message_id path parameter is required")
		return
	}
	messageID = strings.Split(messageID, "/")[0]

	uid, err := parseUID(messageID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "message_id must be a valid IMAP UID")
		return
	}

	mailbox := r.URL.Query().Get("mailbox")
	if mailbox == "" {
		mailbox = defaultMailbox
	}

	if err := h.rateLimiter.Allow(r.Context(), claims.Subject, serviceID, rateLimitPerMin); err != nil {
		writeError(w, http.StatusTooManyRequests, "rate limit exceeded")
		return
	}

	imapClient, cfg, err := h.leaseIMAPClient(r.Context(), claims, serviceID)
	if err != nil {
		if errors.Is(err, oauth2.ErrRefreshTokenRevoked) {
			writeError(w, http.StatusUnauthorized, "email service authorization expired")
			return
		}
		slog.Warn("delete_message: failed to lease IMAP client", "error", err)
		writeError(w, http.StatusServiceUnavailable, "failed to connect to email service")
		return
	}
	defer h.pool.Release(cfg, imapClient)

	// SelectMailbox before delete so the client knows which mailbox to expunge from.
	if _, err := imapClient.SelectMailbox(r.Context(), mailbox); err != nil && !errors.Is(err, imapwrap.ErrUIDValidityChanged) {
		slog.Warn("delete_message: SelectMailbox failed", "error", err)
		writeError(w, http.StatusServiceUnavailable, "IMAP operation failed")
		return
	}

	if err := imapClient.DeleteMessage(r.Context(), uid); err != nil {
		if strings.Contains(err.Error(), "not found") {
			writeError(w, http.StatusNotFound, "message not found")
			return
		}
		slog.Warn("delete_message: DeleteMessage failed", "error", err)
		writeError(w, http.StatusServiceUnavailable, "IMAP operation failed")
		return
	}

	_ = h.audit.Emit(r.Context(), AuditEvent{
		EventType:  "email.message.deleted",
		TenantID:   claims.TenantID,
		AgentID:    claims.Subject,
		ServiceID:  serviceID,
		TargetID:   fmt.Sprintf("%d", uid),
		TargetType: "email_message",
		Payload: map[string]interface{}{
			"agent_id":    claims.Subject,
			"service_id":  serviceID,
			"message_uid": fmt.Sprintf("%d", uid),
			"mailbox":     mailbox,
		},
	})

	w.WriteHeader(http.StatusNoContent)
}

// ============================================================================
// 7. Update message flags   PATCH /v1/email-proxy/messages/{message_id}/flags
// ============================================================================

// HandleUpdateFlags handles PATCH /v1/email-proxy/messages/{message_id}/flags.
// Required scope: write:email.
func (h *EmailHandlers) HandleUpdateFlags(w http.ResponseWriter, r *http.Request) {
	claims, ok := claimsFromContext(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing claims in context")
		return
	}
	if !claims.Has("write:email") {
		writeError(w, http.StatusForbidden, "scope write:email required")
		return
	}

	serviceID := r.URL.Query().Get("service_id")
	if serviceID == "" {
		writeError(w, http.StatusBadRequest, "service_id query parameter is required")
		return
	}

	if !h.checkEmailPermission(w, r, claims, serviceID) {
		return
	}

	messageID := pathSegment(r.URL.Path, "messages", 0)
	if messageID == "" {
		writeError(w, http.StatusBadRequest, "message_id path parameter is required")
		return
	}
	// Strip /flags suffix
	messageID = strings.Split(messageID, "/")[0]

	uid, err := parseUID(messageID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "message_id must be a valid IMAP UID")
		return
	}

	mailbox := r.URL.Query().Get("mailbox")
	if mailbox == "" {
		mailbox = defaultMailbox
	}

	if err := h.rateLimiter.Allow(r.Context(), claims.Subject, serviceID, rateLimitPerMin); err != nil {
		writeError(w, http.StatusTooManyRequests, "rate limit exceeded")
		return
	}

	var body flagsRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	imapClient, cfg, err := h.leaseIMAPClient(r.Context(), claims, serviceID)
	if err != nil {
		if errors.Is(err, oauth2.ErrRefreshTokenRevoked) {
			writeError(w, http.StatusUnauthorized, "email service authorization expired")
			return
		}
		slog.Warn("update_flags: failed to lease IMAP client", "error", err)
		writeError(w, http.StatusServiceUnavailable, "failed to connect to email service")
		return
	}
	defer h.pool.Release(cfg, imapClient)

	// Select the mailbox first.
	if _, err := imapClient.SelectMailbox(r.Context(), mailbox); err != nil && !errors.Is(err, imapwrap.ErrUIDValidityChanged) {
		slog.Warn("update_flags: SelectMailbox failed", "error", err)
		writeError(w, http.StatusServiceUnavailable, "IMAP operation failed")
		return
	}

	flags := toIMAPFlags(body)
	if err := imapClient.UpdateFlags(r.Context(), uid, flags); err != nil {
		slog.Warn("update_flags: UpdateFlags failed", "error", err)
		writeError(w, http.StatusServiceUnavailable, "IMAP operation failed")
		return
	}

	_ = h.audit.Emit(r.Context(), AuditEvent{
		EventType:  "email.message.flags_updated",
		TenantID:   claims.TenantID,
		AgentID:    claims.Subject,
		ServiceID:  serviceID,
		TargetID:   fmt.Sprintf("%d", uid),
		TargetType: "email_message",
		Payload: map[string]interface{}{
			"agent_id":    claims.Subject,
			"service_id":  serviceID,
			"message_uid": fmt.Sprintf("%d", uid),
			"mailbox":     mailbox,
			"flag_count":  len(flags),
		},
	})

	writeJSON(w, http.StatusOK, body)
}

// ============================================================================
// 8. Move message   POST /v1/email-proxy/messages/{message_id}/move
// ============================================================================

// HandleMoveMessage handles POST /v1/email-proxy/messages/{message_id}/move.
// Required scope: write:email.
func (h *EmailHandlers) HandleMoveMessage(w http.ResponseWriter, r *http.Request) {
	claims, ok := claimsFromContext(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing claims in context")
		return
	}
	if !claims.Has("write:email") {
		writeError(w, http.StatusForbidden, "scope write:email required")
		return
	}

	serviceID := r.URL.Query().Get("service_id")
	if serviceID == "" {
		writeError(w, http.StatusBadRequest, "service_id query parameter is required")
		return
	}

	if !h.checkEmailPermission(w, r, claims, serviceID) {
		return
	}

	messageID := pathSegment(r.URL.Path, "messages", 0)
	if messageID == "" {
		writeError(w, http.StatusBadRequest, "message_id path parameter is required")
		return
	}
	// Strip /move suffix
	messageID = strings.Split(messageID, "/")[0]

	uid, err := parseUID(messageID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "message_id must be a valid IMAP UID")
		return
	}

	if err := h.rateLimiter.Allow(r.Context(), claims.Subject, serviceID, rateLimitPerMin); err != nil {
		writeError(w, http.StatusTooManyRequests, "rate limit exceeded")
		return
	}

	var body moveRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if body.DestinationMailbox == "" {
		writeError(w, http.StatusBadRequest, "destination_mailbox is required")
		return
	}

	// Sanitize destination mailbox name.
	if _, _, err := security.SanitizeHeader("destination_mailbox", body.DestinationMailbox); err != nil {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("invalid destination_mailbox: %v", err))
		return
	}

	srcMailbox := r.URL.Query().Get("mailbox")
	if srcMailbox == "" {
		srcMailbox = defaultMailbox
	}

	imapClient, cfg, err := h.leaseIMAPClient(r.Context(), claims, serviceID)
	if err != nil {
		if errors.Is(err, oauth2.ErrRefreshTokenRevoked) {
			writeError(w, http.StatusUnauthorized, "email service authorization expired")
			return
		}
		slog.Warn("move_message: failed to lease IMAP client", "error", err)
		writeError(w, http.StatusServiceUnavailable, "failed to connect to email service")
		return
	}
	defer h.pool.Release(cfg, imapClient)

	// Select source mailbox before MOVE.
	if _, err := imapClient.SelectMailbox(r.Context(), srcMailbox); err != nil && !errors.Is(err, imapwrap.ErrUIDValidityChanged) {
		slog.Warn("move_message: SelectMailbox failed", "error", err)
		writeError(w, http.StatusServiceUnavailable, "IMAP operation failed")
		return
	}

	if err := imapClient.MoveMessage(r.Context(), uid, body.DestinationMailbox); err != nil {
		if strings.Contains(err.Error(), "not found") {
			writeError(w, http.StatusNotFound, "message not found")
			return
		}
		slog.Warn("move_message: MoveMessage failed", "error", err)
		writeError(w, http.StatusServiceUnavailable, "IMAP operation failed")
		return
	}

	_ = h.audit.Emit(r.Context(), AuditEvent{
		EventType:  "email.message.moved",
		TenantID:   claims.TenantID,
		AgentID:    claims.Subject,
		ServiceID:  serviceID,
		TargetID:   fmt.Sprintf("%d", uid),
		TargetType: "email_message",
		Payload: map[string]interface{}{
			"agent_id":            claims.Subject,
			"service_id":          serviceID,
			"message_uid":         fmt.Sprintf("%d", uid),
			"source_mailbox":      srcMailbox,
			"destination_mailbox": body.DestinationMailbox,
		},
	})

	writeJSON(w, http.StatusOK, map[string]string{
		"message_id": messageID,
		"mailbox":    body.DestinationMailbox,
	})
}

// ============================================================================
// 9. Download attachment   GET /v1/email-proxy/messages/{message_id}/attachments/{attachment_id}
// ============================================================================

// HandleDownloadAttachment handles GET /v1/email-proxy/messages/{message_id}/attachments/{attachment_id}.
// Required scope: read:email.
func (h *EmailHandlers) HandleDownloadAttachment(w http.ResponseWriter, r *http.Request) {
	claims, ok := claimsFromContext(r.Context())
	if !ok {
		writeError(w, http.StatusUnauthorized, "missing claims in context")
		return
	}
	if !claims.Has("read:email") {
		writeError(w, http.StatusForbidden, "scope read:email required")
		return
	}

	serviceID := r.URL.Query().Get("service_id")
	if serviceID == "" {
		writeError(w, http.StatusBadRequest, "service_id query parameter is required")
		return
	}

	if !h.checkEmailPermission(w, r, claims, serviceID) {
		return
	}

	messageID := pathSegment(r.URL.Path, "messages", 0)
	if messageID == "" {
		writeError(w, http.StatusBadRequest, "message_id path parameter is required")
		return
	}
	// Extract message_id (before /attachments/)
	parts := strings.SplitN(messageID, "/", 3)
	if len(parts) < 3 || parts[1] != "attachments" {
		writeError(w, http.StatusBadRequest, "invalid URL: expected .../messages/{id}/attachments/{att_id}")
		return
	}
	msgIDStr := parts[0]
	attachmentID := parts[2]

	uid, err := parseUID(msgIDStr)
	if err != nil {
		writeError(w, http.StatusBadRequest, "message_id must be a valid IMAP UID")
		return
	}

	mailbox := r.URL.Query().Get("mailbox")
	if mailbox == "" {
		mailbox = defaultMailbox
	}

	if err := h.rateLimiter.Allow(r.Context(), claims.Subject, serviceID, rateLimitPerMin); err != nil {
		writeError(w, http.StatusTooManyRequests, "rate limit exceeded")
		return
	}

	imapClient, cfg, err := h.leaseIMAPClient(r.Context(), claims, serviceID)
	if err != nil {
		if errors.Is(err, oauth2.ErrRefreshTokenRevoked) {
			writeError(w, http.StatusUnauthorized, "email service authorization expired")
			return
		}
		slog.Warn("download_attachment: failed to lease IMAP client", "error", err)
		writeError(w, http.StatusServiceUnavailable, "failed to connect to email service")
		return
	}
	defer h.pool.Release(cfg, imapClient)

	att, err := imapClient.DownloadAttachment(r.Context(), uid, attachmentID)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			writeError(w, http.StatusNotFound, "attachment not found")
			return
		}
		slog.Warn("download_attachment: DownloadAttachment failed", "error", err)
		writeError(w, http.StatusServiceUnavailable, "IMAP operation failed")
		return
	}

	_ = h.audit.Emit(r.Context(), AuditEvent{
		EventType:  "email.message.read",
		TenantID:   claims.TenantID,
		AgentID:    claims.Subject,
		ServiceID:  serviceID,
		TargetID:   fmt.Sprintf("%d/%s", uid, attachmentID),
		TargetType: "email_attachment",
		Payload: map[string]interface{}{
			"agent_id":      claims.Subject,
			"service_id":    serviceID,
			"message_uid":   fmt.Sprintf("%d", uid),
			"attachment_id": attachmentID,
			"content_type":  att.ContentType,
			"size_bytes":    len(att.Data),
			// NOTE: att.Data (attachment content) is NOT included.
		},
	})

	ct := att.ContentType
	if ct == "" {
		ct = "application/octet-stream"
	}
	w.Header().Set("Content-Type", ct)
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(att.Data)
}

// ============================================================================
// Internal helpers
// ============================================================================

// resolveIMAPAddr returns the IMAP dial address for an email credential,
// using a fixed priority order that mirrors getSMTPCredential's
// cred.SMTPHost/cred.SMTPPort precedence (ADR-0024 Phase 2):
//
//  1. cred.IMAPHost:cred.IMAPPort — the JOIN-populated per-service fields
//     from email_services (primary; populated for all post-cb2ae0b rows).
//  2. payloadIMAPHost — legacy JSON-payload imap_host (backwards compat
//     for pre-cb2ae0b email_password / email_app_password rows whose
//     plaintext payload contains an imap_host field). Empty for OAuth2.
//  3. cred.BaseUrl — legacy fallback (always empty for email_services rows
//     because the vault-adapter's JOIN sources base_url from public.services,
//     which has no row for email services; harmless to attempt).
//
// Returns "" when none of the three sources is populated; callers MUST
// treat that as the "no IMAP address found for service" error case.
//
// Note: this resolves *addressing metadata*, not credential plaintext.
// Logging/inspecting the returned string is safe under NFR-17.
func resolveIMAPAddr(cred *vault.Credential, payloadIMAPHost string) string {
	if cred == nil {
		return ""
	}
	// Primary: per-service IMAP host/port from email_services JOIN.
	// IMAPPort must be non-zero — IMAPPort=0 means "no port returned",
	// in which case we must fall through, not emit "host:0".
	if cred.IMAPHost != "" && cred.IMAPPort != 0 {
		return fmt.Sprintf("%s:%d", cred.IMAPHost, cred.IMAPPort)
	}
	// Fallback 1: legacy payload imap_host (password schemes only).
	if payloadIMAPHost != "" {
		return payloadIMAPHost
	}
	// Fallback 2: legacy BaseUrl (always empty for email_services; harmless).
	return cred.BaseUrl
}

// leaseIMAPClient resolves credentials and obtains a pooled IMAP client.
// The caller MUST call pool.Release when done.
func (h *EmailHandlers) leaseIMAPClient(ctx context.Context, claims *auth.Claims, serviceID string) (*imapwrap.Client, pool.ServiceConfig, error) {
	// Try OAuth2 first; fall back to password / app-password.
	cred, err := h.vaultClient.GetCredential(ctx, claims.TenantID, serviceID, vault.AuthSchemeEmailOAuth2)
	if err != nil {
		// Credential fetch failed entirely — treat as service unavailable.
		return nil, pool.ServiceConfig{}, fmt.Errorf("vault: GetCredential: %w", err)
	}

	var imapCreds imapwrap.Credentials
	var addr string

	switch cred.AuthScheme {
	case vault.AuthSchemeEmailOAuth2:
		// Fetch fresh access token from admin-api via oauth2.Manager.
		accessToken, err := h.oauth2Mgr.GetAccessToken(ctx, claims.TenantID, serviceID)
		if err != nil {
			return nil, pool.ServiceConfig{}, err
		}
		// Parse the email_address from the vault JSON payload.
		emailAddr := parseEmailAddressFromPayload(cred.Value)
		imapCreds = imapwrap.Credentials{
			Username:    emailAddr,
			AccessToken: accessToken,
			AuthMode:    imapwrap.AuthModeXOAuth2,
		}
		// OAuth2 payload has no imap_host field — pass "" so the helper
		// falls through to the BaseUrl fallback when IMAPHost is empty.
		addr = resolveIMAPAddr(cred, "")

	case vault.AuthSchemeEmailPassword, vault.AuthSchemeEmailAppPassword:
		// Parse JSON payload: {"username":"...","password":"...","imap_host":"..."}
		username, password, imapHost := parsePasswordPayload(cred.Value)
		imapCreds = imapwrap.Credentials{
			Username: username,
			Password: password,
			AuthMode: imapwrap.AuthModeLogin,
		}
		addr = resolveIMAPAddr(cred, imapHost)

	default:
		return nil, pool.ServiceConfig{}, fmt.Errorf("unsupported auth scheme %d for IMAP", cred.AuthScheme)
	}

	// Zero the vault credential bytes after parsing (NFR-17).
	for i := range cred.Value {
		cred.Value[i] = 0
	}

	if addr == "" {
		return nil, pool.ServiceConfig{}, fmt.Errorf("no IMAP address found for service %s", serviceID)
	}

	cfg := pool.ServiceConfig{
		TenantID:              claims.TenantID,
		ServiceID:             serviceID,
		Addr:                  addr,
		DialMode:              imapwrap.DialModeTLS,
		Creds:                 imapCreds,
		TlsInsecureSkipVerify: cred.TlsInsecureSkipVerify,
	}

	client, err := h.pool.Get(ctx, cfg)
	if err != nil {
		return nil, pool.ServiceConfig{}, fmt.Errorf("pool.Get: %w", err)
	}
	return client, cfg, nil
}

// smtpConnConfig holds resolved SMTP connection parameters.
type smtpConnConfig struct {
	fromAddr string
	// Per-service SMTP routing metadata from the vault credential response.
	// Populated from email_services.smtp_host / smtp_port (ADR-0024 Phase 2).
	smtpHost string
	smtpPort int32
	// insecureSkipVerify mirrors tls_insecure_skip_verify from the vault response.
	insecureSkipVerify bool
}

// getSMTPCredential resolves SMTP credentials for a send operation.
// It populates smtpConnConfig with per-service SMTP host/port/TLS metadata
// from the vault credential response (ADR-0024 Phase 2).
func (h *EmailHandlers) getSMTPCredential(ctx context.Context, claims *auth.Claims, serviceID string) (smtp.Credential, smtpConnConfig, error) {
	cred, err := h.vaultClient.GetCredential(ctx, claims.TenantID, serviceID, vault.AuthSchemeEmailOAuth2)
	if err != nil {
		return smtp.Credential{}, smtpConnConfig{}, fmt.Errorf("vault: GetCredential: %w", err)
	}
	defer func() {
		for i := range cred.Value {
			cred.Value[i] = 0
		}
	}()

	switch cred.AuthScheme {
	case vault.AuthSchemeEmailOAuth2:
		accessToken, err := h.oauth2Mgr.GetAccessToken(ctx, claims.TenantID, serviceID)
		if err != nil {
			return smtp.Credential{}, smtpConnConfig{}, err
		}
		emailAddr := parseEmailAddressFromPayload(cred.Value)
		return smtp.Credential{
				AuthMode:           smtp.AuthModeXOAUTH2,
				Username:           emailAddr,
				AccessToken:        accessToken,
				InsecureSkipVerify: cred.TlsInsecureSkipVerify,
			}, smtpConnConfig{
				fromAddr:           emailAddr,
				smtpHost:           cred.SMTPHost,
				smtpPort:           cred.SMTPPort,
				insecureSkipVerify: cred.TlsInsecureSkipVerify,
			}, nil

	case vault.AuthSchemeEmailPassword, vault.AuthSchemeEmailAppPassword:
		username, password, _ := parsePasswordPayload(cred.Value)
		return smtp.Credential{
				AuthMode:           smtp.AuthModePLAIN,
				Username:           username,
				Password:           password,
				InsecureSkipVerify: cred.TlsInsecureSkipVerify,
			}, smtpConnConfig{
				fromAddr:           username,
				smtpHost:           cred.SMTPHost,
				smtpPort:           cred.SMTPPort,
				insecureSkipVerify: cred.TlsInsecureSkipVerify,
			}, nil

	default:
		return smtp.Credential{}, smtpConnConfig{}, fmt.Errorf("unsupported auth scheme %d for SMTP", cred.AuthScheme)
	}
}

// ============================================================================
// JSON types
// ============================================================================

// mailboxJSON is the openapi.yaml Mailbox schema.
type mailboxJSON struct {
	Name       string   `json:"name"`
	Attributes []string `json:"attributes,omitempty"`
}

// messageHeaderJSON is the openapi.yaml EmailMessage schema.
type messageHeaderJSON struct {
	MessageID string   `json:"message_id"`
	Subject   string   `json:"subject"`
	From      []string `json:"from"`
	To        []string `json:"to"`
	Date      string   `json:"date"`
	Mailbox   string   `json:"mailbox"`
	Seen      bool     `json:"seen"`
	Answered  bool     `json:"answered,omitempty"`
	Body      string   `json:"body,omitempty"`
}

// sendEmailRequest is the openapi.yaml EmailSendRequest schema.
type sendEmailRequest struct {
	To               []string `json:"to"`
	Cc               []string `json:"cc,omitempty"`
	Bcc              []string `json:"bcc,omitempty"`
	Subject          string   `json:"subject"`
	Body             string   `json:"body,omitempty"`
	BodyHTML         string   `json:"body_html,omitempty"`
	ReplyToMessageID string   `json:"reply_to_message_id,omitempty"`
}

// flagsRequest is the openapi.yaml EmailMessageFlags schema.
type flagsRequest struct {
	Seen     *bool `json:"seen,omitempty"`
	Answered *bool `json:"answered,omitempty"`
	Starred  *bool `json:"starred,omitempty"`
}

// moveRequest is the request body for move endpoint.
type moveRequest struct {
	DestinationMailbox string `json:"destination_mailbox"`
}

// ============================================================================
// Conversion helpers
// ============================================================================

func toMailboxJSON(mailboxes []imapwrap.MailboxInfo) []mailboxJSON {
	out := make([]mailboxJSON, len(mailboxes))
	for i, m := range mailboxes {
		out[i] = mailboxJSON{Name: m.Name, Attributes: m.Attributes}
	}
	return out
}

func toMessageHeaderJSON(headers []imapwrap.MessageHeader, mailbox string) []messageHeaderJSON {
	out := make([]messageHeaderJSON, len(headers))
	for i, h := range headers {
		out[i] = messageHeaderToJSON(h, mailbox)
	}
	return out
}

func messageHeaderToJSON(h imapwrap.MessageHeader, mailbox string) messageHeaderJSON {
	return messageHeaderJSON{
		MessageID: fmt.Sprintf("%d", h.UID),
		Subject:   h.Subject,
		From:      h.From,
		To:        h.To,
		Date:      h.Date.UTC().Format(time.RFC3339),
		Mailbox:   mailbox,
		Seen:      h.Seen,
		Answered:  h.Answered,
	}
}

func toIMAPFlags(req flagsRequest) []goiMAP.Flag {
	var flags []goiMAP.Flag
	if req.Seen != nil && *req.Seen {
		flags = append(flags, goiMAP.FlagSeen)
	}
	if req.Answered != nil && *req.Answered {
		flags = append(flags, goiMAP.FlagAnswered)
	}
	if req.Starred != nil && *req.Starred {
		flags = append(flags, goiMAP.FlagFlagged)
	}
	return flags
}

// ============================================================================
// Credential payload parsers
// ============================================================================

// parseEmailAddressFromPayload extracts the email_address field from the
// OAuth2 vault JSON payload: {"provider":"gmail","refresh_token":"...","email_address":"..."}.
// Returns empty string if parsing fails (callers fall back to a default).
func parseEmailAddressFromPayload(raw []byte) string {
	var m struct {
		EmailAddress string `json:"email_address"`
	}
	if err := json.Unmarshal(raw, &m); err != nil {
		return ""
	}
	return m.EmailAddress
}

// parsePasswordPayload extracts username, password, and imap_host from the
// email_password / app_password vault JSON payload.
// Expected shape: {"username":"...","password":"...","imap_host":"..."}
func parsePasswordPayload(raw []byte) (username, password, imapHost string) {
	var m struct {
		Username string `json:"username"`
		Password string `json:"password"`
		IMAPHost string `json:"imap_host"`
	}
	if err := json.Unmarshal(raw, &m); err != nil {
		return "", "", ""
	}
	return m.Username, m.Password, m.IMAPHost
}

// ============================================================================
// URL path helpers
// ============================================================================

// pathSegment extracts path components after a named segment.
// E.g. pathSegment("/v1/email-proxy/messages/123/flags", "messages", 0) → "123"
// subIndex selects how many additional segments to include after the anchor.
// The returned value includes all path tail after the anchor segment.
func pathSegment(path, anchor string, _ int) string {
	// Normalise: remove leading slash.
	p := strings.TrimPrefix(path, "/")
	parts := strings.Split(p, "/")
	for i, seg := range parts {
		if seg == anchor && i+1 < len(parts) {
			return strings.Join(parts[i+1:], "/")
		}
	}
	return ""
}

// parseUID converts a message_id string to an IMAP UID.
func parseUID(s string) (goiMAP.UID, error) {
	n, err := strconv.ParseUint(s, 10, 32)
	if err != nil {
		return 0, fmt.Errorf("invalid UID %q: %w", s, err)
	}
	return goiMAP.UID(n), nil
}

// sanitizeSearchQuery strips CRLF and control characters from a search string.
// This provides defence-in-depth on top of the parameterised IMAP SEARCH.
func sanitizeSearchQuery(q string) string {
	var b strings.Builder
	for _, r := range q {
		if r == '\r' || r == '\n' {
			continue
		}
		if r < 0x20 && r != '\t' {
			continue
		}
		b.WriteRune(r)
	}
	return b.String()
}

// truncateSubject truncates the subject to ≤100 chars for audit payload.
func truncateSubject(s string) string {
	if len(s) <= 100 {
		return s
	}
	return s[:100] + "…"
}

// ============================================================================
// HTTP response helpers
// ============================================================================

// claimsFromContext retrieves Claims from the request context.
func claimsFromContext(ctx context.Context) (*auth.Claims, bool) {
	c, ok := ctx.Value(contextKeyClaimsType).(*auth.Claims)
	return c, ok && c != nil
}

// writeJSON marshals v as JSON and writes it with the given status code.
func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		slog.Warn("writeJSON: encode failed", "error", err)
	}
}

// writeError writes a JSON problem body.
func writeError(w http.ResponseWriter, status int, msg string) {
	w.Header().Set("Content-Type", "application/problem+json")
	w.WriteHeader(status)
	body := map[string]interface{}{
		"status": status,
		"detail": msg,
	}
	if err := json.NewEncoder(w).Encode(body); err != nil {
		slog.Warn("writeError: encode failed", "error", err)
	}
}
