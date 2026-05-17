# Base Image Lock — S2 Trivy Base Image Bump

**Session:** fix/s2-trivy-base-image-2026-05-18  
**Date:** 2026-05-18  
**Digest source:** `docker pull <image> && docker inspect --format='{{index .RepoDigests 0}}'` + registry HTTP API verification via `curl -H "Accept: application/vnd.oci.image.index.v1+json" --head <registry>/v2/.../manifests/<tag>`

---

## Inventory table

| Dockerfile | Stage | Old tag | Old digest (sha256:…) | New tag | New digest (sha256:…) | Changed? | Rationale |
|---|---|---|---|---|---|---|---|
| `admin-api/Dockerfile` | (single) | `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` | `e5b65587…` | `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` | `e5b65587…` | NO — already current | docker pull confirmed up to date 2026-05-18 |
| `mcp-server/Dockerfile` | (single) | `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` | `e5b65587…` | `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` | `e5b65587…` | NO — already current | same image as admin-api |
| `mock-backend/Dockerfile` | (single) | `python:3.12-slim` | `401f6e1a…` | `python:3.12-slim-bookworm` | `d193c6f5…` | **YES** | explicit bookworm tag carries patched Debian packages vs generic `slim` alias; registry confirmed new digest |
| `seed-job/Dockerfile` | (single) | `python:3.12-slim` | `401f6e1a…` | `python:3.12-slim-bookworm` | `d193c6f5…` | **YES** | same as mock-backend |
| `admin-ui/Dockerfile` | (single) | `node:22-slim` | `689c1104…` | `node:22-bookworm-slim` | `689c1104…` | tag rename only | `22-slim` and `22-bookworm-slim` resolve to same digest (confirmed 2026-05-18); tag made explicit per owner policy |
| `jaeger-auth/Dockerfile` | proxy (builder) | `quay.io/oauth2-proxy/oauth2-proxy:v7.6.0` | `dcb6ff8d…` | `quay.io/oauth2-proxy/oauth2-proxy:v7.6.0` | `dcb6ff8d…` | NO — already current | docker pull confirmed up to date |
| `jaeger-auth/Dockerfile` | (runtime) | `alpine:3.19` | `6baf4358…` | `alpine:3.19` | `6baf4358…` | NO — already current | docker pull + registry API confirmed up to date |
| `services/broker/Dockerfile` | builder | `golang:1.26-alpine` | `91eda977…` | `golang:1.26-alpine` | `91eda977…` | NO — already current | docker pull confirmed up to date |
| `services/broker/Dockerfile` | runtime | `gcr.io/distroless/static-debian12` | `20bc6c0b…` | `gcr.io/distroless/static-debian12` | `20bc6c0b…` | NO — already current | docker pull confirmed up to date |
| `services/proxy-plugin/Dockerfile` | builder | `golang:1.26-alpine` | `91eda977…` | `golang:1.26-alpine` | `91eda977…` | NO — already current | same as broker |
| `services/proxy-plugin/Dockerfile` | runtime | `gcr.io/distroless/static-debian12` | `20bc6c0b…` | `gcr.io/distroless/static-debian12` | `20bc6c0b…` | NO — already current | same as broker |
| `services/kong-syncer/Dockerfile` | builder | `golang:1.26-alpine` | `91eda977…` | `golang:1.26-alpine` | `91eda977…` | NO — already current | same as broker |
| `services/kong-syncer/Dockerfile` | runtime | `gcr.io/distroless/static-debian12` | `20bc6c0b…` | `gcr.io/distroless/static-debian12` | `20bc6c0b…` | NO — already current | same as broker |
| `services/vault-adapter/Dockerfile` | builder | `golang:1.26-alpine` | `91eda977…` | `golang:1.26-alpine` | `91eda977…` | NO — already current | same as broker |
| `services/vault-adapter/Dockerfile` | runtime | `gcr.io/distroless/static-debian12` | `20bc6c0b…` | `gcr.io/distroless/static-debian12` | `20bc6c0b…` | NO — already current | same as broker |

---

## Full digests

| Image | Tag | sha256 digest |
|---|---|---|
| `ghcr.io/astral-sh/uv` | `python3.12-bookworm-slim` | `e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58` |
| `docker.io/library/python` | `3.12-slim` (old) | `401f6e1a67dad31a1bd78e9ad22d0ee0a3b52154e6bd30e90be696bb6a3d7461` |
| `docker.io/library/python` | `3.12-slim-bookworm` (new) | `d193c6f51a7dbd10395d6328de3a7edb0516fb0608ca138036576f574c3e07d2` |
| `docker.io/library/node` | `22-slim` / `22-bookworm-slim` | `689c11043dad91472750cd824c97dd5e2318e9dd6f954e492fe7af0135d33ceb` |
| `docker.io/library/golang` | `1.26-alpine` | `91eda9776261207ea25fd06b5b7fed8d397dd2c0a283e77f2ab6e91bfa71079d` |
| `gcr.io/distroless/static-debian12` | `latest` | `20bc6c0bc4d625a22a8fde3e55f6515709b32055ef8fb9cfbddaa06d1760f838` |
| `docker.io/library/alpine` | `3.19` | `6baf43584bcb78f2e5847d1de515f23499913ac9f12bdf834811a3145eb11ca1` |
| `quay.io/oauth2-proxy/oauth2-proxy` | `v7.6.0` | `dcb6ff8dd21bf3058f6a22c6fa385fa5b897a9cd3914c88a2cc2bb0a85f8065d` |

---

## Notes

- `python:3.12-slim` (generic alias) and `python:3.12-slim-bookworm` (explicit distro tag) had diverged — as of 2026-05-18 the `3.12-slim` alias points to **Debian 13 (trixie)** while `3.12-slim-bookworm` is **Debian 12 (bookworm)**. The new `python:3.12-slim-bookworm` digest (`d193c6f5`) carries `openssl 3.0.19-1~deb12u2` which patches CVE-2026-31789 (fixed version `3.0.19-1~deb12u2`). `mock-backend` and `seed-job` migrated.
- `node:22-slim` and `node:22-bookworm-slim` resolve identically (same manifest) as of 2026-05-18; the tag is renamed to explicit bookworm for consistency and future clarity.
- `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` (e5b65587) is the latest available uv image as of 2026-05-18 but still carries **openssl 3.0.18-1~deb12u2** (not yet patched for CVE-2026-31789). Admin-api and mcp-server CVE-2026-31789 will be resolved when astral-sh rebuilds the uv image with updated Debian packages. **STATUS for uv image: deferred — upstream has not yet published a rebuild.**
- All other base images confirmed current at their pinned digests.
- Digest source verified: `docker pull --quiet <image> 2>&1` confirmed "up to date" for unchanged images; `python:3.12-slim-bookworm` returned "Downloaded newer image" confirming new content; OS and package versions verified via `docker run --rm <image> cat /etc/os-release` and `dpkg -l`.
