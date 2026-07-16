// Package recording handles SSH session recording in asciicast v2 format.
package recording

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"hash"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// Recorder records SSH session I/O in asciicast v2 format.
// On Close() it flushes, computes a SHA-256 digest of the entire .cast file,
// writes a sidecar <sessionID>.cast.sha256 file, and returns the digest.
type Recorder struct {
	file      *os.File
	hasher    hash.Hash // accumulates over every byte written
	sessionID string
	startTime time.Time
	width     int
	height    int
	mu        sync.Mutex
	closed    bool
	storagePath string
}

// NewRecorder creates a new session recorder.
func NewRecorder(storagePath, sessionID string, width, height int) (*Recorder, error) {
	// Create storage directory if it doesn't exist
	if err := os.MkdirAll(storagePath, 0755); err != nil {
		return nil, fmt.Errorf("failed to create storage directory: %w", err)
	}

	// Create recording file
	filename := filepath.Join(storagePath, sessionID+".cast")
	file, err := os.Create(filename)
	if err != nil {
		return nil, fmt.Errorf("failed to create recording file: %w", err)
	}

	recorder := &Recorder{
		file:        file,
		hasher:      sha256.New(),
		sessionID:   sessionID,
		startTime:   time.Now(),
		width:       width,
		height:      height,
		storagePath: storagePath,
	}

	// Write header
	if err := recorder.writeHeader(); err != nil {
		file.Close()
		os.Remove(filename)
		return nil, fmt.Errorf("failed to write header: %w", err)
	}

	return recorder, nil
}

// WriteOutput writes output data to the recording.
func (r *Recorder) WriteOutput(data []byte) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.closed {
		return fmt.Errorf("recorder is closed")
	}

	elapsed := time.Since(r.startTime).Seconds()

	event := []interface{}{
		elapsed,
		"o", // output
		string(data),
	}

	line, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("failed to marshal event: %w", err)
	}

	line = append(line, '\n')

	if _, err := r.writeBytes(line); err != nil {
		return fmt.Errorf("failed to write event: %w", err)
	}

	return nil
}

// WriteInput writes input data to the recording.
func (r *Recorder) WriteInput(data []byte) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.closed {
		return fmt.Errorf("recorder is closed")
	}

	elapsed := time.Since(r.startTime).Seconds()

	event := []interface{}{
		elapsed,
		"i", // input
		string(data),
	}

	line, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("failed to marshal event: %w", err)
	}

	line = append(line, '\n')

	if _, err := r.writeBytes(line); err != nil {
		return fmt.Errorf("failed to write event: %w", err)
	}

	return nil
}

// Close closes the recorder, computes the SHA-256 digest of the recording file,
// writes a sidecar .cast.sha256 file, and returns the hex digest string.
// Calling Close() on an already-closed Recorder returns ("", nil) idempotently.
func (r *Recorder) Close() (digest string, err error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.closed {
		return "", nil
	}

	r.closed = true

	// Flush and close the file.
	if closeErr := r.file.Close(); closeErr != nil {
		return "", fmt.Errorf("failed to close recording file: %w", closeErr)
	}

	// The hasher has accumulated all bytes written through writeBytes.
	digest = "sha256:" + hex.EncodeToString(r.hasher.Sum(nil))

	// Write sidecar file: <sessionID>.cast.sha256
	sidecarPath := filepath.Join(r.storagePath, r.sessionID+".cast.sha256")
	sidecarContent := digest + "  " + r.sessionID + ".cast\n"
	if writeErr := os.WriteFile(sidecarPath, []byte(sidecarContent), 0644); writeErr != nil {
		// Non-fatal: log but don't fail; the digest is still returned to caller
		// so the audit event can carry it.
		fmt.Fprintf(os.Stderr, "recording: failed to write sidecar %s: %v\n", sidecarPath, writeErr)
	}

	return digest, nil
}

// Digest returns the current (partial) digest without closing the recorder.
// Only useful before Close(); after Close() use the returned value from Close().
func (r *Recorder) Digest() string {
	r.mu.Lock()
	defer r.mu.Unlock()
	return "sha256:" + hex.EncodeToString(r.hasher.Sum(nil))
}

// writeBytes writes to both the file and the SHA-256 hasher.
// Caller must hold r.mu.
func (r *Recorder) writeBytes(data []byte) (int, error) {
	n, err := r.file.Write(data)
	if n > 0 {
		r.hasher.Write(data[:n])
	}
	return n, err
}

func (r *Recorder) writeHeader() error {
	header := map[string]interface{}{
		"version":   2,
		"width":     r.width,
		"height":    r.height,
		"timestamp": r.startTime.Unix(),
		"env": map[string]string{
			"SHELL": "/bin/bash",
			"TERM":  "xterm-256color",
		},
	}

	line, err := json.Marshal(header)
	if err != nil {
		return fmt.Errorf("failed to marshal header: %w", err)
	}

	line = append(line, '\n')

	if _, err := r.writeBytes(line); err != nil {
		return fmt.Errorf("failed to write header: %w", err)
	}

	return nil
}

// RecordingWriter wraps an io.Writer and records all writes.
type RecordingWriter struct {
	writer   io.Writer
	recorder *Recorder
}

// NewRecordingWriter creates a new recording writer.
func NewRecordingWriter(writer io.Writer, recorder *Recorder) *RecordingWriter {
	return &RecordingWriter{
		writer:   writer,
		recorder: recorder,
	}
}

// Write writes data to both the underlying writer and the recorder.
func (w *RecordingWriter) Write(data []byte) (int, error) {
	// Record the output
	if err := w.recorder.WriteOutput(data); err != nil {
		slog.Debug("failed to record output", "error", err)
	}

	// Write to underlying writer
	return w.writer.Write(data)
}

// RecordingReader wraps an io.Reader and records all reads.
type RecordingReader struct {
	reader   io.Reader
	recorder *Recorder
}

// NewRecordingReader creates a new recording reader.
func NewRecordingReader(reader io.Reader, recorder *Recorder) *RecordingReader {
	return &RecordingReader{
		reader:   reader,
		recorder: recorder,
	}
}

// Read reads data from the underlying reader and records it.
func (r *RecordingReader) Read(data []byte) (int, error) {
	n, err := r.reader.Read(data)
	if n > 0 {
		// Record the input
		if recErr := r.recorder.WriteInput(data[:n]); recErr != nil {
			slog.Debug("failed to record input", "error", recErr)
		}
	}
	return n, err
}
