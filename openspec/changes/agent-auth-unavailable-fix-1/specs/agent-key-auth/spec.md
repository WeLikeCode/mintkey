# Spec Delta

## Purpose
How the MCP server and admin-api answer a request authenticated by an agent key when the key is valid, rejected, or could not be checked, and the capacity admin-api needs to check keys without timing out.

## ADDED Requirements

### Requirement: to_mib accepts 512mi, 1gi and non-ASCII digits — feedback FB-001
The behaviour pinned by the scenarios below SHALL hold.

#### Scenario: to_mib accepts 512mi, 1gi and non-ASCII digits
- **WHEN** to_mib is given 512mi, 1gi, or 512m written with non-ASCII digits (the full-width ５１２m)
- **THEN** it raises ValueError whose message contains the string, as it already does for 512, 512k, '512 Mi', '' and abc; only ASCII digits followed by exactly m, M, Mi, g, G or Gi convert
