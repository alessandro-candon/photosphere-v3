FROM node:22-slim AS builder

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
ENV PHOTOSPHERE_SKIP_BUILD_CONFIG=1
RUN corepack enable

WORKDIR /app

COPY ssr/package.json ssr/pnpm-lock.yaml ssr/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY ssr/ .
RUN pnpm build

FROM node:22-slim AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NITRO_PORT=3000
ENV NITRO_HOST=0.0.0.0

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nuxtjs && \
    mkdir -p /mnt/photosphere && \
    chown -R nuxtjs:nodejs /mnt/photosphere

COPY --from=builder --chown=nuxtjs:nodejs /app/.output ./.output
COPY --from=builder --chown=nuxtjs:nodejs /app/package.json ./package.json

USER nuxtjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/api/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", ".output/server/index.mjs"]
