# Contracts — the source of truth for SDD

> Specifications-driven development means **the contract is the spec, not the code**. Implementations are derived; contracts are authored.

## Layout

```
contracts/
├── openapi/                  # REST APIs (OpenAPI 3.1)
│   └── v1/                   # Versioned by major; v2/ on breaking changes
├── asyncapi/                 # Event / messaging contracts (AsyncAPI 2.6)
├── jsonschema/               # Reusable payload / config schemas
├── avro/  protobuf/          # Optional: streaming / gRPC
└── fixtures/                 # Canonical example payloads (CI validates)
```

**Wizard-gated:** if Q12 was `Internal-only`, only `jsonschema/` exists. If `gRPC`, `protobuf/` is added. Etc.

## Authoring rules

### OpenAPI 3.1
- One file per resource family. Filenames: `<service>-<resource>.v1.yaml`.
- `$ref` shared types into `jsonschema/`. Don't inline reusable types.
- Versioning: breaking changes bump major in path (`v1/` → `v2/`); additive changes are minor on the same file.
- Lint: `spectral` config in `tools/lint/`. CI fails on lint errors.

### AsyncAPI 2.6
- Channels named `<bounded-context>.<entity>.<verb>` (e.g., `inventory.product.created`).
- Event payload schemas live in `jsonschema/` and are `$ref`-ed.
- Validate via `asyncapi-cli validate`.

### JSON Schema
- Use Draft-2020-12 unless the engagement chose otherwise at bootstrap (Q19 / Q22).
- Every schema has at least one fixture in `contracts/fixtures/`.
- Fixtures are validated against their schema in CI via `ajv-cli` (TS) or `jsonschema` (Python).

### Fixtures
- Canonical example payloads. Use to drive contract tests.
- Naming: `<schema-name>.{valid,invalid-<reason>}.json`.
- CI fails if a fixture stops validating against its schema.

## Contract-first workflow

1. **Author or update a contract** in `contracts/`. Open a PR.
2. **Validate locally**: `make contracts-lint && make contracts-test`.
3. **Update fixtures** if shape changed.
4. **Get review** from the contract owner (per CODEOWNERS).
5. **Merge.** Code that implements the contract follows in subsequent PRs, citing this contract.
6. **Generated SDKs** (TS / Python clients, server stubs) regenerate on merge — never hand-edit them.

## Spec-first enforcement

The `/spec-first-check` skill refuses code-write requests that don't reference a contract or ADR. CI also runs `vibe-check` which scans PR descriptions for `Spec:` / `ADR:` / `Contract:` citation tokens.

## Anti-patterns

- Writing code first and back-filling the contract — the timestamp on the contract should precede the implementing code.
- Contract that's never referenced by tests — see the `coverage-vs-spec` report.
- Inline payload shapes in OpenAPI when they're reused — extract to `jsonschema/`.
- Hand-edited generated client code — always regenerate from contract.
- Treating `contracts/` as a dump for OpenAPI alone — events, payloads, RPC are all "specs."

## Tooling

| Concern | Default tool | Alternatives |
|---|---|---|
| OpenAPI lint | spectral | redocly, oas-validator |
| OpenAPI tests | Schemathesis | Dredd, Pact |
| AsyncAPI validate | asyncapi-cli | Microcks |
| JSON Schema validate | ajv-cli (TS), jsonschema (Python) | check-jsonschema |
| Avro / Protobuf | buf | avro-tools |
| Mock server | Prism (OpenAPI) | Microcks (AsyncAPI) |

The wizard records which tools the engagement uses. Default toolchain for greenfield: **OpenAPI 3.1 + AsyncAPI 2.6 + JSON Schema 2020-12 + Schemathesis + Microcks + ajv + spectral**.

---

*Read [`docs/architecture/adrs/`](../docs/architecture/adrs/) for the architectural decisions that constrain what these contracts can express.*
