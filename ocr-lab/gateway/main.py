import os
import uuid
import json
import base64
import asyncio
import logging

import aio_pika
import redis.asyncio as aioredis
import httpx

from prometheus_client import Counter, Histogram, generate_latest
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import inject

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway")

app = FastAPI(title="OCR Gateway", version="2.0.0")

# ── Environment ────────────────────────────────────────────────
RABBITMQ_URL   = os.getenv("RABBITMQ_URL",  "amqp://admin:admin@rabbitmq:5672/")
REDIS_URL      = os.getenv("REDIS_URL",     "redis://redis-master:6379")
JOB_TTL        = int(os.getenv("JOB_TTL",  "3600"))   # seconds — how long job status lives in Redis

# Engine URLs kept for /engines info endpoint and legacy direct calls if needed
ENGINE_URLS = {
    "tesseract": os.getenv("TESSERACT_URL", "http://engine-tesseract:8001"),
    "easyocr":   os.getenv("EASYOCR_URL",   "http://engine-easyocr:8002"),
    "paddle":    os.getenv("PADDLE_URL",     "http://engine-paddle:8003"),
}

# ── OpenTelemetry ──────────────────────────────────────────────
resource = Resource.create({"service.name": "ocr-gateway"})
provider = TracerProvider(resource=resource)
otlp_exporter = OTLPSpanExporter(
    endpoint="otel-collector-opentelemetry-collector:4317",
    insecure=True
)
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()

# ── Prometheus ─────────────────────────────────────────────────
REQUEST_COUNT = Counter(
    'ocr_requests_total',
    'Total OCR requests received by gateway',
    ['engine', 'status']
)
PUBLISH_LATENCY = Histogram(
    'ocr_publish_seconds',
    'Time to publish job to RabbitMQ',
    ['engine']
)

# ── Shared async clients (created once on startup) ─────────────
_redis: aioredis.Redis = None
_rmq_connection: aio_pika.RobustConnection = None

@app.on_event("startup")
async def startup():
    global _redis, _rmq_connection
    _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    _rmq_connection = await aio_pika.connect_robust(RABBITMQ_URL)
    logger.info("Gateway connected to Redis and RabbitMQ")

@app.on_event("shutdown")
async def shutdown():
    if _rmq_connection:
        await _rmq_connection.close()
    if _redis:
        await _redis.aclose()

# ── Health ─────────────────────────────────────────────────────
@app.get("/healthz", tags=["health"])
def healthz():
    return {"status": "ok"}

# ── Engines info ───────────────────────────────────────────────
@app.get("/engines", tags=["info"])
def list_engines():
    return {"engines": list(ENGINE_URLS.keys())}

# ── Job status poll ────────────────────────────────────────────
@app.get("/jobs/{job_id}", tags=["ocr"])
async def get_job(job_id: str):
    raw = await _redis.get(f"job:{job_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    return JSONResponse(content=json.loads(raw))

# ── Main OCR endpoint — now async, returns 202 immediately ─────
@app.post("/ocr", tags=["ocr"])
async def run_ocr(
    file: UploadFile = File(...),
    engine: str = Query("tesseract", enum=["tesseract", "easyocr", "paddle"]),
    lang: str = Query("en"),
):
    REQUEST_COUNT.labels(engine=engine, status="received").inc()

    image_bytes = await file.read()
    if not image_bytes:
        REQUEST_COUNT.labels(engine=engine, status="error").inc()
        raise HTTPException(status_code=400, detail="Empty file")

    job_id = str(uuid.uuid4())

    # Inject OTel trace context into message headers
    # so the worker can continue the same trace span end-to-end
    carrier = {}
    inject(carrier)

    message_body = json.dumps({
        "job_id":       job_id,
        "filename":     file.filename,
        "content_type": file.content_type,
        "image_b64":    base64.b64encode(image_bytes).decode(),
        "lang":         lang,
        "engine":       engine,
        "trace_context": carrier,         # OTel propagation headers
    }).encode()

    # Publish to RabbitMQ
    try:
        with tracer.start_as_current_span("publish-job") as span:
            span.set_attribute("ocr.engine", engine)
            span.set_attribute("ocr.job_id", job_id)

            with PUBLISH_LATENCY.labels(engine=engine).time():
                channel = await _rmq_connection.channel()
                queue   = await channel.declare_queue(
                    f"ocr.{engine}",
                    durable=True
                )
                await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=message_body,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        content_type="application/json",
                    ),
                    routing_key=f"ocr.{engine}",
                )

        REQUEST_COUNT.labels(engine=engine, status="queued").inc()
        logger.info(f"JOB_QUEUED job_id={job_id} engine={engine} filename={file.filename}")

    except Exception as exc:
        REQUEST_COUNT.labels(engine=engine, status="error").inc()
        logger.error(f"PUBLISH_ERROR engine={engine} error={exc}")
        raise HTTPException(status_code=503, detail="Failed to queue job")

    # Write initial status to Redis
    await _redis.setex(
        f"job:{job_id}",
        JOB_TTL,
        json.dumps({
            "job_id":   job_id,
            "status":   "queued",
            "engine":   engine,
            "filename": file.filename,
            "lang":     lang,
        })
    )

    return JSONResponse(
        status_code=202,
        content={
            "job_id":      job_id,
            "status":      "queued",
            "engine":      engine,
            "status_url":  f"/jobs/{job_id}",
        }
    )

# ── Metrics ────────────────────────────────────────────────────
@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")

# ── Debug trace ────────────────────────────────────────────────
@app.get("/debug-trace")
def debug_trace():
    with tracer.start_as_current_span("manual-test-span"):
        return {"ok": "trace created"}
