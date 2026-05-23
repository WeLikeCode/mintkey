/**
 * Signed-request JWT tests — T-1.2.3.
 *
 * Tests:
 * - buildSignedRequest returns a valid compact JWS.
 * - JWT claims include iss, sub, tnt, aud, exp, jti.
 * - exp is iat + 60.
 * - Two calls produce different jti values.
 *
 * Source: T-1.2.3; ADR-0014.5; ADR-0014.6.
 */

import { describe, it, expect } from "vitest";
import { buildSignedRequest } from "../src/lib/signed-request.js";
import { generateKeyPair, exportPKCS8 } from "jose";

async function makeTestKey() {
  const { privateKey } = await generateKeyPair("EdDSA", { crv: "Ed25519" });
  return privateKey;
}

describe("buildSignedRequest", () => {
  it("returns a compact JWS with three dot-separated parts", async () => {
    const key = await makeTestKey();
    const token = await buildSignedRequest({
      operatorId: "op_test",
      tenantId: "tenant_test",
      privateKey: key,
    });

    expect(token.split(".")).toHaveLength(3);
  });

  it("JWT payload contains required claims (ADR-0014.5)", async () => {
    const key = await makeTestKey();
    const token = await buildSignedRequest({
      operatorId: "op_abc",
      tenantId: "tenant_xyz",
      privateKey: key,
    });

    const payloadB64 = token.split(".")[1];
    const payload = JSON.parse(Buffer.from(payloadB64, "base64url").toString());

    expect(payload.iss).toBe("mintkey/admin-ui");
    expect(payload.aud).toBe("mintkey/admin-api");
    expect(payload.sub).toBe("op_abc");
    expect(payload.tnt).toBe("tenant_xyz");
    expect(payload.jti).toBeDefined();
    expect(typeof payload.exp).toBe("number");
    expect(typeof payload.iat).toBe("number");
  });

  it("exp = iat + 60 (ADR-0014.5: 60-second window)", async () => {
    const key = await makeTestKey();
    const token = await buildSignedRequest({
      operatorId: "op_test",
      tenantId: "tenant_test",
      privateKey: key,
    });

    const payload = JSON.parse(
      Buffer.from(token.split(".")[1], "base64url").toString()
    );
    expect(payload.exp - payload.iat).toBe(60);
  });

  it("two calls produce different jti values (replay prevention)", async () => {
    const key = await makeTestKey();

    const t1 = await buildSignedRequest({ operatorId: "op", tenantId: "t", privateKey: key });
    const t2 = await buildSignedRequest({ operatorId: "op", tenantId: "t", privateKey: key });

    const p1 = JSON.parse(Buffer.from(t1.split(".")[1], "base64url").toString());
    const p2 = JSON.parse(Buffer.from(t2.split(".")[1], "base64url").toString());

    expect(p1.jti).not.toBe(p2.jti);
  });

  it("JWT header alg is EdDSA", async () => {
    const key = await makeTestKey();
    const token = await buildSignedRequest({
      operatorId: "op_test",
      tenantId: "tenant_test",
      privateKey: key,
    });

    const header = JSON.parse(
      Buffer.from(token.split(".")[0], "base64url").toString()
    );
    expect(header.alg).toBe("EdDSA");
  });
});
