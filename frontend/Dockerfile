FROM node:22-alpine AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

FROM nginx/nginx-unprivileged:alpine AS runtime

ENV PORT=8080 \
    API_UPSTREAM=backend:8000 \
    NGINX_ENVSUBST_FILTER=^(PORT|API_UPSTREAM)$

COPY --from=build /app/dist/ /usr/share/nginx/html/
COPY frontend/nginx/default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -q --spider "http://127.0.0.1:${PORT:-8080}/health" || exit 1
