# Mintkey brand direction

Mintkey is a self-hosted credential broker for AI agents. The brand should feel
like infrastructure: calm, precise, trustworthy, and built for developers who
care about security.

## Core idea

Mintkey gives agents access without handing them raw credentials.

The mark combines three ideas:

- **Mint leaf**: freshness, control, and the product name.
- **Keyway**: credential custody and access control.
- **Routing nodes**: MCP discovery, token issuance, and proxy-mediated calls.

Avoid generic locks, shields, robots, mascots, glossy gradients, and overly busy
network/circuit imagery. Mintkey should look like security infrastructure, not a
consumer password app.

## Primary asset

The initial generated brand board is stored at:

`marketing/assets/mintkey-brand-board.png`

This file is a concept board, not a final production vector source. Before using
the logo in package managers, favicons, or high-resolution marketing material,
recreate the selected mark as SVG and verify small-size legibility.

## Generated brand assets

| Asset | Path | Purpose |
|---|---|---|
| Brand board | `marketing/assets/mintkey-brand-board.png` | Raster concept board and visual reference |
| Brand mark | `marketing/assets/mintkey-mark.svg` | Standalone logo mark for docs, UI, and diagrams |
| Wordmark | `marketing/assets/mintkey-wordmark.svg` | Horizontal logo lockup |
| Favicon | `marketing/assets/mintkey-favicon.svg` | Browser/app icon source |
| Banner | `marketing/assets/mintkey-banner.svg` | Repository/social preview and docs hero asset |

The SVG assets are production-oriented starting points, but they should still be
reviewed at small sizes before being treated as final trademark artwork.

## Palette

| Token | Hex | Use |
|---|---|---|
| Deep ink | `#101820` | Primary text, icon contrast, dark UI surfaces |
| Mint | `#2EE6A6` | Primary brand color, active states, logo leaf |
| Glacier | `#DDF7EF` | Soft backgrounds, callouts, diagrams |
| Brass | `#C7A64A` | Accent only, status highlights, sparing emphasis |
| Off-white | `#F7FAF8` | Page background and negative space |

## Typography direction

- Use a modern geometric sans for product and marketing surfaces.
- Use a technical monospace only for IDs, tokens, CLI commands, and code.
- Keep headlines direct and short. Mintkey is an infrastructure product; avoid
  hype language.

## Voice

Mintkey should sound:

- clear, not clever
- security-aware, not fear-driven
- precise, not academic
- honest about pre-alpha limits

Preferred language:

- "Agents get scoped short-lived access, never raw API keys."
- "Self-hosted credential brokering for AI agents."
- "Audit and revoke agent access from one control plane."

Avoid:

- "military-grade"
- "unbreakable"
- "zero risk"
- "production-ready" until the release gates support that claim

## Product one-liner

Mintkey is a self-hosted credential broker for AI agents: agents discover
services, receive scoped short-lived access, and call through a proxy that
injects the real credential in-flight.
