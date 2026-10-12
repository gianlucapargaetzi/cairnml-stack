FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY packages/mlops-common packages/mlops-common
COPY packages/mlops-server packages/mlops-server
RUN uv pip install --system --no-cache ./packages/mlops-common ./packages/mlops-server
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=12 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/healthz', timeout=3)"
CMD ["uvicorn", "mlops_server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
