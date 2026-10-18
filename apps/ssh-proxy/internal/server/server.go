// Package server implements the SSH Proxy bastion server.
package server

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/pem"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"

	"github.com/mintkey/mintkey/services/ssh-proxy/internal/auth"
	"github.com/mintkey/mintkey/services/ssh-proxy/internal/backend"
	"github.com/mintkey/mintkey/services/ssh-proxy/internal/config"
	"github.com/mintkey/mintkey/services/ssh-proxy/internal/metrics"
	"github.com/mintkey/mintkey/services/ssh-proxy/internal/session"
	"github.com/mintkey/mintkey/services/ssh-proxy/internal/vault"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"golang.org/x/crypto/ssh"
	"golang.org/x/time/rate"
)

// deniedChannelTypes lists SSH channel types that the bastion explicitly
// rejects. Only "session" channels are permitted (B5/B6).
var deniedChannelTypes = map[string]bool{
	"direct-tcpip":              true,
	"forwarded-tcpip":           true,
	"x11":                       true,
	"direct-streamlocal@openssh.com": true,
	"auth-agent@openssh.com":    true,
}

// deniedGlobalRequests lists SSH global request names that are rejected.
var deniedGlobalRequests = map[string]bool{
	"tcpip-forward":                  true,
	"cancel-tcpip-forward":           true,
	"streamlocal-forward@openssh.com": true,
	"cancel-streamlocal-forward@openssh.com": true,
}

// Server is the SSH Proxy bastion server.
type Server struct {
	cfg          *config.Config
	sshConfig    *ssh.ServerConfig
	listener     net.Listener
	sessionMgr   *session.Manager
	authHandler  *auth.Handler
	mu           sync.Mutex
	running      bool
	shutdownCh   chan struct{}

	// Rate limiting (B20): token-bucket limiter and concurrent-handshake semaphore.
	limiter *rate.Limiter
	sem     chan struct{} // semaphore: bounded concurrent unauthenticated handshakes
}

// New creates a new SSH Proxy server.
func New(cfg *config.Config) (*Server, error) {
	// Wire the backend connector so sessions can reach upstream SSH targets.
	vaultClient, err := vault.NewClient(cfg.VaultAddr, cfg.VaultIdentityID, cfg.VaultToken)
	if err != nil {
		return nil, fmt.Errorf("failed to create vault client for backend: %w", err)
	}
	connector := backend.NewConnector(vaultClient, nil)

	deps := session.Deps{
		Connector:      connector,
		RecordingPath:  cfg.RecordingStoragePath,
		SessionTimeout: cfg.SessionTimeout,
	}

	s := &Server{
		cfg:        cfg,
		sessionMgr: session.NewManagerWithDeps(cfg.MaxConcurrentSessionsPerAgent, deps),
		shutdownCh: make(chan struct{}),
		limiter:    rate.NewLimiter(rate.Limit(cfg.RateLimitPerSecond), cfg.RateLimitBurst),
		sem:        make(chan struct{}, cfg.MaxConcurrentHandshakes),
	}

	// Load or generate host key
	hostKey, err := s.loadOrGenerateHostKey()
	if err != nil {
		return nil, fmt.Errorf("failed to load host key: %w", err)
	}

	// Create SSH server config (G: server version, banner, MaxAuthTries)
	s.sshConfig = &ssh.ServerConfig{
		PasswordCallback:  s.passwordCallback,
		PublicKeyCallback: s.publicKeyCallback,
		MaxAuthTries:      2,
		ServerVersion:     "SSH-2.0-Mintkey-1",
		BannerCallback: func(conn ssh.ConnMetadata) string {
			return "Mintkey SSH bastion. Sessions are recorded and audited per policy.\r\n"
		},
	}
	s.sshConfig.AddHostKey(hostKey)

	// Create auth handler
	s.authHandler, err = auth.NewHandler(cfg)
	if err != nil {
		return nil, fmt.Errorf("failed to create auth handler: %w", err)
	}

	return s, nil
}

// Start starts the SSH server.
func (s *Server) Start() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.running {
		return errors.New("server already running")
	}

	listener, err := net.Listen("tcp", s.cfg.SSHAddr)
	if err != nil {
		return fmt.Errorf("failed to listen on %s: %w", s.cfg.SSHAddr, err)
	}

	s.listener = listener
	s.running = true

	go s.acceptLoop()

	return nil
}

// Shutdown gracefully shuts down the SSH server.
func (s *Server) Shutdown(ctx context.Context) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.running {
		return nil
	}

	slog.Info("shutting down SSH server", "active_sessions", s.sessionMgr.ActiveCount())

	// Close listener to stop accepting new connections
	if s.listener != nil {
		s.listener.Close()
	}

	// Signal shutdown
	close(s.shutdownCh)

	// Wait for active sessions to complete or context timeout
	done := make(chan struct{})
	go func() {
		s.sessionMgr.WaitForAllSessions()
		close(done)
	}()

	select {
	case <-done:
		slog.Info("all sessions completed")
	case <-ctx.Done():
		slog.Warn("shutdown timeout, forcing session termination")
		s.sessionMgr.TerminateAllSessions()
	}

	s.running = false
	return nil
}

// HealthHandler handles health check requests.
func (s *Server) HealthHandler(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	running := s.running
	s.mu.Unlock()

	if !running {
		w.WriteHeader(http.StatusServiceUnavailable)
		if _, err := w.Write([]byte("shutting down")); err != nil {
			slog.Debug("HealthHandler: write error", "error", err)
		}
		return
	}

	w.WriteHeader(http.StatusOK)
	if _, err := w.Write([]byte("ok")); err != nil {
		slog.Debug("HealthHandler: write error", "error", err)
	}
}

// MetricsHandler handles Prometheus metrics requests.
func (s *Server) MetricsHandler(w http.ResponseWriter, r *http.Request) {
	promhttp.Handler().ServeHTTP(w, r)
}

// ActiveSessions returns the number of active SSH sessions.
func (s *Server) ActiveSessions() int {
	return s.sessionMgr.ActiveCount()
}

func (s *Server) acceptLoop() {
	for {
		conn, err := s.listener.Accept()
		if err != nil {
			select {
			case <-s.shutdownCh:
				return // Shutdown requested
			default:
				slog.Error("failed to accept connection", "error", err)
				continue
			}
		}

		// Rate limiting (B20): token-bucket check. Allow() is non-blocking;
		// excess connections are dropped early before they consume goroutine resources.
		if !s.limiter.Allow() {
			slog.Warn("ssh.connection.rate_limited: dropping connection",
				"remote_addr", conn.RemoteAddr(),
			)
			conn.Close()
			continue
		}

		// Concurrent-handshake semaphore (B20): acquire before handing off.
		// Non-blocking try; if full, drop the connection.
		select {
		case s.sem <- struct{}{}:
			// acquired
		default:
			slog.Warn("ssh.connection.rate_limited: handshake semaphore full, dropping connection",
				"remote_addr", conn.RemoteAddr(),
			)
			conn.Close()
			continue
		}

		go func(c net.Conn) {
			defer func() { <-s.sem }() // release semaphore after handshake completes
			s.handleConnection(c)
		}(conn)
	}
}

func (s *Server) handleConnection(conn net.Conn) {
	defer conn.Close()

	// Perform SSH handshake
	sshConn, chans, reqs, err := ssh.NewServerConn(conn, s.sshConfig)
	if err != nil {
		slog.Debug("SSH handshake failed", "error", err, "remote_addr", conn.RemoteAddr())
		return
	}
	defer sshConn.Close()

	// Get session context from auth
	sessionCtx := sshConn.Permissions.Extensions["session_context"]
	if sessionCtx == "" {
		slog.Error("no session context in SSH connection", "user", sshConn.User())
		return
	}

	slog.Info("SSH connection established",
		"user", sshConn.User(),
		"remote_addr", conn.RemoteAddr(),
	)

	// Handle global requests — reject port-forward/streamlocal, discard the rest.
	go s.handleGlobalRequests(reqs)

	// Handle channels — only "session" is allowed.
	for newChannel := range chans {
		go s.handleChannel(sshConn, newChannel, sessionCtx)
	}
}

// handleGlobalRequests processes the server-level SSH request stream.
// Port-forwarding and streamlocal requests are explicitly rejected with audit.
// Keepalive requests get a polite "no" without audit noise.
// Everything else is discarded.
func (s *Server) handleGlobalRequests(reqs <-chan *ssh.Request) {
	for req := range reqs {
		if req == nil {
			continue
		}

		if req.Type == "keepalive@openssh.com" {
			// Reply false — don't audit (noisy and expected from some clients).
			if req.WantReply {
				_ = req.Reply(false, nil)
			}
			continue
		}

		if deniedGlobalRequests[req.Type] {
			slog.Info("ssh.global_request.denied",
				"request_type", req.Type,
			)
			if req.WantReply {
				_ = req.Reply(false, nil)
			}
			continue
		}

		// Discard anything else silently.
		if req.WantReply {
			_ = req.Reply(false, nil)
		}
	}
}

func (s *Server) handleChannel(sshConn *ssh.ServerConn, newChannel ssh.NewChannel, sessionCtx string) {
	chanType := newChannel.ChannelType()

	// Channel-type denylist (B5/B6): reject everything except "session".
	if chanType != "session" {
		user, remoteAddr := "<unknown>", "<unknown>"
		if sshConn != nil {
			user = sshConn.User()
			remoteAddr = sshConn.RemoteAddr().String()
		}
		slog.Info("ssh.channel.denied",
			"channel_type", chanType,
			"user", user,
			"remote_addr", remoteAddr,
		)
		if err := newChannel.Reject(ssh.Prohibited, "Mintkey SSH bastion: channel type not permitted"); err != nil {
			slog.Debug("channel reject error", "error", err)
		}
		return
	}

	channel, requests, err := newChannel.Accept()
	if err != nil {
		slog.Error("failed to accept channel", "error", err)
		return
	}
	defer channel.Close()

	// Create session
	sess, err := s.sessionMgr.CreateSession(sessionCtx, sshConn, channel)
	if err != nil {
		slog.Error("failed to create session", "error", err)
		if _, werr := channel.Stderr().Write([]byte(fmt.Sprintf("Error: %v\n", err))); werr != nil {
			slog.Debug("failed to write error to channel stderr", "error", werr)
		}
		return
	}
	defer s.sessionMgr.DestroySession(sess.ID)

	// Handle session requests (pty, shell, exec, etc.)
	for req := range requests {
		// Explicitly reject agent-forwarding channel requests (B5).
		if req.Type == "auth-agent-req@openssh.com" {
			connUser := "<unknown>"
			if sshConn != nil {
				connUser = sshConn.User()
			}
			slog.Info("ssh.channel.denied",
				"channel_type", "session",
				"request_type", req.Type,
				"user", connUser,
			)
			if req.WantReply {
				_ = req.Reply(false, nil)
			}
			continue
		}

		if err := sess.HandleRequest(req); err != nil {
			slog.Error("session request failed", "error", err, "type", req.Type)
			if req.WantReply {
				_ = req.Reply(false, nil)
			}
			continue
		}

		if req.WantReply {
			_ = req.Reply(true, nil)
		}
	}
}

func (s *Server) passwordCallback(conn ssh.ConnMetadata, password []byte) (*ssh.Permissions, error) {
	ctx, err := s.authHandler.AuthenticateJWT(conn.User(), password)
	if err != nil {
		// Observable auth failure (do NOT log the presented password/JWT bytes).
		metrics.RecordAuthFailure("jwt")
		slog.Warn("ssh.auth.failed", "method", "jwt", "user", conn.User(), "reason", err)
		return nil, fmt.Errorf("authentication failed")
	}

	return &ssh.Permissions{
		Extensions: map[string]string{
			"session_context": ctx.Serialize(),
		},
	}, nil
}

func (s *Server) publicKeyCallback(conn ssh.ConnMetadata, key ssh.PublicKey) (*ssh.Permissions, error) {
	ctx, err := s.authHandler.AuthenticatePublicKey(conn.User(), key)
	if err != nil {
		// SSH clients routinely offer a public key before falling back to
		// password, and pubkey auth is not wired (vault-backed CA), so the
		// "unsupported" rejection is expected on nearly every connection. Log it
		// at Debug and do NOT count it, so AuthFailures{public_key} stays a
		// genuine signal; reserve Warn + the metric for real key-verification
		// failures once pubkey auth is wired. Never log the key material.
		if strings.Contains(err.Error(), "ssh.auth.pubkey.unsupported") {
			slog.Debug("ssh.auth.pubkey.unsupported", "user", conn.User())
		} else {
			metrics.RecordAuthFailure("public_key")
			slog.Warn("ssh.auth.failed", "method", "public_key", "user", conn.User(), "reason", err)
		}
		return nil, fmt.Errorf("authentication failed")
	}

	return &ssh.Permissions{
		Extensions: map[string]string{
			"session_context": ctx.Serialize(),
		},
	}, nil
}

func (s *Server) loadOrGenerateHostKey() (ssh.Signer, error) {
	// Try to load existing key
	if data, err := os.ReadFile(s.cfg.HostKeyPath); err == nil {
		signer, err := ssh.ParsePrivateKey(data)
		if err != nil {
			return nil, fmt.Errorf("failed to parse host key: %w", err)
		}
		slog.Info("loaded host key", "path", s.cfg.HostKeyPath)
		return signer, nil
	}

	// Generate new key if allowed
	if !s.cfg.HostKeyGenerate {
		return nil, fmt.Errorf("host key not found at %s and generation disabled", s.cfg.HostKeyPath)
	}

	slog.Info("generating new host key", "path", s.cfg.HostKeyPath)

	// Generate Ed25519 key
	_, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return nil, fmt.Errorf("failed to generate Ed25519 key: %w", err)
	}

	// Marshal to OpenSSH format
	pemBlock, err := ssh.MarshalPrivateKey(priv, "")
	if err != nil {
		return nil, fmt.Errorf("failed to marshal private key: %w", err)
	}

	pemData := pem.EncodeToMemory(pemBlock)

	// Write to file
	if err := os.WriteFile(s.cfg.HostKeyPath, pemData, 0600); err != nil {
		return nil, fmt.Errorf("failed to write host key: %w", err)
	}

	signer, err := ssh.NewSignerFromKey(priv)
	if err != nil {
		return nil, fmt.Errorf("failed to create signer: %w", err)
	}

	return signer, nil
}
