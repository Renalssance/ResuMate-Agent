ARG NODE_IMAGE=docker.m.daocloud.io/library/node:22-alpine
ARG NGINX_IMAGE=docker.m.daocloud.io/library/nginx:1.27-alpine

FROM ${NODE_IMAGE} AS build

ARG NPM_REGISTRY=https://mirrors.tuna.tsinghua.edu.cn/npm/

WORKDIR /app
ENV NPM_CONFIG_REGISTRY=${NPM_REGISTRY}
COPY package*.json ./
RUN npm ci --cache /root/.npm --prefer-offline --registry=${NPM_REGISTRY}
COPY . .
RUN npm run build

FROM ${NGINX_IMAGE}
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
