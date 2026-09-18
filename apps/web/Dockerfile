# Web (Next.js) container. The server proxies same-origin /api/v1 to the API
# container, keeping session cookies first-party.
FROM node:22-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY . .
# Rewrites are resolved at build time; point them at the compose API service.
ARG API_ORIGIN=http://api:8000
ENV API_ORIGIN=$API_ORIGIN
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/next.config.ts ./next.config.ts

RUN addgroup -S nodejs -g 10001 2>/dev/null || true \
    && adduser -S nextjs -u 10001 -G nodejs 2>/dev/null || true
USER nextjs

EXPOSE 3000
CMD ["npm", "run", "start"]
