# MongoDB Atlas Service Templates

## ADDED Requirements

### Requirement: Two Atlas Administration API templates exist
The template registry SHALL provide `mongodb-atlas-service-account` (`auth_type: oauth2_client_credentials`) and `mongodb-atlas-api-key` (`auth_type: http_digest`), both with `base_url: https://cloud.mongodb.com/api/atlas/v2`, the Atlas v2 OpenAPI spec URL, `test_path: /groups`, and credential hints for their respective schemes.

#### Scenario: Operator registers Atlas via a Service Account
- **WHEN** an operator instantiates `mongodb-atlas-service-account` and supplies `client_id`/`client_secret`
- **THEN** a service is created with `auth_scheme: oauth2_client_credentials` and `base_url: https://cloud.mongodb.com/api/atlas/v2`, ready for `read:atlas`/`admin:atlas` grants

#### Scenario: Operator registers Atlas via a Programmatic API Key
- **WHEN** an operator instantiates `mongodb-atlas-api-key` and supplies `public_key`/`private_key`
- **THEN** a service is created with `auth_scheme: http_digest` and the same Atlas base URL

### Requirement: Templates explicitly instruct the agent to send the Atlas version header
Both Atlas templates SHALL carry, in the agent-visible `description` and in operator `config_notes`, an explicit statement that the agent must send `Accept: application/vnd.atlas.<yyyy-mm-dd>+json` on every request (or receive HTTP 406), and that Mintkey forwards request headers unchanged and does NOT add this header automatically.

#### Scenario: Agent discovers the version-header requirement
- **WHEN** an agent calls `describe_service` (or `list_services`) for a service created from an Atlas template
- **THEN** the returned `description` states the dated `Accept` version-header requirement and that the agent must set it itself

#### Scenario: Mintkey does not inject the version header
- **WHEN** an agent calls an Atlas service without an `Accept` version header
- **THEN** the proxy forwards the request unchanged (no version header added by Mintkey) and the agent receives MongoDB's 406, consistent with the documented behavior
