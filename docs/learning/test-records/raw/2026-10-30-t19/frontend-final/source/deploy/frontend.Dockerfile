FROM public.ecr.aws/docker/library/node:24-bookworm-slim AS build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM public.ecr.aws/docker/library/nginx:1.28-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/frontend/dist/ /usr/share/nginx/html/
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 CMD wget -q -O /dev/null http://127.0.0.1/readyz || exit 1
