FROM python:3.10

# System deps required by PaddleOCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# CRITICAL — prevents oneDNN/MKLDNN crash on CPU-only environments
ENV FLAGS_use_mkldnn=false

WORKDIR /app

# numpy pinned — PaddleOCR 2.7.0.3 is incompatible with numpy 2.x
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pillow \
    numpy==1.26.4 \
    python-multipart \
    paddlepaddle==2.6.2 \
    paddleocr==2.7.0.3 \
    aio-pika \
    redis[asyncio] \
    httpx \
    prometheus-client \
    opentelemetry-api \
    opentelemetry-sdk \
    opentelemetry-exporter-otlp \
    opentelemetry-exporter-otlp-proto-grpc \
    opentelemetry-instrumentation-fastapi

COPY main.py .

EXPOSE 8003

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
