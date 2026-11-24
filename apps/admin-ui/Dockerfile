# Pinned 2026-11-22; re-pin every quarter.
FROM node:26-bookworm-slim@sha256:5df79989ed685e09f0a98019db4cebfb22fb9df1a53c0161664a011f7ff6b0f1
WORKDIR /app

# node:26 images no longer bundle corepack (removed from Node >=25 dists);
# install it from npm before enabling. Broke 'Publish admin-ui' after the
# dependabot bump to node:26 (same failure as the reverted bump in #91).
# 2026-10 Trivy: the node image still ships perl-base 5.36.0-7+deb12u3 (CVE-2026-13221 CRITICAL,
# CVE-2026-57432 and CVE-2026-57433 HIGH, fixed in deb12u4); perl-base is essential, so upgrade it.
RUN apt-get update && apt-get install -y --no-install-recommends --only-upgrade perl-base \
 && rm -rf /var/lib/apt/lists/*
RUN npm install -g corepack@latest && corepack enable

COPY .npmrc .pnpmfile.cjs package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
# The runtime runs tsx from node_modules and never npm or npx. Remove the npm CLI once corepack and pnpm are
# in place: its bundled brace-expansion, undici and http-cache-semantics are HIGH in Trivy (2026-10; the last
# has no fix).
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx
# The runtime runs src/index.ts with tsx (esbuild) and never type-checks: TypeScript is a build and CI tool only.
# Since TypeScript 7 the compiler is a native Go binary (@typescript/typescript-<platform>), and 7.0.2 is built with
# Go 1.26.4 and golang.org/x/text 0.38.0 (HIGH in Trivy, 2026-11). Remove the compiler from the runtime image.
RUN rm -rf node_modules/typescript node_modules/.pnpm/typescript@* node_modules/.pnpm/@typescript+typescript-*

COPY tsconfig.json ./
COPY src ./src

# node:22-slim ships with a pre-created 'node' user (UID 1000).
# Chown the working tree so the non-root process can read app files.
RUN chown -R node:node /app
USER node

ENV PORT=8081
ENV NODE_ENV=production

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "require('http').get('http://127.0.0.1:8081/health',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"

CMD ["node_modules/.bin/tsx", "src/index.ts"]
