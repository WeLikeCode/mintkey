package config_test

import (
	"os"
	"reflect"
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/config"
)

// scrubPatternsField reads config.Config.ScrubPatterns through reflection so
// this test compiles before the field exists (design section Interfaces).
func scrubPatternsField(t *testing.T, cfg *config.Config) bool {
	t.Helper()

	field := reflect.ValueOf(cfg).Elem().FieldByName("ScrubPatterns")
	if !field.IsValid() {
		t.Fatal("config.Config has no ScrubPatterns field; cannot read MINTKEY_PROXY_SCRUB_PATTERNS")
	}
	if field.Kind() != reflect.Bool {
		t.Fatalf("config.Config.ScrubPatterns has kind %s, want bool", field.Kind())
	}
	return field.Bool()
}

// TestScrubPatternsFromEnvironment_C_9048f97b covers the scenario "the setting
// is read from the environment": strconv.ParseBool decides the value and an
// unset, empty or unparsable value is false.
func TestScrubPatternsFromEnvironment_C_9048f97b(t *testing.T) {
	cases := []struct {
		name  string
		value string
		set   bool
		want  bool
	}{
		{"unset", "", false, false},
		{"empty", "", true, false},
		{"true", "true", true, true},
		{"upper", "TRUE", true, true},
		{"one", "1", true, true},
		{"false", "false", true, false},
		{"zero", "0", true, false},
		{"yes", "yes", true, false},
		{"banana", "banana", true, false},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if tc.set {
				t.Setenv("MINTKEY_PROXY_SCRUB_PATTERNS", tc.value)
			} else if err := os.Unsetenv("MINTKEY_PROXY_SCRUB_PATTERNS"); err != nil {
				t.Fatalf("unset MINTKEY_PROXY_SCRUB_PATTERNS: %v", err)
			}

			cfg := config.Load()
			if got := scrubPatternsField(t, cfg); got != tc.want {
				t.Fatalf("ScrubPatterns = %v with MINTKEY_PROXY_SCRUB_PATTERNS=%q, want %v", got, tc.value, tc.want)
			}
		})
	}
}
