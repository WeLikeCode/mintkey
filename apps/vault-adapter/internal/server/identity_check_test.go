package server

import (
	"bytes"
	"context"
	"fmt"
	"runtime"
	"slices"
	"testing"

	"github.com/mintkey/mintkey/services/vault-adapter/internal/store"
)

func newIdentityCheckVault(t *testing.T) *VaultService {
	t.Helper()

	st, err := store.New(":memory:")
	if err != nil {
		t.Fatalf("store.New: %v", err)
	}
	t.Cleanup(func() { _ = st.Close() })

	kek := make([]byte, 32)
	for i := range kek {
		kek[i] = byte(i + 1)
	}
	return NewVaultService(kek, st)
}

func identityCheckTotalAlloc() uint64 {
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	return m.TotalAlloc
}

func assertAllocUnderOneMiB(t *testing.T, before, after uint64) {
	t.Helper()
	if grew := after - before; grew >= 1<<20 {
		t.Fatalf("TotalAlloc grew by %d bytes, want below %d", grew, 1<<20)
	}
}

func TestValidateServiceIdentity_AllocatesUnderOneMiB_C_ca32998a(t *testing.T) {
	svc := newIdentityCheckVault(t)
	ctx := context.Background()

	token := bytes.Repeat([]byte{0x11}, 32)
	wrong := bytes.Repeat([]byte{0x22}, 32)
	scopes := []string{"vault.read", "vault.put"}
	if err := svc.RegisterServiceIdentity("svcid_cost", token, scopes); err != nil {
		t.Fatalf("RegisterServiceIdentity: %v", err)
	}

	before := identityCheckTotalAlloc()
	for i := 0; i < 10; i++ {
		got, ok := svc.ValidateServiceIdentity(ctx, "svcid_cost", token)
		if !ok || !slices.Equal(got, scopes) {
			t.Fatalf("right token: scopes = %v, ok = %v; want %v, true", got, ok, scopes)
		}
		if _, ok := svc.ValidateServiceIdentity(ctx, "svcid_cost", wrong); ok {
			t.Fatal("wrong token was accepted")
		}
		if _, ok := svc.ValidateServiceIdentity(ctx, "svcid_absent", token); ok {
			t.Fatal("unknown identity was accepted")
		}
	}
	after := identityCheckTotalAlloc()

	assertAllocUnderOneMiB(t, before, after)
}

func TestRegisterServiceIdentity_AllocatesUnderOneMiB_C_526209eb(t *testing.T) {
	svc := newIdentityCheckVault(t)

	before := identityCheckTotalAlloc()
	for i := 0; i < 5; i++ {
		id := fmt.Sprintf("svcid_reg_%d", i)
		token := bytes.Repeat([]byte{byte(i + 1)}, 32)
		if err := svc.RegisterServiceIdentity(id, token, []string{"vault.read"}); err != nil {
			t.Fatalf("RegisterServiceIdentity(%s): %v", id, err)
		}
	}
	after := identityCheckTotalAlloc()

	assertAllocUnderOneMiB(t, before, after)
}

func TestValidateServiceIdentity_RightToken_C_926d2b3e(t *testing.T) {
	svc := newIdentityCheckVault(t)
	ctx := context.Background()

	token := bytes.Repeat([]byte{0x33}, 32)
	want := []string{"vault.read", "vault.put"}
	if err := svc.RegisterServiceIdentity("svcid_a", token, want); err != nil {
		t.Fatalf("RegisterServiceIdentity: %v", err)
	}

	before := identityCheckTotalAlloc()
	got, ok := svc.ValidateServiceIdentity(ctx, "svcid_a", token)
	after := identityCheckTotalAlloc()

	if !ok {
		t.Fatal("ValidateServiceIdentity rejected the registered token")
	}
	if !slices.Equal(got, want) {
		t.Fatalf("scopes = %v, want %v", got, want)
	}
	assertAllocUnderOneMiB(t, before, after)
}

func TestValidateServiceIdentity_OtherTokensRefused_C_208852d8(t *testing.T) {
	svc := newIdentityCheckVault(t)
	ctx := context.Background()

	token := bytes.Repeat([]byte{0x44}, 32)
	if err := svc.RegisterServiceIdentity("svcid_a", token, []string{"vault.read", "vault.put"}); err != nil {
		t.Fatalf("RegisterServiceIdentity: %v", err)
	}

	flipped := bytes.Clone(token)
	flipped[len(flipped)-1] ^= 0xff
	longer := append(bytes.Clone(token), 0x00)
	shorter := token[:len(token)-1]
	variants := map[string][]byte{
		"last byte changed": flipped,
		"one byte longer":   longer,
		"one byte shorter":  shorter,
		"empty":             {},
	}

	before := identityCheckTotalAlloc()
	for name, candidate := range variants {
		got, ok := svc.ValidateServiceIdentity(ctx, "svcid_a", candidate)
		if ok {
			t.Fatalf("%s token was accepted", name)
		}
		if got != nil {
			t.Fatalf("%s token returned scopes %v, want nil", name, got)
		}
	}
	after := identityCheckTotalAlloc()

	assertAllocUnderOneMiB(t, before, after)
}

func TestValidateServiceIdentity_UnknownIdentity_C_985b05b1(t *testing.T) {
	svc := newIdentityCheckVault(t)
	ctx := context.Background()

	token := bytes.Repeat([]byte{0x55}, 32)

	before := identityCheckTotalAlloc()
	got, ok := svc.ValidateServiceIdentity(ctx, "svcid_absent", token)
	after := identityCheckTotalAlloc()

	if ok {
		t.Fatal("ValidateServiceIdentity accepted an unknown identity")
	}
	if got != nil {
		t.Fatalf("scopes = %v, want nil", got)
	}
	assertAllocUnderOneMiB(t, before, after)
}

func TestRegisterServiceIdentity_ScopesAreCopied_C_69da84c9(t *testing.T) {
	svc := newIdentityCheckVault(t)
	ctx := context.Background()

	token := bytes.Repeat([]byte{0x66}, 32)
	scopes := []string{"vault.read"}
	if err := svc.RegisterServiceIdentity("svcid_b", token, scopes); err != nil {
		t.Fatalf("RegisterServiceIdentity: %v", err)
	}
	scopes[0] = "vault.put"

	before := identityCheckTotalAlloc()
	got, ok := svc.ValidateServiceIdentity(ctx, "svcid_b", token)
	after := identityCheckTotalAlloc()

	if !ok {
		t.Fatal("ValidateServiceIdentity rejected the registered token")
	}
	if !slices.Equal(got, []string{"vault.read"}) {
		t.Fatalf("scopes = %v, want [vault.read]", got)
	}
	assertAllocUnderOneMiB(t, before, after)
}
