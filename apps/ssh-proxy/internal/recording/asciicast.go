package recording

import (
	"encoding/json"
	"fmt"
	"io"
	"time"
)

// AsciicastHeader represents the header of an asciicast v2 file.
type AsciicastHeader struct {
	Version   int               `json:"version"`
	Width     int               `json:"width"`
	Height    int               `json:"height"`
	Timestamp int64             `json:"timestamp"`
	Env       map[string]string `json:"env,omitempty"`
	Title     string            `json:"title,omitempty"`
}

// AsciicastEvent represents an event in an asciicast v2 file.
type AsciicastEvent struct {
	Time float64     `json:"-"` // Stored as first element of array
	Type string      `json:"-"` // "o" for output, "i" for input
	Data interface{} `json:"-"` // String data
}

// AsciicastWriter writes asciicast v2 format.
type AsciicastWriter struct {
	writer    io.Writer
	startTime time.Time
}

// NewAsciicastWriter creates a new asciicast writer.
func NewAsciicastWriter(w io.Writer, width, height int) (*AsciicastWriter, error) {
	now := time.Now()

	aw := &AsciicastWriter{
		writer:    w,
		startTime: now,
	}

	// Write header
	header := AsciicastHeader{
		Version:   2,
		Width:     width,
		Height:    height,
		Timestamp: now.Unix(),
		Env: map[string]string{
			"SHELL": "/bin/bash",
			"TERM":  "xterm-256color",
		},
	}

	if err := aw.writeJSON(header); err != nil {
		return nil, fmt.Errorf("failed to write header: %w", err)
	}

	return aw, nil
}

// WriteOutput writes an output event.
func (aw *AsciicastWriter) WriteOutput(data []byte) error {
	elapsed := time.Since(aw.startTime).Seconds()
	return aw.writeEvent(elapsed, "o", string(data))
}

// WriteInput writes an input event.
func (aw *AsciicastWriter) WriteInput(data []byte) error {
	elapsed := time.Since(aw.startTime).Seconds()
	return aw.writeEvent(elapsed, "i", string(data))
}

// WriteResize writes a resize event.
func (aw *AsciicastWriter) WriteResize(width, height int) error {
	elapsed := time.Since(aw.startTime).Seconds()
	return aw.writeEvent(elapsed, "r", fmt.Sprintf("%dx%d", width, height))
}

func (aw *AsciicastWriter) writeEvent(elapsed float64, eventType string, data interface{}) error {
	event := []interface{}{elapsed, eventType, data}
	return aw.writeJSON(event)
}

func (aw *AsciicastWriter) writeJSON(v interface{}) error {
	line, err := json.Marshal(v)
	if err != nil {
		return fmt.Errorf("failed to marshal JSON: %w", err)
	}

	line = append(line, '\n')

	if _, err := aw.writer.Write(line); err != nil {
		return fmt.Errorf("failed to write line: %w", err)
	}

	return nil
}

// AsciicastReader reads asciicast v2 format.
type AsciicastReader struct {
	reader io.Reader
	header *AsciicastHeader
}

// NewAsciicastReader creates a new asciicast reader.
func NewAsciicastReader(r io.Reader) (*AsciicastReader, error) {
	ar := &AsciicastReader{
		reader: r,
	}

	// Read header
	decoder := json.NewDecoder(r)
	var header AsciicastHeader
	if err := decoder.Decode(&header); err != nil {
		return nil, fmt.Errorf("failed to read header: %w", err)
	}

	if header.Version != 2 {
		return nil, fmt.Errorf("unsupported asciicast version: %d", header.Version)
	}

	ar.header = &header
	return ar, nil
}

// Header returns the asciicast header.
func (ar *AsciicastReader) Header() *AsciicastHeader {
	return ar.header
}

// ReadEvent reads the next event.
func (ar *AsciicastReader) ReadEvent() (*AsciicastEvent, error) {
	decoder := json.NewDecoder(ar.reader)

	var raw []interface{}
	if err := decoder.Decode(&raw); err != nil {
		if err == io.EOF {
			return nil, err
		}
		return nil, fmt.Errorf("failed to decode event: %w", err)
	}

	if len(raw) < 3 {
		return nil, fmt.Errorf("invalid event format: expected 3 elements, got %d", len(raw))
	}

	timeVal, ok := raw[0].(float64)
	if !ok {
		return nil, fmt.Errorf("invalid time value: expected float64")
	}

	typeVal, ok := raw[1].(string)
	if !ok {
		return nil, fmt.Errorf("invalid type value: expected string")
	}

	return &AsciicastEvent{
		Time: timeVal,
		Type: typeVal,
		Data: raw[2],
	}, nil
}
