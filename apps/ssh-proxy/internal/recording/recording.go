// Package recording handles SSH session recording in asciicast v2 format.
package recording

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// Recorder records SSH session I/O in asciicast v2 format.
type Recorder struct {
	file      *os.File
	sessionID string
	startTime time.Time
	width     int
	height    int
	mu        sync.Mutex
	closed    bool
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
		file:      file,
		sessionID: sessionID,
		startTime: time.Now(),
		width:     width,
		height:    height,
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

	if _, err := r.file.Write(line); err != nil {
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

	if _, err := r.file.Write(line); err != nil {
		return fmt.Errorf("failed to write event: %w", err)
	}

	return nil
}

// Close closes the recorder.
func (r *Recorder) Close() error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.closed {
		return nil
	}

	r.closed = true
	return r.file.Close()
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

	if _, err := r.file.Write(line); err != nil {
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
		// Log error but don't fail the write
		// slog.Debug("failed to record output", "error", err)
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
			// Log error but don't fail the read
			// slog.Debug("failed to record input", "error", recErr)
		}
	}
	return n, err
}
