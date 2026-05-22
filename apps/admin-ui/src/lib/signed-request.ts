/**
 * AdminUI signed-request JWT signer.
 *
 * All AdminJS writes are forwarded to admin-api with an Ed25519-signed JWT
 * instead of calling the DB directly. This file implements the JWT signer.
 *
 * JWT claims (ADR-0014.5, ADR-0014.6):
 *   iss: "mintkey/admin-ui"
 *   sub: <operator_id>
 *   tnt: <tenant_id>
 *   aud: "mintkey/admin-api"
 *   iat: <unix timestamp>
 *   exp: iat + 60   (60-second window)
 *   jti: <uuid v4>  (replay prevention — checked against admin_request_jti table)
 *
 * The private key is loaded from the path in ADMIN_UI_PRIVATE_KEY_PATH env var
 * (default: /run/secrets/admin_ui_private.pem). In tests, an in-process key
 * pair is generated.
 *
 * Source: T-1.2.3; T-1.0.13; ADR-0014.5; ADR-0014.6.
 */

import { readFileSync } from "fs";
import { SignJWT, importPKCS8, type KeyLike } from "jose";
import { v4 as uuidv4 } from "uuid";

const PRIVATE_KEY_PATH =
  process.env.ADMIN_UI_PRIVATE_KEY_PATH ?? "/run/secrets/admin_ui_private.pem";

let _privateKey: KeyLike | null = null;

/**
 * Returns null if the PEM file is absent or unreadable — callers should
 * omit the x-mintkey-signed-request header rather than crashing.  The
 * AdminUiSignedRequestMiddleware on admin-api is configured with a null
 * public_key in dev (no key file provisioned) and skips verification when
 * no key is loaded — so omitting the JWT is safe in that configuration.
 * In production the key file must be present.
 */
async function loadPrivateKey(): Promise<KeyLike | null> {
  if (_privateKey) return _privateKey;
  let pem: string;
  try {
    pem = readFileSync(PRIVATE_KEY_PATH, "utf8");
  } catch {
    // Key file not provisioned (dev / bootstrap scenario) — return null so
    // the caller can skip the JWT header.
    return null;
  }
  _privateKey = await importPKCS8(pem, "EdDSA");
  return _privateKey;
}

export interface SignedRequestOptions {
  operatorId: string;
  tenantId: string;
  /** Session token relayed from admin-api (for Cookie header). */
  sessionToken?: string;
  /** CSRF token for double-submit (X-Mintkey-Csrf header). */
  csrfToken?: string;
  /** Override the private key (useful in tests). */
  privateKey?: KeyLike;
}

/**
 * Build an Ed25519-signed JWT for an AdminJS write forwarded to admin-api.
 * Returns the compact JWS string, or null if no private key is available.
 *
 * ADR-0014.5: iss="mintkey/admin-ui", aud="mintkey/admin-api",
 * exp=iat+60, jti is a fresh UUIDv4 on every call.
 */
export async function buildSignedRequest(
  opts: SignedRequestOptions
): Promise<string | null> {
  const key = opts.privateKey ?? (await loadPrivateKey());
  if (!key) return null;
  const now = Math.floor(Date.now() / 1000);

  return new SignJWT({
    sub: opts.operatorId,
    tnt: opts.tenantId,
  })
    .setProtectedHeader({ alg: "EdDSA" })
    .setIssuer("mintkey/admin-ui")
    .setAudience("mintkey/admin-api")
    .setIssuedAt(now)
    .setExpirationTime(now + 60)
    .setJti(uuidv4())
    .sign(key);
}

/**
 * Call admin-api with session/CSRF headers. Attaches an Ed25519-signed JWT
 * when the private key is available; omits the header when it is not (dev /
 * bootstrap scenario where AdminUiSignedRequestMiddleware has no public key).
 *
 * Source: ADR-0014.5; ADR-0019.
 */
export async function signedFetch(
  url: string,
  opts: SignedRequestOptions & { method?: string; body?: unknown }
): Promise<Response> {
  const token = await buildSignedRequest(opts);

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  // ADR-0019: JWT goes in x-mintkey-signed-request, NOT Authorization
  // Omit header when key is unavailable (admin-api skips verify when no pub key).
  if (token) {
    headers["x-mintkey-signed-request"] = token;
  }

  if (opts.sessionToken) {
    const cookieParts = [`mintkey_session=${opts.sessionToken}`];
    if (opts.csrfToken) cookieParts.push(`csrf_token=${opts.csrfToken}`);
    headers["Cookie"] = cookieParts.join("; ");
  }
  if (opts.csrfToken) {
    headers["X-Mintkey-Csrf"] = opts.csrfToken;
  }

  return fetch(url, {
    method: opts.method ?? "POST",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
}
