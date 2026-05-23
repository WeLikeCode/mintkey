/**
 * Security config tests — S6 CodeQL cleartext-storage fix (strike-3).
 *
 * Verifies `getAdminPassword` behaviour under two security-critical paths:
 *
 * 1. KEK absent (dev path without encryption):
 *    - Falls back silently to ADMIN_PASSWORD env var.
 *    - Does NOT emit a console.error.
 *
 * 2. KEK present but decryption fails (wrong key / tampered ciphertext):
 *    - Emits console.error with the failure detail (not the KEK).
 *    - Returns "" so the caller treats auth as unavailable.
 *
 * Source: S6 CodeQL cleartext-storage-seed-job; reviewer issue #2.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// --- mock fs before importing the module under test -----------------------
// The mock must be declared before `getAdminPassword` is imported so that
// vitest hoisting replaces the real `fs` with the mock.
vi.mock("fs", () => ({
  readFileSync: vi.fn(),
}));

import { readFileSync } from "fs";
import { getAdminPassword } from "../src/lib/api-client.js";

// ---------------------------------------------------------------------------

const CANONICAL_DEV_KEK = "TUQpz9CUkfOvVJiM0yBUL8J9xAgrzE__JkNnwcocVas=";
const WRONG_KEK         = "jePSMThbHXS8J0V2d3xrOOgLmYhXx3V7VCcpVYeX6_0=";

// A Fernet token encrypted with CANONICAL_DEV_KEK containing "test-admin-password".
// Generated + verified via:
//   python3 -c "from cryptography.fernet import Fernet; f=Fernet(b'TUQpz...'); t=f.encrypt(b'test-admin-password'); print(t.decode()); print(f.decrypt(t).decode())"
// The JS decryptFernet implementation does not check the timestamp, so this static
// token remains valid indefinitely for unit tests.
const VALID_FERNET_TOKEN =
  "gAAAAABqCj3R9EKKtXWs85w_qOid-lYI3MXO2_pfdVWxAwCCWez01elGw25wdgdzrvccNqa_pgDdfm_4tpAFV9-9iSuVioSUpjizzP9btdr6jFIIPMtQ_xQ=";

// A Fernet token encrypted with WRONG_KEK (same plaintext).
// Attempting to decrypt this with CANONICAL_DEV_KEK must fail HMAC.
const WRONG_KEY_FERNET_TOKEN =
  "gAAAAABqCj2eemOe-_b6951Ds6SGjrAMCwbijC4_do17z88S4UrC4w-IMkvUOMz3PkPfAX4mcGGpja-nopVsLwJT87vCrRg3Tmmvk61SiDhe3xm6-4mxq7s=";

// ---------------------------------------------------------------------------

describe("getAdminPassword — KEK absent (dev path without encryption)", () => {
  const origEnv: Record<string, string | undefined> = {};

  beforeEach(() => {
    origEnv.MINTKEY_BOOTSTRAP_KEK  = process.env.MINTKEY_BOOTSTRAP_KEK;
    origEnv.ADMIN_PASSWORD_FILE    = process.env.ADMIN_PASSWORD_FILE;
    origEnv.ADMIN_PASSWORD         = process.env.ADMIN_PASSWORD;
    delete process.env.MINTKEY_BOOTSTRAP_KEK;
    delete process.env.ADMIN_PASSWORD_FILE;
    delete process.env.ADMIN_PASSWORD;
  });

  afterEach(() => {
    for (const [k, v] of Object.entries(origEnv)) {
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
    vi.restoreAllMocks();
  });

  it("returns ADMIN_PASSWORD env var when KEK is unset and no password file", () => {
    const consoleSpy = vi.spyOn(console, "error");
    process.env.ADMIN_PASSWORD = "dev-password-123";

    const result = getAdminPassword();

    expect(result).toBe("dev-password-123");
    expect(consoleSpy).not.toHaveBeenCalled();
  });

  it("returns empty string when KEK is unset and no env var", () => {
    const consoleSpy = vi.spyOn(console, "error");

    const result = getAdminPassword();

    expect(result).toBe("");
    expect(consoleSpy).not.toHaveBeenCalled();
  });

  it("returns plaintext file content when KEK is unset and file is present", () => {
    const consoleSpy = vi.spyOn(console, "error");
    process.env.ADMIN_PASSWORD_FILE = "/run/secrets/admin_password";
    (readFileSync as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      Buffer.from("plaintext-dev-pass\n"),
    );

    const result = getAdminPassword();

    expect(result).toBe("plaintext-dev-pass");
    expect(consoleSpy).not.toHaveBeenCalled();
  });

  it("falls back to ADMIN_PASSWORD when KEK is unset and file read fails", () => {
    const consoleSpy = vi.spyOn(console, "error");
    process.env.ADMIN_PASSWORD_FILE = "/nonexistent/admin_password";
    process.env.ADMIN_PASSWORD = "fallback-password";
    (readFileSync as ReturnType<typeof vi.fn>).mockImplementationOnce(() => {
      throw new Error("ENOENT: no such file or directory");
    });

    const result = getAdminPassword();

    expect(result).toBe("fallback-password");
    expect(consoleSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------

describe("getAdminPassword — KEK set but decryption fails (wrong key)", () => {
  const origEnv: Record<string, string | undefined> = {};

  beforeEach(() => {
    origEnv.MINTKEY_BOOTSTRAP_KEK  = process.env.MINTKEY_BOOTSTRAP_KEK;
    origEnv.ADMIN_PASSWORD_FILE    = process.env.ADMIN_PASSWORD_FILE;
    origEnv.ADMIN_PASSWORD         = process.env.ADMIN_PASSWORD;
    origEnv.NODE_ENV               = process.env.NODE_ENV;
    process.env.NODE_ENV = "development";
    process.env.MINTKEY_BOOTSTRAP_KEK = CANONICAL_DEV_KEK;
    process.env.ADMIN_PASSWORD_FILE   = "/run/secrets/admin_password";
  });

  afterEach(() => {
    for (const [k, v] of Object.entries(origEnv)) {
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
    vi.restoreAllMocks();
  });

  it("emits console.error and returns '' when ciphertext was encrypted with a different key", () => {
    const consoleSpy = vi.spyOn(console, "error");
    // File contains a token encrypted with WRONG_KEK, but env has CANONICAL_DEV_KEK
    (readFileSync as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      Buffer.from(WRONG_KEY_FERNET_TOKEN + "\n"),
    );

    const result = getAdminPassword();

    expect(result).toBe("");
    expect(consoleSpy).toHaveBeenCalledOnce();
    // Message must contain context but NOT the KEK value
    const [, detail] = consoleSpy.mock.calls[0] as [string, string];
    expect(typeof detail).toBe("string");
    expect(detail).not.toContain(CANONICAL_DEV_KEK);
    expect(detail).not.toContain(WRONG_KEK);
  });

  it("console.error message mentions 'decrypt' or 'HMAC'", () => {
    const consoleSpy = vi.spyOn(console, "error");
    (readFileSync as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      Buffer.from(WRONG_KEY_FERNET_TOKEN + "\n"),
    );

    getAdminPassword();

    const call = consoleSpy.mock.calls[0].join(" ");
    expect(call.toLowerCase()).toMatch(/decrypt|hmac|fernet/i);
  });

  it("does NOT fall back to ADMIN_PASSWORD when KEK is set and decrypt fails", () => {
    process.env.ADMIN_PASSWORD = "should-not-be-returned";
    (readFileSync as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      Buffer.from(WRONG_KEY_FERNET_TOKEN + "\n"),
    );

    const result = getAdminPassword();

    // Must return "" (auth-unavailable), not the env var fallback
    expect(result).toBe("");
    expect(result).not.toBe("should-not-be-returned");
  });

  it("decrypts successfully with the correct key (happy path)", () => {
    const consoleSpy = vi.spyOn(console, "error");
    (readFileSync as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      Buffer.from(VALID_FERNET_TOKEN + "\n"),
    );

    const result = getAdminPassword();

    expect(result).toBe("test-admin-password");
    expect(consoleSpy).not.toHaveBeenCalled();
  });
});
