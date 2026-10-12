FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker:27-cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY packages/mlops-common packages/mlops-common
COPY packages/mlops-agent packages/mlops-agent
RUN uv pip install --system --no-cache ./packages/mlops-common ./packages/mlops-agent "dvc[s3]>=3.50"
COPY deploy/agent/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
