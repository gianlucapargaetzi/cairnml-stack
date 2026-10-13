# The explorer (the Aim UI fork) is built here and copied into the image. No Node at runtime.
FROM node:24 AS ui-builder
ENV NODE_OPTIONS=--openssl-legacy-provider
WORKDIR /build
COPY packages/mlops-ui .
RUN npm ci && npm run build && node tasks/check-bundle-hosts.js build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY packages/mlops-common packages/mlops-common
COPY packages/mlops-server packages/mlops-server
COPY --from=ui-builder /build/build packages/mlops-server/src/mlops_server/ui/next
RUN uv pip install --system --no-cache ./packages/mlops-common ./packages/mlops-server
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=12 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/healthz', timeout=3)"
CMD ["uvicorn", "mlops_server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
