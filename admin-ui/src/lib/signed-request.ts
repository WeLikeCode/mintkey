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

async function loadPrivateKey(): Promise<KeyLike> {
  if (_privateKey) return _privateKey;
  const pem = readFileSync(PRIVATE_KEY_PATH, "utf8");
  _privateKey = await importPKCS8(pem, "EdDSA");
  return _privateKey;
}

export interface SignedRequestOptions {
  operatorId: string;
  tenantId: string;
  /** Override the private key (useful in tests). */
  privateKey?: KeyLike;
}

/**
 * Build an Ed25519-signed JWT for an AdminJS write forwarded to admin-api.
 * Returns the compact JWS string.
 *
 * ADR-0014.5: iss="mintkey/admin-ui", aud="mintkey/admin-api",
 * exp=iat+60, jti is a fresh UUIDv4 on every call.
 */
export async function buildSignedRequest(
  opts: SignedRequestOptions
): Promise<string> {
  const key = opts.privateKey ?? (await loadPrivateKey());
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
 * Call admin-api with a signed JWT in the Authorization header.
 * Returns the fetch Response.
 *
 * Source: ADR-0014.5.
 */
export async function signedFetch(
  url: string,
  opts: SignedRequestOptions & { method?: string; body?: unknown }
): Promise<Response> {
  const token = await buildSignedRequest(opts);

  return fetch(url, {
    method: opts.method ?? "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
}
