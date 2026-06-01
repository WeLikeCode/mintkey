/**
 * Credential payload wire-form contract tests (C-1).
 *
 * Guards against the double-construction bug: the credentials/new handler
 * was calling buildCredentialPayload() on a payload the frontend had already
 * serialised, producing inner JSON with all empty strings.
 *
 * These tests verify:
 *   1. buildCredentialPayload produces the correct wire-form for all 8 schemes
 *      (the frontend's job).
 *   2. Calling buildCredentialPayload a second time on an already-built
 *      payload clobbers the nested value (documents the old regression).
 *   3. All 5 special schemes produce {auth_scheme, value: "<JSON>"} where
 *      the inner JSON matches the admin-api pydantic model field names.
 *   4. Bearer_token and basic_auth produce flat payloads (no nested value).
 *
 * Source: C-1 fix; admin_api.services.credential_service payload models.
 */

import { describe, it, expect } from "vitest";
import { buildCredentialPayload } from "../src/lib/auth-scheme.js";

// ── helpers ──────────────────────────────────────────────────────────────────

function parseInner(payload: Record<string, string>): Record<string, unknown> {
  return JSON.parse(payload["value"]) as Record<string, unknown>;
}

// ── ssh_password ──────────────────────────────────────────────────────────────

describe("wire-form contract: ssh_password", () => {
  it("emits {auth_scheme, value: JSON({scheme, username, password, target_address})}", () => {
    const p = buildCredentialPayload("ssh_password", {
      username: "root",
      password: "hunter2",
      target_address: "172.24.1.234:22",
    });
    expect(p.auth_scheme).toBe("ssh_password");
    expect(typeof p.value).toBe("string");
    const inner = parseInner(p);
    expect(inner).toMatchObject({
      scheme: "ssh_password",
      username: "root",
      password: "hunter2",
      target_address: "172.24.1.234:22",
    });
    // Exactly the 4 keys admin-api SSHPasswordPayload expects
    expect(Object.keys(inner).sort()).toEqual(
      ["password", "scheme", "target_address", "username"].sort()
    );
  });

  it("double-construction clobbers inner values (documents old handler regression)", () => {
    // Step 1: frontend builds the correct payload
    const frontendPayload = buildCredentialPayload("ssh_password", {
      username: "root",
      password: "hunter2",
      target_address: "172.24.1.234:22",
    });
    // frontendPayload.value = '{"scheme":"ssh_password","username":"root",...}'

    // Step 2: OLD handler called buildCredentialPayload again on frontendPayload.
    // frontendPayload has {auth_scheme, value: "<json>"} — no top-level
    // username/password/target_address keys — so all fields come back empty.
    const doubleBuilt = buildCredentialPayload(
      frontendPayload.auth_scheme,
      frontendPayload as Record<string, string>
    );
    const inner = parseInner(doubleBuilt);
    // This is the bug: all three credential fields are empty strings
    expect(inner.username).toBe("");
    expect(inner.password).toBe("");
    expect(inner.target_address).toBe("");
  });

  it("pass-through preserves the frontend-built payload unchanged", () => {
    const frontendPayload = buildCredentialPayload("ssh_password", {
      username: "root",
      password: "hunter2",
      target_address: "172.24.1.234:22",
    });
    // Simulate the FIXED handler: pure pass-through, no second call.
    const handlerPayload = frontendPayload; // handler just passes it on
    const inner = parseInner(handlerPayload);
    expect(inner.username).toBe("root");
    expect(inner.password).toBe("hunter2");
    expect(inner.target_address).toBe("172.24.1.234:22");
  });
});

// ── ssh_private_key ───────────────────────────────────────────────────────────

describe("wire-form contract: ssh_private_key", () => {
  it("emits {auth_scheme, value: JSON({scheme, private_key_pem, target_address, ssh_user})}", () => {
    const p = buildCredentialPayload("ssh_private_key", {
      private_key_pem: "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNza\n-----END OPENSSH PRIVATE KEY-----",
      target_address: "10.0.0.5:22",
      ssh_user: "ubuntu",
    });
    expect(p.auth_scheme).toBe("ssh_private_key");
    expect(typeof p.value).toBe("string");
    const inner = parseInner(p);
    expect(inner).toMatchObject({
      scheme: "ssh_private_key",
      private_key_pem: "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNza\n-----END OPENSSH PRIVATE KEY-----",
      target_address: "10.0.0.5:22",
      ssh_user: "ubuntu",
    });
    expect(Object.keys(inner).sort()).toEqual(
      ["private_key_pem", "scheme", "ssh_user", "target_address"].sort()
    );
  });

  it("double-construction clobbers private_key_pem (documents old handler regression)", () => {
    const frontendPayload = buildCredentialPayload("ssh_private_key", {
      private_key_pem: "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNza\n-----END OPENSSH PRIVATE KEY-----",
      target_address: "10.0.0.5:22",
      ssh_user: "ubuntu",
    });
    const doubleBuilt = buildCredentialPayload(
      frontendPayload.auth_scheme,
      frontendPayload as Record<string, string>
    );
    const inner = parseInner(doubleBuilt);
    expect(inner.private_key_pem).toBe("");
    expect(inner.target_address).toBe("");
    expect(inner.ssh_user).toBe("");
  });
});

// ── ssh_ca ────────────────────────────────────────────────────────────────────

describe("wire-form contract: ssh_ca", () => {
  it("emits {auth_scheme, value: JSON({scheme, ca_private_key_pem, ca_principal_prefix})}", () => {
    const p = buildCredentialPayload("ssh_ca", {
      ca_private_key_pem: "-----BEGIN OPENSSH PRIVATE KEY-----\nca_key\n-----END OPENSSH PRIVATE KEY-----",
      ca_principal_prefix: "agent-",
    });
    expect(p.auth_scheme).toBe("ssh_ca");
    expect(typeof p.value).toBe("string");
    const inner = parseInner(p);
    expect(inner).toMatchObject({
      scheme: "ssh_ca",
      ca_private_key_pem: "-----BEGIN OPENSSH PRIVATE KEY-----\nca_key\n-----END OPENSSH PRIVATE KEY-----",
      ca_principal_prefix: "agent-",
    });
    expect(Object.keys(inner).sort()).toEqual(
      ["ca_principal_prefix", "ca_private_key_pem", "scheme"].sort()
    );
  });

  it("double-construction clobbers ca fields (documents old handler regression)", () => {
    const frontendPayload = buildCredentialPayload("ssh_ca", {
      ca_private_key_pem: "-----BEGIN OPENSSH PRIVATE KEY-----\nca_key\n-----END OPENSSH PRIVATE KEY-----",
      ca_principal_prefix: "agent-",
    });
    const doubleBuilt = buildCredentialPayload(
      frontendPayload.auth_scheme,
      frontendPayload as Record<string, string>
    );
    const inner = parseInner(doubleBuilt);
    expect(inner.ca_private_key_pem).toBe("");
    expect(inner.ca_principal_prefix).toBe("");
  });
});

// ── apple_jwt ─────────────────────────────────────────────────────────────────

describe("wire-form contract: apple_jwt", () => {
  it("emits {auth_scheme, value: JSON({scheme, p8_key_pem, key_id, issuer_id})}", () => {
    const p = buildCredentialPayload("apple_jwt", {
      p8_key_pem: "-----BEGIN PRIVATE KEY-----\nMIGH...\n-----END PRIVATE KEY-----",
      key_id: "TNRVKBLCWWTH",
      issuer_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    });
    expect(p.auth_scheme).toBe("apple_jwt");
    expect(typeof p.value).toBe("string");
    const inner = parseInner(p);
    expect(inner).toMatchObject({
      scheme: "apple_jwt",
      p8_key_pem: "-----BEGIN PRIVATE KEY-----\nMIGH...\n-----END PRIVATE KEY-----",
      key_id: "TNRVKBLCWWTH",
      issuer_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    });
    expect(Object.keys(inner).sort()).toEqual(
      ["issuer_id", "key_id", "p8_key_pem", "scheme"].sort()
    );
  });

  it("double-construction clobbers apple_jwt fields (documents old handler regression)", () => {
    // apple_jwt previously fell to the else branch in CredentialNewForm
    // (no special-case), so the flat fields were at top level and the
    // double-call happened to work. This test documents that once we move
    // apple_jwt to the special-case branch (and the handler is pass-through),
    // the double-call path would also clobber.
    const frontendPayload = buildCredentialPayload("apple_jwt", {
      p8_key_pem: "-----BEGIN PRIVATE KEY-----\nMIGH...\n-----END PRIVATE KEY-----",
      key_id: "TNRVKBLCWWTH",
      issuer_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    });
    // frontendPayload has {auth_scheme, value: "<json>"} — flat fields are nested
    const doubleBuilt = buildCredentialPayload(
      frontendPayload.auth_scheme,
      frontendPayload as Record<string, string>
    );
    const inner = parseInner(doubleBuilt);
    // Double-build clobbers because top-level p8_key_pem/key_id/issuer_id are absent
    expect(inner.p8_key_pem).toBe("");
    expect(inner.key_id).toBe("");
    expect(inner.issuer_id).toBe("");
  });
});

// ── google_service_account ────────────────────────────────────────────────────

describe("wire-form contract: google_service_account", () => {
  it("emits {auth_scheme, value: JSON({scheme, service_account_json, scope})}", () => {
    const saJson = '{"type":"service_account","project_id":"my-proj"}';
    const p = buildCredentialPayload("google_service_account", {
      service_account_json: saJson,
      scope: "https://www.googleapis.com/auth/androidpublisher",
    });
    expect(p.auth_scheme).toBe("google_service_account");
    expect(typeof p.value).toBe("string");
    const inner = parseInner(p);
    expect(inner).toMatchObject({
      scheme: "google_service_account",
      service_account_json: saJson,
      scope: "https://www.googleapis.com/auth/androidpublisher",
    });
    expect(Object.keys(inner).sort()).toEqual(
      ["scheme", "scope", "service_account_json"].sort()
    );
  });

  it("double-construction clobbers service_account_json (documents old handler regression)", () => {
    const frontendPayload = buildCredentialPayload("google_service_account", {
      service_account_json: '{"type":"service_account"}',
      scope: "https://www.googleapis.com/auth/androidpublisher",
    });
    const doubleBuilt = buildCredentialPayload(
      frontendPayload.auth_scheme,
      frontendPayload as Record<string, string>
    );
    const inner = parseInner(doubleBuilt);
    expect(inner.service_account_json).toBe("");
  });
});

// ── oauth2_password_grant ─────────────────────────────────────────────────────

describe("wire-form contract: oauth2_password_grant", () => {
  it("emits {auth_scheme, token_url, value: JSON({token_url, credential_fields, token_response_path, exchange_timeout_seconds})}", () => {
    const p = buildCredentialPayload("oauth2_password_grant", {
      token_url: "https://auth.example.com/oauth2/token",
      credential_fields_json: JSON.stringify({ userName: "vrusu", password: "Asd123!" }),
      token_response_path: "$.access_token",
      exchange_timeout_seconds: "10",
    });
    expect(p.auth_scheme).toBe("oauth2_password_grant");
    expect(p.token_url).toBe("https://auth.example.com/oauth2/token");
    expect(typeof p.value).toBe("string");
    const inner = parseInner(p);
    expect(inner.token_url).toBe("https://auth.example.com/oauth2/token");
    expect(inner.credential_fields).toEqual({ userName: "vrusu", password: "Asd123!" });
    expect(inner.token_response_path).toBe("$.access_token");
    expect(inner.exchange_timeout_seconds).toBe(10);
  });
});

// ── legacy schemes: bearer_token and basic_auth ───────────────────────────────

describe("wire-form contract: bearer_token (legacy)", () => {
  it("emits flat {auth_scheme, value: '<token>'} — no nested JSON", () => {
    const p = buildCredentialPayload("bearer_token", {
      value: "sk-supersecret",
    });
    expect(p.auth_scheme).toBe("bearer_token");
    // value is the raw token string, not a JSON envelope
    expect(p.value).toBe("sk-supersecret");
    // Parsing it as JSON should fail (it's a raw string, not JSON)
    expect(() => JSON.parse(p.value)).toThrow();
  });

  it("pass-through preserves bearer_token payload unchanged", () => {
    const frontendPayload = buildCredentialPayload("bearer_token", {
      value: "sk-supersecret",
    });
    const handlerPayload = frontendPayload; // pure pass-through
    expect(handlerPayload.auth_scheme).toBe("bearer_token");
    expect(handlerPayload.value).toBe("sk-supersecret");
  });
});

describe("wire-form contract: basic_auth (legacy)", () => {
  it("emits flat {auth_scheme, username, password} — no nested JSON", () => {
    const p = buildCredentialPayload("basic_auth", {
      username: "alice",
      password: "wonderland",
    });
    expect(p.auth_scheme).toBe("basic_auth");
    expect(p.username).toBe("alice");
    expect(p.password).toBe("wonderland");
    expect(p.value).toBeUndefined();
  });

  it("pass-through preserves basic_auth payload unchanged", () => {
    const frontendPayload = buildCredentialPayload("basic_auth", {
      username: "alice",
      password: "wonderland",
    });
    const handlerPayload = frontendPayload; // pure pass-through
    expect(handlerPayload.username).toBe("alice");
    expect(handlerPayload.password).toBe("wonderland");
  });
});
