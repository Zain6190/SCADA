# ── Stage 1: Build Next.js static export ──────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

# The static export is consumed by the BROWSER on the host, so the default
# must be host-reachable - docker-internal names like aquavision don't resolve
# there and every auth/API call silently fails.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8100
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

RUN npm run build

# ── Stage 2: Serve with nginx ─────────────────────────────────
FROM nginx:alpine

# Custom config: SPA routing + cache policy (HTML revalidates, hashed
# /_next/static assets immutable). See nginx.conf for details.
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/out /usr/share/nginx/html

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
