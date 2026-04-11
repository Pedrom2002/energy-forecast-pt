# syntax=docker/dockerfile:1.6
#
# Multi-stage build for the Vite + React frontend.
#
# Stage 1 (builder): node image that installs npm deps and runs `npm run
#   build`, producing the static bundle in /app/dist.
# Stage 2 (runtime): nginx:alpine (~25 MB) serving the static files with
#   SPA fallback. No node, no npm, no source code in the final image.
#
# Expected image size: ~30-45 MB.

# ----------------------------------------------------------------------------
# Stage 1: builder
# ----------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

ENV NODE_ENV=production \
    CI=true

# Install dependencies first to maximise layer cache reuse. Using `npm ci`
# for reproducible installs from package-lock.json. We need devDependencies
# here because vite/typescript/tailwind live there.
COPY package.json package-lock.json ./
RUN npm ci --include=dev --no-audit --no-fund

# Copy the rest of the source and build.
COPY . .
RUN npm run build

# ----------------------------------------------------------------------------
# Stage 2: runtime (nginx serving static files)
# ----------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Minimal SPA-friendly nginx config: gzip + history API fallback + caching
# for hashed Vite assets.
RUN rm /etc/nginx/conf.d/default.conf
COPY <<'NGINX' /etc/nginx/conf.d/default.conf
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript
               text/xml application/xml application/xml+rss text/javascript
               image/svg+xml;
    gzip_min_length 1024;

    # Long-cache hashed assets emitted by Vite.
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    # SPA fallback: any unknown path returns index.html so the React
    # router can handle it client-side.
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Never cache the entrypoint so new deploys are picked up immediately.
    location = /index.html {
        add_header Cache-Control "no-store, no-cache, must-revalidate";
    }
}
NGINX

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
