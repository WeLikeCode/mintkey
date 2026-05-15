package config_test

import (
	"os"
	"testing"

	"github.com/mintkey/mintkey/services/proxy-plugin/internal/config"
)

func TestLoadAudEnforcementDefaults(t *testing.T) {
	cases := []struct {
		env        string
		override   string
		want       config.AudEnforcement
	}{
		{"dev", "", config.AudEnforcementPermissive},
		{"", "", config.AudEnforcementPermissive},
		{"production", "", config.AudEnforcementStrict},
		{"production", "permissive", config.AudEnforcementPermissive},
		{"dev", "strict", config.AudEnforcementStrict},
		{"production", "strict", config.AudEnforcementStrict},
		{"dev", "garbage", config.AudEnforcementPermissive},
	}
	for _, tc := range cases {
		os.Setenv("MINTKEY_ENV", tc.env)
		if tc.override == "" {
			os.Unsetenv("MINTKEY_AUD_ENFORCEMENT")
		} else {
			os.Setenv("MINTKEY_AUD_ENFORCEMENT", tc.override)
		}
		cfg := config.Load()
		if cfg.AudEnforcement != tc.want {
			t.Errorf("env=%q override=%q: got %q, want %q", tc.env, tc.override, cfg.AudEnforcement, tc.want)
		}
	}
	os.Unsetenv("MINTKEY_ENV")
	os.Unsetenv("MINTKEY_AUD_ENFORCEMENT")
}
