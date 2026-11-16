# syntax=docker/dockerfile:1
# statline/api: multi-stage build. Context is the repo root (pnpm workspace):
#   docker build -f services/api/Dockerfile -t statline/api:local .

FROM node:20-alpine AS base
RUN apk add --no-cache openssl
RUN corepack enable
WORKDIR /repo

FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY services/api/package.json services/api/
RUN pnpm install --frozen-lockfile --filter @statline/api...

FROM deps AS build
COPY services/api services/api
WORKDIR /repo/services/api
# prisma (the CLI) is a runtime dependency: the initContainer runs `prisma migrate deploy`.
RUN pnpm prisma generate && pnpm build \
 && pnpm deploy --filter @statline/api --prod --legacy /out \
 && cp -r prisma /out/prisma \
 && cd /out && ./node_modules/.bin/prisma generate

FROM node:20-alpine AS runtime
RUN apk add --no-cache openssl
ENV NODE_ENV=production PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /out ./
COPY --from=build --chown=node:node /repo/services/api/dist ./dist
USER node
EXPOSE 3000
# Migrations run in the Deployment's initContainer (`npx prisma migrate deploy`), not here.
CMD ["node", "dist/server.js"]
