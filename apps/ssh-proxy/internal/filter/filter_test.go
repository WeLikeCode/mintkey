package filter

import (
	"testing"
)

func TestNewFilter(t *testing.T) {
	tests := []struct {
		name     string
		mode     Mode
		patterns []string
		wantErr  bool
	}{
		{
			name:     "valid allowlist",
			mode:     ModeAllowlist,
			patterns: []string{"^ls$", "^cat "},
			wantErr:  false,
		},
		{
			name:     "valid denylist",
			mode:     ModeDenylist,
			patterns: []string{"^rm ", "^sudo "},
			wantErr:  false,
		},
		{
			name:     "empty patterns",
			mode:     ModeAllowlist,
			patterns: []string{},
			wantErr:  false,
		},
		{
			name:     "invalid mode",
			mode:     Mode("invalid"),
			patterns: []string{},
			wantErr:  true,
		},
		{
			name:     "invalid regex",
			mode:     ModeAllowlist,
			patterns: []string{"[invalid"},
			wantErr:  true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := NewFilter(tt.mode, tt.patterns)
			if (err != nil) != tt.wantErr {
				t.Errorf("NewFilter() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestFilter_IsAllowed(t *testing.T) {
	tests := []struct {
		name     string
		mode     Mode
		patterns []string
		command  string
		want     bool
	}{
		{
			name:     "allowlist - command allowed",
			mode:     ModeAllowlist,
			patterns: []string{"^ls", "^cat "},
			command:  "ls -la",
			want:     true,
		},
		{
			name:     "allowlist - command denied",
			mode:     ModeAllowlist,
			patterns: []string{"^ls", "^cat "},
			command:  "rm -rf /",
			want:     false,
		},
		{
			name:     "denylist - command allowed",
			mode:     ModeDenylist,
			patterns: []string{"^rm ", "^sudo "},
			command:  "ls -la",
			want:     true,
		},
		{
			name:     "denylist - command denied",
			mode:     ModeDenylist,
			patterns: []string{"^rm ", "^sudo "},
			command:  "rm -rf /",
			want:     false,
		},
		{
			name:     "empty allowlist - denies all",
			mode:     ModeAllowlist,
			patterns: []string{},
			command:  "ls",
			want:     false,
		},
		{
			name:     "empty denylist - allows all",
			mode:     ModeDenylist,
			patterns: []string{},
			command:  "rm -rf /",
			want:     true,
		},
		{
			name:     "regex pattern matching",
			mode:     ModeAllowlist,
			patterns: []string{"^ls\\s+(-[la]+\\s+)*[\\w/]+$"},
			command:  "ls -la /tmp",
			want:     true,
		},
		{
			name:     "regex pattern not matching",
			mode:     ModeAllowlist,
			patterns: []string{"^ls\\s+(-[la]+\\s+)*[\\w/]+$"},
			command:  "ls -la /tmp; rm -rf /",
			want:     false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			f, err := NewFilter(tt.mode, tt.patterns)
			if err != nil {
				t.Fatalf("NewFilter() error = %v", err)
			}

			got := f.IsAllowed(tt.command)
			if got != tt.want {
				t.Errorf("IsAllowed(%q) = %v, want %v", tt.command, got, tt.want)
			}
		})
	}
}

func TestFilter_Check(t *testing.T) {
	f, err := NewFilter(ModeDenylist, []string{"^rm ", "^sudo "})
	if err != nil {
		t.Fatalf("NewFilter() error = %v", err)
	}

	// Allowed command
	if err := f.Check("ls -la"); err != nil {
		t.Errorf("Check(ls -la) error = %v, want nil", err)
	}

	// Blocked command
	err = f.Check("rm -rf /")
	if err == nil {
		t.Error("Check(rm -rf /) error = nil, want error")
	}

	// Verify error type
	if _, ok := err.(*CommandBlockedError); !ok {
		t.Errorf("Check() error type = %T, want *CommandBlockedError", err)
	}
}

func TestCommandBlockedError(t *testing.T) {
	err := &CommandBlockedError{
		Command: "rm -rf /",
		Mode:    ModeDenylist,
	}

	msg := err.Error()
	if msg != "command blocked by filter" {
		t.Errorf("Error() = %q, want 'command blocked by filter'", msg)
	}
}

func TestParseCommand(t *testing.T) {
	tests := []struct {
		name    string
		command string
		want    string
	}{
		{
			name:    "simple command",
			command: "ls",
			want:    "ls",
		},
		{
			name:    "command with args",
			command: "ls -la /tmp",
			want:    "ls",
		},
		{
			name:    "command with leading whitespace",
			command: "  ls -la",
			want:    "ls",
		},
		{
			name:    "command with trailing whitespace",
			command: "ls -la  ",
			want:    "ls",
		},
		{
			name:    "empty command",
			command: "",
			want:    "",
		},
		{
			name:    "whitespace only",
			command: "   ",
			want:    "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ParseCommand(tt.command)
			if got != tt.want {
				t.Errorf("ParseCommand(%q) = %q, want %q", tt.command, got, tt.want)
			}
		})
	}
}

func TestParseCommandWithArgs(t *testing.T) {
	tests := []struct {
		name      string
		command   string
		wantCmd   string
		wantArgs  []string
	}{
		{
			name:     "simple command",
			command:  "ls",
			wantCmd:  "ls",
			wantArgs: nil,
		},
		{
			name:     "command with args",
			command:  "ls -la /tmp",
			wantCmd:  "ls",
			wantArgs: []string{"-la", "/tmp"},
		},
		{
			name:     "empty command",
			command:  "",
			wantCmd:  "",
			wantArgs: nil,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cmd, args := ParseCommandWithArgs(tt.command)
			if cmd != tt.wantCmd {
				t.Errorf("command = %q, want %q", cmd, tt.wantCmd)
			}
			if len(args) != len(tt.wantArgs) {
				t.Errorf("args length = %d, want %d", len(args), len(tt.wantArgs))
			}
			for i, arg := range args {
				if i < len(tt.wantArgs) && arg != tt.wantArgs[i] {
					t.Errorf("args[%d] = %q, want %q", i, arg, tt.wantArgs[i])
				}
			}
		})
	}
}

func TestParser_Parse(t *testing.T) {
	parser := NewParser()

	tests := []struct {
		name    string
		command string
		want    []string
		wantErr bool
	}{
		{
			name:    "simple command",
			command: "ls -la",
			want:    []string{"ls", "-la"},
			wantErr: false,
		},
		{
			name:    "command with single quotes",
			command: "echo 'hello world'",
			want:    []string{"echo", "hello world"},
			wantErr: false,
		},
		{
			name:    "command with double quotes",
			command: `echo "hello world"`,
			want:    []string{"echo", "hello world"},
			wantErr: false,
		},
		{
			name:    "command with escaped space",
			command: `echo hello\ world`,
			want:    []string{"echo", "hello world"},
			wantErr: false,
		},
		{
			name:    "command with environment variable",
			command: "VAR=value ls",
			want:    []string{"VAR=value", "ls"},
			wantErr: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := parser.Parse(tt.command)
			if (err != nil) != tt.wantErr {
				t.Errorf("Parse() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr {
				if len(got) != len(tt.want) {
					t.Errorf("Parse() length = %d, want %d", len(got), len(tt.want))
					return
				}
				for i, token := range got {
					if token != tt.want[i] {
						t.Errorf("Parse()[%d] = %q, want %q", i, token, tt.want[i])
					}
				}
			}
		})
	}
}

func TestParser_ExtractCommand(t *testing.T) {
	parser := NewParser()

	tests := []struct {
		name   string
		tokens []string
		want   string
	}{
		{
			name:   "simple command",
			tokens: []string{"ls", "-la"},
			want:   "ls",
		},
		{
			name:   "command with env var",
			tokens: []string{"VAR=value", "ls", "-la"},
			want:   "ls",
		},
		{
			name:   "only env vars",
			tokens: []string{"VAR1=value1", "VAR2=value2"},
			want:   "",
		},
		{
			name:   "empty tokens",
			tokens: []string{},
			want:   "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := parser.ExtractCommand(tt.tokens)
			if got != tt.want {
				t.Errorf("ExtractCommand() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestParser_HasPipe(t *testing.T) {
	parser := NewParser()

	if !parser.HasPipe("ls | grep foo") {
		t.Error("HasPipe() should return true for command with pipe")
	}

	if parser.HasPipe("ls -la") {
		t.Error("HasPipe() should return false for command without pipe")
	}
}

func TestParser_HasRedirect(t *testing.T) {
	parser := NewParser()

	if !parser.HasRedirect("ls > file.txt") {
		t.Error("HasRedirect() should return true for command with redirect")
	}

	if !parser.HasRedirect("cat < file.txt") {
		t.Error("HasRedirect() should return true for command with input redirect")
	}

	if parser.HasRedirect("ls -la") {
		t.Error("HasRedirect() should return false for command without redirect")
	}
}

func TestParser_HasBackground(t *testing.T) {
	parser := NewParser()

	if !parser.HasBackground("sleep 10 &") {
		t.Error("HasBackground() should return true for background command")
	}

	if parser.HasBackground("sleep 10") {
		t.Error("HasBackground() should return false for foreground command")
	}
}

func TestParser_SplitPipeline(t *testing.T) {
	parser := NewParser()

	parts := parser.SplitPipeline("ls | grep foo | wc -l")
	if len(parts) != 3 {
		t.Errorf("SplitPipeline() length = %d, want 3", len(parts))
	}

	expected := []string{"ls", "grep foo", "wc -l"}
	for i, part := range parts {
		if part != expected[i] {
			t.Errorf("SplitPipeline()[%d] = %q, want %q", i, part, expected[i])
		}
	}
}

func TestIsShellBuiltin(t *testing.T) {
	if !IsShellBuiltin("cd") {
		t.Error("IsShellBuiltin(cd) should return true")
	}

	if !IsShellBuiltin("echo") {
		t.Error("IsShellBuiltin(echo) should return true")
	}

	if IsShellBuiltin("ls") {
		t.Error("IsShellBuiltin(ls) should return false")
	}
}

func TestIsDangerousCommand(t *testing.T) {
	if !IsDangerousCommand("rm") {
		t.Error("IsDangerousCommand(rm) should return true")
	}

	if !IsDangerousCommand("sudo") {
		t.Error("IsDangerousCommand(sudo) should return true")
	}

	if IsDangerousCommand("ls") {
		t.Error("IsDangerousCommand(ls) should return false")
	}
}
