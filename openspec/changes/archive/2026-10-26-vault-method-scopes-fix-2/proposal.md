# Proposal: fix 2 for vault-method-scopes

## Why
The verifier found problems in `vault-method-scopes` that this change fixes. The findings are listed below with their ids; each task of this change names the ones it answers.

## What Changes
- F-2813828d (blocker): a pre-existing test fails on the unit's code: github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestGRPCValidateServiceIdentity_MissingToken (Failed), github.com/mintkey/mintkey/services/vault-adapter/internal/server::TestSSHVault_GetAgentByFingerprint_MissingToken (Failed)

## Impact
The code and the tests of `vault-method-scopes`.
