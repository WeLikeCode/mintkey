# Pinned 2026-05-18; re-pin every quarter.
FROM node:26-bookworm-slim@sha256:d2ec0a1766c01dad04a185c2d5558b0adace167a7f1758ce80f0017698431d06
WORKDIR /app

RUN corepack enable

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
