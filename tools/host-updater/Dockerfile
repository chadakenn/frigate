ARG FRIGATE_VERSION=0.18.0
FROM node:20 AS web-build
ENV NODE_OPTIONS=--max-old-space-size=6144
WORKDIR /work
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build \
    && mv dist/BASE_PATH/monacoeditorwork/* dist/assets/ \
    && rm -rf dist/BASE_PATH

ARG FRIGATE_VERSION
FROM ghcr.io/blakeblackshear/frigate:${FRIGATE_VERSION}
COPY --from=web-build /work/dist/ /opt/frigate/web/
COPY frigate/api/fastapi_app.py frigate/api/updater.py /opt/frigate/frigate/api/
