// Package session manages SSH sessions in the SSH Proxy.
package session

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"sync/atomic"
	"time"

	"github.com/mintkey/mintkey/packages/go/ulid"
	"golang.org/x/crypto/ssh"
)

// Manager tracks active SSH sessions and enforces per-agent limits.
type Manager struct {
	maxPerAgent   int
	sessions      map[string]*Session // session_id -> Session
	agentSessions map[string]int      // agent_id -> count
	mu            sync.RWMutex
	wg            sync.WaitGroup
}

// NewManager creates a new session manager.
func NewManager(maxPerAgent int) *Manager {
	return &Manager{
		maxPerAgent:   maxPerAgent,
		sessions:      make(map[string]*Session),
		agentSessions: make(map[string]int),
	}
}

// CreateSession creates a new SSH session.
func (m *Manager) CreateSession(sessionCtx string, sshConn *ssh.ServerConn, channel ssh.Channel) (*Session, error) {
	// Parse session context
	ctx, err := ParseSessionContext(sessionCtx)
	if err != nil {
		return nil, fmt.Errorf("failed to parse session context: %w", err)
	}

	m.mu.Lock()
	defer m.mu.Unlock()

	// Check per-agent limit
	if count := m.agentSessions[ctx.AgentID]; count >= m.maxPerAgent {
		return nil, fmt.Errorf("max concurrent sessions (%d) reached for agent %s", m.maxPerAgent, ctx.AgentID)
	}

	// Create session
	sessionID := ulid.New("session_")
	sess := &Session{
		ID:         sessionID,
		Context:    ctx,
		SSHConn:    sshConn,
		Channel:    channel,
		StartTime:  time.Now(),
		cancelFunc: func() {}, // Will be set by session goroutine
	}

	m.sessions[sessionID] = sess
	m.agentSessions[ctx.AgentID]++
	m.wg.Add(1)

	slog.Info("session created",
		"session_id", sessionID,
		"agent_id", ctx.AgentID,
		"service_id", ctx.ServiceID,
		"tenant_id", ctx.TenantID,
	)

	return sess, nil
}

// DestroySession removes a session from tracking.
func (m *Manager) DestroySession(sessionID string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	sess, ok := m.sessions[sessionID]
	if !ok {
		return
	}

	// Decrement agent session count
	if count := m.agentSessions[sess.Context.AgentID]; count > 0 {
		m.agentSessions[sess.Context.AgentID]--
		if m.agentSessions[sess.Context.AgentID] == 0 {
			delete(m.agentSessions, sess.Context.AgentID)
		}
	}

	delete(m.sessions, sessionID)
	m.wg.Done()

	slog.Info("session destroyed",
		"session_id", sessionID,
		"duration", time.Since(sess.StartTime),
	)
}

// GetSession returns a session by ID.
func (m *Manager) GetSession(sessionID string) (*Session, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	sess, ok := m.sessions[sessionID]
	return sess, ok
}

// ActiveCount returns the number of active sessions.
func (m *Manager) ActiveCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()

	return len(m.sessions)
}

// WaitForAllSessions waits for all sessions to complete.
func (m *Manager) WaitForAllSessions() {
	m.wg.Wait()
}

// TerminateAllSessions forcefully terminates all active sessions.
func (m *Manager) TerminateAllSessions() {
	m.mu.Lock()
	sessions := make([]*Session, 0, len(m.sessions))
	for _, sess := range m.sessions {
		sessions = append(sessions, sess)
	}
	m.mu.Unlock()

	for _, sess := range sessions {
		sess.Terminate()
	}
}

// TerminateAgentSessions terminates all sessions for a specific agent.
func (m *Manager) TerminateAgentSessions(agentID string) {
	m.mu.Lock()
	var sessions []*Session
	for _, sess := range m.sessions {
		if sess.Context.AgentID == agentID {
			sessions = append(sessions, sess)
		}
	}
	m.mu.Unlock()

	for _, sess := range sessions {
		sess.Terminate()
	}
}

// Session represents an active SSH session.
type Session struct {
	ID         string
	Context    *SessionContext
	SSHConn    *ssh.ServerConn
	Channel    ssh.Channel
	StartTime  time.Time
	BytesSent  atomic.Int64
	BytesRecv  atomic.Int64
	cancelFunc context.CancelFunc
	mu         sync.Mutex
	terminated bool
}

// HandleRequest handles an SSH session request (pty, shell, exec, etc.).
func (s *Session) HandleRequest(req *ssh.Request) error {
	s.mu.Lock()
	if s.terminated {
		s.mu.Unlock()
		return errors.New("session terminated")
	}
	s.mu.Unlock()

	switch req.Type {
	case "pty-req":
		return s.handlePTYRequest(req)
	case "shell":
		return s.handleShellRequest(req)
	case "exec":
		return s.handleExecRequest(req)
	case "subsystem":
		return s.handleSubsystemRequest(req)
	case "env":
		return s.handleEnvRequest(req)
	case "window-change":
		return s.handleWindowChangeRequest(req)
	case "signal":
		return s.handleSignalRequest(req)
	default:
		slog.Debug("unknown session request", "type", req.Type)
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}
}

// Terminate forcefully terminates the session.
func (s *Session) Terminate() {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.terminated {
		return
	}

	s.terminated = true
	s.cancelFunc()

	// Close channel
	s.Channel.Close()

	slog.Info("session terminated", "session_id", s.ID)
}

func (s *Session) handlePTYRequest(req *ssh.Request) error {
	// Parse PTY request
	// TODO: Implement PTY handling
	slog.Debug("pty-req received", "session_id", s.ID)
	if req.WantReply {
		req.Reply(true, nil)
	}
	return nil
}

func (s *Session) handleShellRequest(req *ssh.Request) error {
	// Start interactive shell
	// TODO: Implement shell handling
	slog.Debug("shell request received", "session_id", s.ID)
	if req.WantReply {
		req.Reply(true, nil)
	}
	return nil
}

func (s *Session) handleExecRequest(req *ssh.Request) error {
	// Parse command from payload
	// TODO: Implement exec handling with command filtering
	slog.Debug("exec request received", "session_id", s.ID, "payload", string(req.Payload))
	if req.WantReply {
		req.Reply(true, nil)
	}
	return nil
}

func (s *Session) handleSubsystemRequest(req *ssh.Request) error {
	// Parse subsystem name
	// TODO: Implement subsystem handling (e.g., sftp)
	slog.Debug("subsystem request received", "session_id", s.ID, "payload", string(req.Payload))
	if req.WantReply {
		req.Reply(false, nil)
	}
	return nil
}

func (s *Session) handleEnvRequest(req *ssh.Request) error {
	// Set environment variable
	// TODO: Implement env handling
	slog.Debug("env request received", "session_id", s.ID)
	if req.WantReply {
		req.Reply(true, nil)
	}
	return nil
}

func (s *Session) handleWindowChangeRequest(req *ssh.Request) error {
	// Handle window size change
	// TODO: Implement window change handling
	slog.Debug("window-change request received", "session_id", s.ID)
	// No reply needed for window-change
	return nil
}

func (s *Session) handleSignalRequest(req *ssh.Request) error {
	// Forward signal to backend
	// TODO: Implement signal handling
	slog.Debug("signal request received", "session_id", s.ID)
	// No reply needed for signal
	return nil
}

// SessionContext holds the authenticated session metadata.
type SessionContext struct {
	TenantID   string
	AgentID    string
	ServiceID  string
	AuthMethod string // "jwt" or "api_key"
}

// Serialize serializes the session context to a string.
func (c *SessionContext) Serialize() string {
	return fmt.Sprintf("%s|%s|%s|%s", c.TenantID, c.AgentID, c.ServiceID, c.AuthMethod)
}

// ParseSessionContext parses a serialized session context.
func ParseSessionContext(s string) (*SessionContext, error) {
	var tenantID, agentID, serviceID, authMethod string
	n, err := fmt.Sscanf(s, "%s|%s|%s|%s", &tenantID, &agentID, &serviceID, &authMethod)
	if err != nil || n != 4 {
		return nil, fmt.Errorf("invalid session context format")
	}

	return &SessionContext{
		TenantID:   tenantID,
		AgentID:    agentID,
		ServiceID:  serviceID,
		AuthMethod: authMethod,
	}, nil
}
