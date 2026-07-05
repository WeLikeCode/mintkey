# Broker Key Persistence

## ADDED Requirements

### Requirement: Broker signs with a durable key loaded from a persistent source
The broker SHALL load its Ed25519 JWS signing key from a persistent source rather than generating an ephemeral key per process. The source priority is (1) the Vault Adapter via `svcid_broker`, (2) a file at `MINTKEY_BROKER_SIGNING_KEY_FILE`. When `MINTKEY_ENV=production` and no source yields a key, the broker MUST fail to start rather than generate an ephemeral key.

#### Scenario: Token survives a broker restart
- **WHEN** an agent is issued a JWT, then the broker process is restarted and reloads its key from the same persistent source
- **THEN** the previously-issued JWT still validates against `/.well-known/jwks.json` and a brokered proxy call using it still succeeds

#### Scenario: Production refuses to start without a key source
- **WHEN** the broker starts with `MINTKEY_ENV=production` and neither the Vault Adapter nor `MINTKEY_BROKER_SIGNING_KEY_FILE` provides a key
- **THEN** the broker exits with a clear error and issues no tokens

### Requirement: Multiple broker replicas serve a consistent JWKS
When more than one broker replica runs behind a single Service, all replicas SHALL load the same active signing key and serve an identical, consistent JWKS, so a token signed by any replica validates against the JWKS returned by any replica.

#### Scenario: Cross-replica token validation
- **WHEN** two broker replicas each issue a token from the shared loaded key
- **THEN** each replica's token validates against the other replica's `/.well-known/jwks.json`

### Requirement: Prior keys are retained across rotation
On a signing-key rotation the new key SHALL become the active signing key while previously-active public keys remain in the KeyRing and JWKS until the maximum token TTL for tokens signed under them has elapsed.

#### Scenario: Token issued before rotation still validates
- **WHEN** a token is issued, then the signing key is rotated
- **THEN** the pre-rotation token continues to validate against the JWKS until its own expiry
