// Package session manages SSH sessions in the SSH Proxy.
package session

import (
	"context"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/mintkey/mintkey/packages/go/ulid"
	"github.com/mintkey/mintkey/services/ssh-proxy/internal/bridge"
	"github.com/mintkey/mintkey/services/ssh-proxy/internal/recording"
	"golang.org/x/crypto/ssh"
)

// BackendConnector abstracts backend SSH connectivity so the session package
// does not import the backend package (which imports session — cycle).
type BackendConnector interface {
	// Connect dials the backend target and returns an *ssh.Client plus the raw
	// PEM bytes of the credential used. Callers MUST zero the PEM slice after
	// they have finished with it (defense-in-depth; the parsed signer's
	// in-memory copy cannot be fully zeroed by the caller).
	Connect(ctx context.Context, sessCtx *SessionContext, targetAddr string) (*ssh.Client, []byte, error)
}

// AuditEmitter abstracts audit event emission so the session package does not
// import the audit package (which imports session — cycle).
type AuditEmitter interface {
	EmitSessionStarted(ctx context.Context, sessCtx *SessionContext, sessionID, sourceIP string) error
	EmitSessionEnded(ctx context.Context, sessCtx *SessionContext, sessionID string, durationSeconds, bytesSent, bytesReceived int64) error
	EmitSessionExec(ctx context.Context, sessCtx *SessionContext, sessionID, command string, exitCode int) error
	EmitSessionSFTP(ctx context.Context, sessCtx *SessionContext, sessionID, operation, path string) error
}

// CommandFilter abstracts command filtering to avoid importing the filter
// package in tests that do not need it.
type CommandFilter interface {
	IsAllowed(command string) bool
}

// Deps holds the optional external dependencies for session handlers.
// All fields are optional; nil means the corresponding capability is disabled.
type Deps struct {
	Connector          BackendConnector
	AuditEmitter       AuditEmitter
	Filter             CommandFilter
	RecordingPath      string        // directory for asciicast recordings; empty → no recording
	SessionTimeout     time.Duration // 0 = no max-duration limit
	SessionIdleTimeout time.Duration // 0 = no idle-timeout
}

// Manager tracks active SSH sessions and enforces per-agent limits.
type Manager struct {
	maxPerAgent   int
	sessions      map[string]*Session // session_id -> Session
	agentSessions map[string]int      // agent_id -> count
	mu            sync.RWMutex
	wg            sync.WaitGroup
	deps          Deps
}

// NewManager creates a new session manager.
func NewManager(maxPerAgent int) *Manager {
	return &Manager{
		maxPerAgent:   maxPerAgent,
		sessions:      make(map[string]*Session),
		agentSessions: make(map[string]int),
	}
}

// NewManagerWithDeps creates a new session manager with handler dependencies.
func NewManagerWithDeps(maxPerAgent int, deps Deps) *Manager {
	return &Manager{
		maxPerAgent:   maxPerAgent,
		sessions:      make(map[string]*Session),
		agentSessions: make(map[string]int),
		deps:          deps,
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

	// Use a fresh ULID as the session ID (not the agent_id).
	sessionID := ulid.New("session_")

	// Build the session lifecycle context.  If SessionTimeout > 0 we wrap with
	// WithTimeout so the context is cancelled automatically; otherwise we use a
	// plain cancellable context (Terminate() will call the cancel).
	var (
		sessCtxBase context.Context
		cancelFn    context.CancelFunc
	)
	if m.deps.SessionTimeout > 0 {
		sessCtxBase, cancelFn = context.WithTimeout(context.Background(), m.deps.SessionTimeout)
	} else {
		sessCtxBase, cancelFn = context.WithCancel(context.Background())
	}

	sess := &Session{
		ID:         sessionID,
		Context:    ctx,
		SSHConn:    sshConn,
		Channel:    channel,
		StartTime:  time.Now(),
		cancelFunc: cancelFn,
		sessionCtx: sessCtxBase,
		deps:       m.deps,
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

	// sessionCtx is the lifecycle context for this session. It is cancelled
	// when the max-duration (SessionTimeout) or idle timer (SessionIdleTimeout)
	// fires, propagating closure to all running goroutines.
	sessionCtx context.Context

	// Handler dependencies (optional; nil = capability disabled).
	deps Deps

	// pendingPTY is set by handlePTYRequest and consumed by handleShellRequest /
	// handleExecRequest. Guarded by mu.
	pendingPTY *bridge.PTYRequest

	// backendSess is the upstream SSH session, set after a successful backend
	// connect. Used by handleWindowChangeRequest and handleSignalRequest.
	// Guarded by mu.
	backendSess *ssh.Session
}

// SetCancelFunc replaces the no-op cancel function installed at construction.
// Called by the goroutine that owns the session lifetime.
func (s *Session) SetCancelFunc(fn context.CancelFunc) {
	s.mu.Lock()
	s.cancelFunc = fn
	s.mu.Unlock()
}

// SetDeps injects handler dependencies after construction.
// Used in tests and when wiring the server after CreateSession.
func (s *Session) SetDeps(d Deps) {
	s.mu.Lock()
	s.deps = d
	s.mu.Unlock()
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
	if s.cancelFunc != nil {
		s.cancelFunc()
	}

	// Close channel (may be nil in unit tests or if session setup failed).
	if s.Channel != nil {
		s.Channel.Close()
	}

	slog.Info("session terminated", "session_id", s.ID)
}

// ---------------------------------------------------------------------------
// Request handlers
// ---------------------------------------------------------------------------

func (s *Session) handlePTYRequest(req *ssh.Request) error {
	ptyReq, err := bridge.ParsePTYRequest(req.Payload)
	if err != nil {
		slog.Warn("failed to parse pty-req payload", "session_id", s.ID, "error", err)
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}

	s.mu.Lock()
	s.pendingPTY = ptyReq
	s.mu.Unlock()

	slog.Debug("pty-req stored",
		"session_id", s.ID,
		"term", ptyReq.Term,
		"cols", ptyReq.Width,
		"rows", ptyReq.Height,
	)

	if req.WantReply {
		req.Reply(true, nil)
	}
	return nil
}

// handleShellRequest starts an interactive shell session.
// NOTE: the command filter (deps.Filter) is NOT applied here. The filter is
// exec-only; per-keystroke command extraction from an interactive shell stream
// is out of scope for this proxy implementation.
func (s *Session) handleShellRequest(req *ssh.Request) error {
	s.mu.Lock()
	ptyReq := s.pendingPTY
	s.mu.Unlock()

	if ptyReq == nil {
		slog.Warn("shell request without prior pty-req, rejecting",
			"session_id", s.ID)
		s.emitAudit(func(ctx context.Context) {
			if s.deps.AuditEmitter != nil {
				// Emit as a failed exec with a synthetic command label.
				s.deps.AuditEmitter.EmitSessionExec(ctx, s.Context, s.ID, "shell:no_pty", -1)
			}
		})
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}

	if req.WantReply {
		req.Reply(true, nil)
	}

	// Run the shell in a goroutine so we don't block the request loop.
	go s.runShell(ptyReq)
	return nil
}

func (s *Session) runShell(ptyReq *bridge.PTYRequest) {
	ctx := s.sessionCtxOrBackground()
	start := time.Now()

	connector := s.deps.Connector
	if connector == nil {
		slog.Error("no backend connector configured", "session_id", s.ID)
		s.Channel.Stderr().Write([]byte("Error: backend not configured\r\n"))
		s.Channel.Close()
		return
	}

	// Determine target address: fall back to TargetAddr from context if the
	// credential doesn't supply one (C3 wires it on the vault side).
	targetAddr := s.Context.TargetAddr

	client, pemBytes, err := connector.Connect(ctx, s.Context, targetAddr)
	// Zero PEM bytes immediately after use (defense-in-depth).
	defer func() {
		for i := range pemBytes {
			pemBytes[i] = 0
		}
	}()
	if err != nil {
		slog.Error("shell: failed to connect to backend",
			"session_id", s.ID, "error", err)
		s.Channel.Stderr().Write([]byte(fmt.Sprintf("Error: %v\r\n", err)))
		s.Channel.Close()
		return
	}
	defer client.Close()

	backendSess, err := client.NewSession()
	if err != nil {
		slog.Error("shell: failed to open backend session",
			"session_id", s.ID, "error", err)
		s.Channel.Stderr().Write([]byte(fmt.Sprintf("Error: %v\r\n", err)))
		s.Channel.Close()
		return
	}
	defer backendSess.Close()

	// Store backend session for window-change / signal forwarding.
	s.mu.Lock()
	s.backendSess = backendSess
	s.mu.Unlock()
	defer func() {
		s.mu.Lock()
		s.backendSess = nil
		s.mu.Unlock()
	}()

	// Request PTY on the backend.
	if err := backendSess.RequestPty(ptyReq.Term, int(ptyReq.Height), int(ptyReq.Width), ssh.TerminalModes{}); err != nil {
		slog.Error("shell: backend pty request failed",
			"session_id", s.ID, "error", err)
		s.Channel.Stderr().Write([]byte(fmt.Sprintf("Error: %v\r\n", err)))
		s.Channel.Close()
		return
	}

	// Set up optional recording.
	var recorder *recording.Recorder
	if s.deps.RecordingPath != "" {
		recorder, err = recording.NewRecorder(s.deps.RecordingPath, s.ID, int(ptyReq.Width), int(ptyReq.Height))
		if err != nil {
			slog.Warn("shell: failed to create recorder (continuing without recording)",
				"session_id", s.ID, "error", err)
		} else {
			defer func(rec *recording.Recorder, sid string) {
				if digest, closeErr := rec.Close(); closeErr != nil {
					slog.Warn("shell: failed to close recorder", "session_id", sid, "error", closeErr)
				} else if digest != "" {
					slog.Info("shell: recording closed", "session_id", sid, "recording_sha256", digest)
				}
			}(recorder, s.ID)
		}
	}

	// Wire stdio.
	backendStdin, err := backendSess.StdinPipe()
	if err != nil {
		slog.Error("shell: failed to get backend stdin pipe", "session_id", s.ID, "error", err)
		s.Channel.Close()
		return
	}
	backendStdout, err := backendSess.StdoutPipe()
	if err != nil {
		slog.Error("shell: failed to get backend stdout pipe", "session_id", s.ID, "error", err)
		s.Channel.Close()
		return
	}
	backendStderr, err := backendSess.StderrPipe()
	if err != nil {
		slog.Error("shell: failed to get backend stderr pipe", "session_id", s.ID, "error", err)
		s.Channel.Close()
		return
	}

	if err := backendSess.Shell(); err != nil {
		slog.Error("shell: backend shell start failed", "session_id", s.ID, "error", err)
		s.Channel.Stderr().Write([]byte(fmt.Sprintf("Error: %v\r\n", err)))
		s.Channel.Close()
		return
	}

	// Emit session.started audit event.
	if s.deps.AuditEmitter != nil {
		sourceIP := ""
		if s.SSHConn != nil {
			sourceIP = s.SSHConn.RemoteAddr().String()
		}
		if err := s.deps.AuditEmitter.EmitSessionStarted(ctx, s.Context, s.ID, sourceIP); err != nil {
			slog.Debug("failed to emit session.started", "session_id", s.ID, "error", err)
		}
	}

	slog.Info("shell: started", "session_id", s.ID)

	// Set up idle-timeout reset function (no-op if idle timeout is disabled).
	var resetIdle func() = func() {}
	if s.deps.SessionIdleTimeout > 0 {
		sessCancel := s.cancelFunc // capture current cancel
		resetIdle = startIdleTimer(ctx, s.deps.SessionIdleTimeout, sessCancel)
	}

	// Bridge bidirectional I/O.
	var wg sync.WaitGroup
	var bytesRecv int64

	// agent → backend stdin (fire-and-forget; unblocked when s.Channel is closed).
	go func() {
		var w io.Writer = &idleResetWriter{w: backendStdin, resetIdle: resetIdle}
		if recorder != nil {
			w = &recordingWriter{w: w, rec: recorder, input: true}
		}
		io.Copy(w, s.Channel)
		backendStdin.Close()
	}()

	// backend stdout → agent: tracked so we can flush before close.
	wg.Add(1)
	go func() {
		defer wg.Done()
		var r io.Reader = &idleResetReader{r: backendStdout, resetIdle: resetIdle}
		if recorder != nil {
			r = &recordingReader{r: r, rec: recorder}
		}
		n, _ := io.Copy(s.Channel, r)
		bytesRecv += n
	}()

	// backend stderr → agent stderr
	wg.Add(1)
	go func() {
		defer wg.Done()
		io.Copy(s.Channel.Stderr(), backendStderr)
	}()

	// Wait for backend to exit (or session context cancellation), flush output.
	doneCh := make(chan struct{})
	go func() {
		backendSess.Wait()
		close(doneCh)
	}()
	select {
	case <-doneCh:
	case <-ctx.Done():
		slog.Info("shell: session context expired (timeout/idle), closing backend",
			"session_id", s.ID)
		backendSess.Close()
		if s.deps.AuditEmitter != nil {
			s.deps.AuditEmitter.EmitSessionExec(context.Background(), s.Context, s.ID, "shell:timeout", -1)
		}
	}
	wg.Wait()
	s.Channel.Close()

	duration := time.Since(start)

	// Emit session.ended audit event.
	if s.deps.AuditEmitter != nil {
		if err := s.deps.AuditEmitter.EmitSessionEnded(ctx, s.Context, s.ID,
			int64(duration.Seconds()), 0, bytesRecv); err != nil {
			slog.Debug("failed to emit session.ended", "session_id", s.ID, "error", err)
		}
	}

	slog.Info("shell: ended",
		"session_id", s.ID,
		"duration", duration,
		"bytes_recv", bytesRecv,
	)
}

func (s *Session) handleExecRequest(req *ssh.Request) error {
	// Parse SSH exec payload: [uint32 len][command bytes].
	if len(req.Payload) < 4 {
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}
	cmdLen := binary.BigEndian.Uint32(req.Payload[0:4])
	if int(4+cmdLen) > len(req.Payload) {
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}
	command := string(req.Payload[4 : 4+cmdLen])

	slog.Debug("exec request", "session_id", s.ID, "command", command)

	// Apply command filter.
	if s.deps.Filter != nil && !s.deps.Filter.IsAllowed(command) {
		slog.Info("exec: command blocked by filter",
			"session_id", s.ID, "command", command)
		if s.deps.AuditEmitter != nil {
			s.deps.AuditEmitter.EmitSessionExec(context.Background(), s.Context, s.ID, command, -2)
		}
		if req.WantReply {
			req.Reply(false, nil)
		}
		s.Channel.Stderr().Write([]byte("Error: command blocked by policy\r\n"))
		s.Channel.Close()
		return nil
	}

	s.mu.Lock()
	ptyReq := s.pendingPTY
	s.mu.Unlock()

	if req.WantReply {
		req.Reply(true, nil)
	}

	go s.runExec(command, ptyReq)
	return nil
}

func (s *Session) runExec(command string, ptyReq *bridge.PTYRequest) {
	ctx := s.sessionCtxOrBackground()
	start := time.Now()

	connector := s.deps.Connector
	if connector == nil {
		slog.Error("no backend connector configured", "session_id", s.ID)
		s.Channel.Stderr().Write([]byte("Error: backend not configured\r\n"))
		s.Channel.Close()
		return
	}

	targetAddr := s.Context.TargetAddr

	client, pemBytes, err := connector.Connect(ctx, s.Context, targetAddr)
	defer func() {
		for i := range pemBytes {
			pemBytes[i] = 0
		}
	}()
	if err != nil {
		slog.Error("exec: failed to connect to backend",
			"session_id", s.ID, "error", err)
		s.Channel.Stderr().Write([]byte(fmt.Sprintf("Error: %v\r\n", err)))
		s.Channel.Close()
		return
	}
	defer client.Close()

	backendSess, err := client.NewSession()
	if err != nil {
		slog.Error("exec: failed to open backend session",
			"session_id", s.ID, "error", err)
		s.Channel.Stderr().Write([]byte(fmt.Sprintf("Error: %v\r\n", err)))
		s.Channel.Close()
		return
	}
	defer backendSess.Close()

	s.mu.Lock()
	s.backendSess = backendSess
	s.mu.Unlock()
	defer func() {
		s.mu.Lock()
		s.backendSess = nil
		s.mu.Unlock()
	}()

	// Apply PTY only if the client requested one (ssh -t style).
	if ptyReq != nil {
		if err := backendSess.RequestPty(ptyReq.Term, int(ptyReq.Height), int(ptyReq.Width), ssh.TerminalModes{}); err != nil {
			slog.Warn("exec: backend pty request failed, continuing without pty",
				"session_id", s.ID, "error", err)
		}
	}

	// Set up optional recording.
	var recorder *recording.Recorder
	if s.deps.RecordingPath != "" {
		w, h := 80, 24
		if ptyReq != nil {
			w, h = int(ptyReq.Width), int(ptyReq.Height)
		}
		recorder, err = recording.NewRecorder(s.deps.RecordingPath, s.ID+"-exec", w, h)
		if err != nil {
			slog.Warn("exec: failed to create recorder (continuing without recording)",
				"session_id", s.ID, "error", err)
		} else {
			defer func(rec *recording.Recorder, sid string) {
				if digest, closeErr := rec.Close(); closeErr != nil {
					slog.Warn("exec: failed to close recorder", "session_id", sid, "error", closeErr)
				} else if digest != "" {
					slog.Info("exec: recording closed", "session_id", sid, "recording_sha256", digest)
				}
			}(recorder, s.ID)
		}
	}

	// Wire stdio.
	backendStdin, err := backendSess.StdinPipe()
	if err != nil {
		slog.Error("exec: failed to get backend stdin pipe", "session_id", s.ID, "error", err)
		s.Channel.Close()
		return
	}
	backendStdout, err := backendSess.StdoutPipe()
	if err != nil {
		slog.Error("exec: failed to get backend stdout pipe", "session_id", s.ID, "error", err)
		s.Channel.Close()
		return
	}
	backendStderr, err := backendSess.StderrPipe()
	if err != nil {
		slog.Error("exec: failed to get backend stderr pipe", "session_id", s.ID, "error", err)
		s.Channel.Close()
		return
	}

	if err := backendSess.Start(command); err != nil {
		slog.Error("exec: backend start failed",
			"session_id", s.ID, "command", command, "error", err)
		s.Channel.Stderr().Write([]byte(fmt.Sprintf("Error: %v\r\n", err)))
		s.Channel.Close()
		return
	}

	// Emit exec audit event.
	if s.deps.AuditEmitter != nil {
		if err := s.deps.AuditEmitter.EmitSessionExec(ctx, s.Context, s.ID, command, 0); err != nil {
			slog.Debug("failed to emit session.exec", "session_id", s.ID, "error", err)
		}
	}

	slog.Info("exec: started", "session_id", s.ID, "command", command)

	// outWg tracks the agent-facing output goroutines (backend → agent).
	// We must wait for these before closing the agent channel so no data is lost.
	// The stdin goroutine (agent → backend) is fire-and-forget from the
	// perspective of the clean-shutdown path; it will unblock once s.Channel
	// is closed below.
	var outWg sync.WaitGroup
	var bytesSentAtomic atomic.Int64
	var bytesRecv int64

	// agent → backend stdin (fire-and-forget w.r.t. exit sequencing)
	go func() {
		var w io.Writer = backendStdin
		if recorder != nil {
			w = &recordingWriter{w: backendStdin, rec: recorder, input: true}
		}
		n, _ := io.Copy(w, s.Channel)
		bytesSentAtomic.Add(n)
		backendStdin.Close()
	}()

	outWg.Add(1)
	go func() {
		defer outWg.Done()
		var r io.Reader = backendStdout
		if recorder != nil {
			r = &recordingReader{r: backendStdout, rec: recorder}
		}
		n, _ := io.Copy(s.Channel, r)
		bytesRecv += n
	}()

	outWg.Add(1)
	go func() {
		defer outWg.Done()
		io.Copy(s.Channel.Stderr(), backendStderr)
	}()

	waitErr := backendSess.Wait()
	// Wait for all backend→agent output to flush before closing the channel.
	outWg.Wait()

	exitCode := 0
	var exitErr *ssh.ExitError
	if errors.As(waitErr, &exitErr) {
		exitCode = exitErr.ExitStatus()
	} else if waitErr != nil {
		exitCode = 1
	}

	// Forward exit status and close the agent channel. Closing it will also
	// unblock the stdin-copy goroutine (which reads from s.Channel).
	exitPayload := make([]byte, 4)
	binary.BigEndian.PutUint32(exitPayload, uint32(exitCode))
	s.Channel.SendRequest("exit-status", false, exitPayload)
	s.Channel.Close()

	duration := time.Since(start)

	// Emit exec.ended audit event with real exit code.
	if s.deps.AuditEmitter != nil {
		if err := s.deps.AuditEmitter.EmitSessionExec(ctx, s.Context, s.ID, command, exitCode); err != nil {
			slog.Debug("failed to emit session.exec ended", "session_id", s.ID, "error", err)
		}
		if err := s.deps.AuditEmitter.EmitSessionEnded(ctx, s.Context, s.ID,
			int64(duration.Seconds()), bytesSentAtomic.Load(), bytesRecv); err != nil {
			slog.Debug("failed to emit session.ended", "session_id", s.ID, "error", err)
		}
	}

	slog.Info("exec: ended",
		"session_id", s.ID,
		"command", command,
		"exit_code", exitCode,
		"duration", duration,
	)
}

func (s *Session) handleSubsystemRequest(req *ssh.Request) error {
	if len(req.Payload) < 4 {
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}
	nameLen := binary.BigEndian.Uint32(req.Payload[0:4])
	if int(4+nameLen) > len(req.Payload) {
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}
	subsystem := string(req.Payload[4 : 4+nameLen])

	slog.Debug("subsystem request", "session_id", s.ID, "subsystem", subsystem)

	if subsystem != "sftp" {
		slog.Info("subsystem denied", "session_id", s.ID, "subsystem", subsystem)
		if s.deps.AuditEmitter != nil {
			s.deps.AuditEmitter.EmitSessionSFTP(context.Background(), s.Context, s.ID, "denied", subsystem)
		}
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}

	// SFTP subsystem.
	if s.deps.Connector == nil {
		slog.Error("no backend connector configured for sftp", "session_id", s.ID)
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}

	ctx := context.Background()
	targetAddr := s.Context.TargetAddr

	client, pemBytes, err := s.deps.Connector.Connect(ctx, s.Context, targetAddr)
	defer func() {
		for i := range pemBytes {
			pemBytes[i] = 0
		}
	}()
	if err != nil {
		slog.Error("sftp: failed to connect to backend",
			"session_id", s.ID, "error", err)
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}

	backendSess, err := client.NewSession()
	if err != nil {
		client.Close()
		slog.Error("sftp: failed to open backend session",
			"session_id", s.ID, "error", err)
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}

	// Ask the backend to start sftp subsystem.
	ok, err := backendSess.SendRequest("subsystem", true, req.Payload)
	if err != nil || !ok {
		backendSess.Close()
		client.Close()
		slog.Warn("sftp: backend rejected sftp subsystem",
			"session_id", s.ID, "err", err, "ok", ok)
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}

	if req.WantReply {
		req.Reply(true, nil)
	}

	// Bridge agent channel ↔ backend stdin/stdout.
	// NOTE: ssh.Session does not implement ssh.Channel, so we use pipe adapters.
	// A richer SFTPFactory-based path that passes audit-wrapped channel objects
	// is deferred to a later chunk once the SFTP audit integration is finalised.
	go func() {
		defer backendSess.Close()
		defer client.Close()

		backendStdin, _ := backendSess.StdinPipe()
		backendStdout, _ := backendSess.StdoutPipe()

		var wg sync.WaitGroup
		wg.Add(2)
		go func() {
			defer wg.Done()
			io.Copy(backendStdin, s.Channel)
			backendStdin.Close()
		}()
		go func() {
			defer wg.Done()
			io.Copy(s.Channel, backendStdout)
		}()
		wg.Wait()
		s.Channel.Close()
		slog.Info("sftp: session ended", "session_id", s.ID)
	}()

	return nil
}

// allowedEnvPrefixes is the whitelist of environment variable name prefixes
// that are forwarded to the backend. All others are rejected.
var allowedEnvPrefixes = []string{"LANG", "LC_", "TERM"}

func (s *Session) handleEnvRequest(req *ssh.Request) error {
	// Parse env payload: [uint32 nameLen][name][uint32 valueLen][value].
	if len(req.Payload) < 4 {
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}

	nameLen := binary.BigEndian.Uint32(req.Payload[0:4])
	if int(4+nameLen) > len(req.Payload) {
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}
	name := string(req.Payload[4 : 4+nameLen])

	// Check against allowlist.
	allowed := false
	for _, prefix := range allowedEnvPrefixes {
		if name == prefix || strings.HasPrefix(name, prefix) {
			allowed = true
			break
		}
	}

	if !allowed {
		slog.Info("env: variable denied by policy",
			"session_id", s.ID,
			"var_name", name, // intentionally NOT logging value
		)
		if s.deps.AuditEmitter != nil {
			// Re-use SFTP slot to carry the var name as path; a dedicated
			// EmitEnvDenied would be cleaner but is not in the current Emitter
			// interface — adding it is out of scope for this chunk.
			s.deps.AuditEmitter.EmitSessionSFTP(context.Background(), s.Context, s.ID, "env.denied", name)
		}
		if req.WantReply {
			req.Reply(false, nil)
		}
		return nil
	}

	slog.Debug("env: variable accepted",
		"session_id", s.ID,
		"var_name", name,
	)

	if req.WantReply {
		req.Reply(true, nil)
	}
	return nil
}

func (s *Session) handleWindowChangeRequest(req *ssh.Request) error {
	s.mu.Lock()
	backendSess := s.backendSess
	s.mu.Unlock()

	if backendSess != nil {
		winReq, err := bridge.ParseWindowChangeRequest(req.Payload)
		if err == nil {
			if err := backendSess.WindowChange(int(winReq.Height), int(winReq.Width)); err != nil {
				slog.Debug("window-change: failed to forward to backend",
					"session_id", s.ID, "error", err)
			}
		}
	}

	// No reply for window-change (RFC 4254 §6.7).
	return nil
}

func (s *Session) handleSignalRequest(req *ssh.Request) error {
	s.mu.Lock()
	backendSess := s.backendSess
	s.mu.Unlock()

	sigReq, err := bridge.ParseSignalRequest(req.Payload)
	if err != nil {
		slog.Debug("signal: failed to parse payload", "session_id", s.ID, "error", err)
		return nil
	}

	if backendSess != nil {
		if err := backendSess.Signal(ssh.Signal(sigReq.Signal)); err != nil {
			slog.Debug("signal: failed to forward to backend",
				"session_id", s.ID, "signal", sigReq.Signal, "error", err)
		}
		slog.Debug("signal forwarded", "session_id", s.ID, "signal", sigReq.Signal)
		if s.deps.AuditEmitter != nil {
			// Re-use exec slot with a synthetic "signal:<name>" command string.
			s.deps.AuditEmitter.EmitSessionExec(context.Background(), s.Context, s.ID,
				"signal:"+sigReq.Signal, 0)
		}
	}

	// No reply for signal (RFC 4254 §6.9).
	return nil
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

func (s *Session) emitAudit(fn func(ctx context.Context)) {
	fn(context.Background())
}

// sessionCtxOrBackground returns the session lifecycle context if it has been
// set (i.e. when CreateSession wired a timeout), otherwise context.Background().
func (s *Session) sessionCtxOrBackground() context.Context {
	s.mu.Lock()
	ctx := s.sessionCtx
	s.mu.Unlock()
	if ctx == nil {
		return context.Background()
	}
	return ctx
}

// idleResetWriter wraps an io.Writer and resets an idle timer on each write.
type idleResetWriter struct {
	w         io.Writer
	resetIdle func()
}

func (w *idleResetWriter) Write(p []byte) (int, error) {
	w.resetIdle()
	return w.w.Write(p)
}

// idleResetReader wraps an io.Reader and resets an idle timer on each read.
type idleResetReader struct {
	r         io.Reader
	resetIdle func()
}

func (r *idleResetReader) Read(p []byte) (int, error) {
	n, err := r.r.Read(p)
	if n > 0 {
		r.resetIdle()
	}
	return n, err
}

// startIdleTimer starts a goroutine that cancels cancelFn if no activity
// resets the timer within idleTimeout. The returned resetFn is thread-safe.
// The goroutine exits when ctx is done or when the timer fires and cancels.
func startIdleTimer(ctx context.Context, idleTimeout time.Duration, cancelFn context.CancelFunc) (resetFn func()) {
	resetCh := make(chan struct{}, 1)

	go func() {
		timer := time.NewTimer(idleTimeout)
		defer timer.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-resetCh:
				if !timer.Stop() {
					select {
					case <-timer.C:
					default:
					}
				}
				timer.Reset(idleTimeout)
			case <-timer.C:
				cancelFn()
				return
			}
		}
	}()

	return func() {
		select {
		case resetCh <- struct{}{}:
		default:
		}
	}
}

// recordingWriter wraps a writer and records all writes as input events.
type recordingWriter struct {
	w     io.Writer
	rec   *recording.Recorder
	input bool
}

func (rw *recordingWriter) Write(p []byte) (int, error) {
	if rw.input {
		rw.rec.WriteInput(p)
	} else {
		rw.rec.WriteOutput(p)
	}
	return rw.w.Write(p)
}

// recordingReader wraps a reader and records all reads as output events.
type recordingReader struct {
	r   io.Reader
	rec *recording.Recorder
}

func (rr *recordingReader) Read(p []byte) (int, error) {
	n, err := rr.r.Read(p)
	if n > 0 {
		rr.rec.WriteOutput(p[:n])
	}
	return n, err
}

// ---------------------------------------------------------------------------
// SessionContext
// ---------------------------------------------------------------------------

// SessionContext holds the authenticated session metadata.
type SessionContext struct {
	TenantID   string
	AgentID    string
	ServiceID  string
	AuthMethod string // "jwt" or "api_key"
	// TargetAddr is the backend "host:port" resolved at authentication time.
	// May be empty until C3 wires the vault-adapter extensions; session
	// handlers fall back to "" which lets backend.Connector use the credential's
	// own TargetAddress field.
	TargetAddr string
}

// Serialize serializes the session context to a string.
func (c *SessionContext) Serialize() string {
	return fmt.Sprintf("%s|%s|%s|%s", c.TenantID, c.AgentID, c.ServiceID, c.AuthMethod)
}

// ParseSessionContext parses a serialized session context.
func ParseSessionContext(s string) (*SessionContext, error) {
	parts := strings.SplitN(s, "|", 4)
	if len(parts) != 4 {
		return nil, fmt.Errorf("invalid session context format")
	}
	for _, p := range parts {
		if p == "" {
			return nil, fmt.Errorf("invalid session context format")
		}
	}

	return &SessionContext{
		TenantID:   parts[0],
		AgentID:    parts[1],
		ServiceID:  parts[2],
		AuthMethod: parts[3],
	}, nil
}
