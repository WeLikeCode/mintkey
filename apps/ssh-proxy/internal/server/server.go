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
	"sync"
	"time"

	"github.com/WeLikeCode/mintkey/apps/ssh-proxy/internal/auth"
	"github.com/WeLikeCode/mintkey/apps/ssh-proxy/internal/config"
	"github.com/WeLikeCode/mintkey/apps/ssh-proxy/internal/session"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"golang.org/x/crypto/ssh"
)

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
}

// New creates a new SSH Proxy server.
func New(cfg *config.Config) (*Server, error) {
	s := &Server{
		cfg:        cfg,
		sessionMgr: session.NewManager(cfg.MaxConcurrentSessionsPerAgent),
		shutdownCh: make(chan struct{}),
	}

	// Load or generate host key
	hostKey, err := s.loadOrGenerateHostKey()
	if err != nil {
		return nil, fmt.Errorf("failed to load host key: %w", err)
	}

	// Create SSH server config
	s.sshConfig = &ssh.ServerConfig{
		PasswordCallback:  s.passwordCallback,
		PublicKeyCallback: s.publicKeyCallback,
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
		w.Write([]byte("shutting down"))
		return
	}

	w.WriteHeader(http.StatusOK)
	w.Write([]byte("ok"))
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

		go s.handleConnection(conn)
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

	// Handle global requests (e.g., keepalive)
	go ssh.DiscardRequests(reqs)

	// Handle channels
	for newChannel := range chans {
		go s.handleChannel(sshConn, newChannel, sessionCtx)
	}
}

func (s *Server) handleChannel(sshConn *ssh.ServerConn, newChannel ssh.NewChannel, sessionCtx string) {
	// Only accept session channels
	if newChannel.ChannelType() != "session" {
		newChannel.Reject(ssh.UnknownChannelType, "unknown channel type")
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
		channel.Stderr().Write([]byte(fmt.Sprintf("Error: %v\n", err)))
		return
	}
	defer s.sessionMgr.DestroySession(sess.ID)

	// Handle session requests (pty, shell, exec, etc.)
	for req := range requests {
		if err := sess.HandleRequest(req); err != nil {
			slog.Error("session request failed", "error", err, "type", req.Type)
			if req.WantReply {
				req.Reply(false, nil)
			}
			continue
		}

		if req.WantReply {
			req.Reply(true, nil)
		}
	}
}

func (s *Server) passwordCallback(conn ssh.ConnMetadata, password []byte) (*ssh.Permissions, error) {
	ctx, err := s.authHandler.AuthenticateJWT(conn.User(), password)
	if err != nil {
		slog.Debug("JWT auth failed", "user", conn.User(), "error", err)
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
		slog.Debug("public key auth failed", "user", conn.User(), "error", err)
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
