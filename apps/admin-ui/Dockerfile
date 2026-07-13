# Pinned 2026-05-18; re-pin every quarter.
FROM node:26-bookworm-slim@sha256:e999d087492c7227c85adc70574cf9d3cce774c3e6d7b8dfe473ee6b142c8f2c
WORKDIR /app

# node:26 images no longer bundle corepack (removed from Node >=25 dists);
# install it from npm before enabling. Broke 'Publish admin-ui' after the
# dependabot bump to node:26 (same failure as the reverted bump in #91).
RUN npm install -g corepack@latest && corepack enable

COPY .npmrc .pnpmfile.cjs package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

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
