package bridge

import (
	"testing"
)

func TestParsePTYRequest(t *testing.T) {
	tests := []struct {
		name    string
		payload []byte
		want    *PTYRequest
		wantErr bool
	}{
		{
			name: "valid PTY request",
			payload: func() []byte {
				term := "xterm-256color"
				payload := make([]byte, 4+len(term)+16+4)
				payload[0] = 0
				payload[1] = 0
				payload[2] = 0
				payload[3] = byte(len(term))
				copy(payload[4:], term)
				offset := 4 + len(term)
				// Width: 80
				payload[offset] = 0
				payload[offset+1] = 0
				payload[offset+2] = 0
				payload[offset+3] = 80
				// Height: 24
				payload[offset+4] = 0
				payload[offset+5] = 0
				payload[offset+6] = 0
				payload[offset+7] = 24
				// WidthPx: 0
				payload[offset+8] = 0
				payload[offset+9] = 0
				payload[offset+10] = 0
				payload[offset+11] = 0
				// HeightPx: 0
				payload[offset+12] = 0
				payload[offset+13] = 0
				payload[offset+14] = 0
				payload[offset+15] = 0
				// Modes length: 0
				payload[offset+16] = 0
				payload[offset+17] = 0
				payload[offset+18] = 0
				payload[offset+19] = 0
				return payload
			}(),
			want: &PTYRequest{
				Term:     "xterm-256color",
				Width:    80,
				Height:   24,
				WidthPx:  0,
				HeightPx: 0,
				Modes:    "",
			},
			wantErr: false,
		},
		{
			name:    "payload too short",
			payload: []byte{0, 0, 0},
			wantErr: true,
		},
		{
			name:    "empty payload",
			payload: []byte{},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParsePTYRequest(tt.payload)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParsePTYRequest() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr {
				if got.Term != tt.want.Term {
					t.Errorf("Term = %q, want %q", got.Term, tt.want.Term)
				}
				if got.Width != tt.want.Width {
					t.Errorf("Width = %d, want %d", got.Width, tt.want.Width)
				}
				if got.Height != tt.want.Height {
					t.Errorf("Height = %d, want %d", got.Height, tt.want.Height)
				}
			}
		})
	}
}

func TestParseWindowChangeRequest(t *testing.T) {
	tests := []struct {
		name    string
		payload []byte
		want    *WindowChangeRequest
		wantErr bool
	}{
		{
			name: "valid window change",
			payload: func() []byte {
				payload := make([]byte, 16)
				// Width: 120
				payload[0] = 0
				payload[1] = 0
				payload[2] = 0
				payload[3] = 120
				// Height: 40
				payload[4] = 0
				payload[5] = 0
				payload[6] = 0
				payload[7] = 40
				// WidthPx: 0
				payload[8] = 0
				payload[9] = 0
				payload[10] = 0
				payload[11] = 0
				// HeightPx: 0
				payload[12] = 0
				payload[13] = 0
				payload[14] = 0
				payload[15] = 0
				return payload
			}(),
			want: &WindowChangeRequest{
				Width:    120,
				Height:   40,
				WidthPx:  0,
				HeightPx: 0,
			},
			wantErr: false,
		},
		{
			name:    "payload too short",
			payload: []byte{0, 0, 0, 0, 0, 0, 0, 0},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseWindowChangeRequest(tt.payload)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseWindowChangeRequest() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr {
				if got.Width != tt.want.Width {
					t.Errorf("Width = %d, want %d", got.Width, tt.want.Width)
				}
				if got.Height != tt.want.Height {
					t.Errorf("Height = %d, want %d", got.Height, tt.want.Height)
				}
			}
		})
	}
}

func TestParseSignalRequest(t *testing.T) {
	tests := []struct {
		name    string
		payload []byte
		want    *SignalRequest
		wantErr bool
	}{
		{
			name: "valid signal request",
			payload: func() []byte {
				sig := "INT"
				payload := make([]byte, 4+len(sig))
				payload[0] = 0
				payload[1] = 0
				payload[2] = 0
				payload[3] = byte(len(sig))
				copy(payload[4:], sig)
				return payload
			}(),
			want: &SignalRequest{
				Signal: "INT",
			},
			wantErr: false,
		},
		{
			name:    "payload too short",
			payload: []byte{0, 0},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseSignalRequest(tt.payload)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseSignalRequest() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr && got.Signal != tt.want.Signal {
				t.Errorf("Signal = %q, want %q", got.Signal, tt.want.Signal)
			}
		})
	}
}

func TestParseExitStatusRequest(t *testing.T) {
	tests := []struct {
		name    string
		payload []byte
		want    *ExitStatusRequest
		wantErr bool
	}{
		{
			name: "valid exit status",
			payload: func() []byte {
				payload := make([]byte, 4)
				// Exit status: 0
				payload[0] = 0
				payload[1] = 0
				payload[2] = 0
				payload[3] = 0
				return payload
			}(),
			want: &ExitStatusRequest{
				ExitStatus: 0,
			},
			wantErr: false,
		},
		{
			name: "non-zero exit status",
			payload: func() []byte {
				payload := make([]byte, 4)
				// Exit status: 1
				payload[0] = 0
				payload[1] = 0
				payload[2] = 0
				payload[3] = 1
				return payload
			}(),
			want: &ExitStatusRequest{
				ExitStatus: 1,
			},
			wantErr: false,
		},
		{
			name:    "payload too short",
			payload: []byte{0, 0},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseExitStatusRequest(tt.payload)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseExitStatusRequest() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr && got.ExitStatus != tt.want.ExitStatus {
				t.Errorf("ExitStatus = %d, want %d", got.ExitStatus, tt.want.ExitStatus)
			}
		})
	}
}

func TestBridge_Stats(t *testing.T) {
	// Create a bridge with nil channels (we're only testing stats)
	b := &Bridge{
		bytesSent:     100,
		bytesReceived: 200,
	}

	sent, received := b.Stats()

	if sent != 100 {
		t.Errorf("Stats() sent = %d, want 100", sent)
	}

	if received != 200 {
		t.Errorf("Stats() received = %d, want 200", received)
	}
}
