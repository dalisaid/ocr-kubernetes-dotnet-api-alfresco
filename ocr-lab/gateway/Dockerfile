FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn httpx python-multipart prometheus-client \
    opentelemetry-api opentelemetry-sdk \
    opentelemetry-exporter-otlp \
    opentelemetry-exporter-otlp-proto-grpc \
    opentelemetry-instrumentation-fastapi \
    opentelemetry-instrumentation-httpx

COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
