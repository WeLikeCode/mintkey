FROM node:22-slim
WORKDIR /app

RUN corepack enable

COPY .npmrc .pnpmfile.cjs package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY tsconfig.json ./
COPY src ./src

ENV PORT=8081
ENV NODE_ENV=production

CMD ["node_modules/.bin/tsx", "src/index.ts"]
