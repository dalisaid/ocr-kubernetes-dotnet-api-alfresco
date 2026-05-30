import io
import os
import base64
import json
import asyncio
import logging

import aio_pika
import redis.asyncio as aioredis
import httpx
import pytesseract
from PIL import Image

from prometheus_client import Counter, Histogram, generate_latest
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import Response

from opentelemetry import trace, propagate
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engine-tesseract")

# ── Environment ────────────────────────────────────────────────
RABBITMQ_URL   = os.getenv("RABBITMQ_URL",   "amqp://admin:admin@rabbitmq:5672/")
REDIS_URL      = os.getenv("REDIS_URL",      "redis://redis-master:6379")
DOTNET_API_URL = os.getenv("DOTNET_API_URL", "http://dotnet-api:5122/ocrdata")
JOB_TTL        = int(os.getenv("JOB_TTL",   "3600"))
ENGINE_NAME    = "tesseract"

LANG_MAP = {
    "en": "eng",
    "fr": "fra",
    "ar": "ara",
    "de": "deu",
    "es": "spa",
    "zh": "chi_sim",
}

# ── OpenTelemetry ──────────────────────────────────────────────
resource = Resource.create({"service.name": f"ocr-engine-{ENGINE_NAME}"})
provider = TracerProvider(resource=resource)
otlp_exporter = OTLPSpanExporter(
    endpoint=os.getenv("OTEL_ENDPOINT", "otel-collector-opentelemetry-collector:4317"),
    insecure=True
)
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

# ── Prometheus ─────────────────────────────────────────────────
JOBS_PROCESSED = Counter(
    'ocr_jobs_processed_total',
    'Total jobs processed by worker',
    ['engine', 'status']
)
JOB_DURATION = Histogram(
    'ocr_job_duration_seconds',
    'End-to-end job processing time',
    ['engine']
)
OCR_DURATION = Histogram(
    'ocr_engine_duration_seconds',
    'Time spent on OCR processing only',
    ['engine']
)

# ── FastAPI app ────────────────────────────────────────────────
app = FastAPI(title="Tesseract OCR Engine", version="2.0.0")
FastAPIInstrumentor.instrument_app(app)

@app.get("/healthz")
def healthz():
    try:
        pytesseract.get_tesseract_version()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

# Direct HTTP endpoint — kept for testing/debugging
@app.post("/ocr")
async def ocr(file: UploadFile = File(...), lang: str = Query("en")):
    try:
        tess_lang = LANG_MAP.get(lang, "eng")
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        text = pytesseract.image_to_string(image, lang=tess_lang)
        return {"engine": ENGINE_NAME, "text": text.strip()}
    except Exception as e:
        logger.exception("OCR failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")

# ── Worker ─────────────────────────────────────────────────────
async def process_job(message: aio_pika.IncomingMessage):
    async with message.process():
        job = json.loads(message.body)
        job_id   = job["job_id"]
        lang     = job.get("lang", "en")
        tess_lang = LANG_MAP.get(lang, "eng")

        # Extract OTel trace context from message headers
        # This continues the same trace started in the gateway
        ctx = propagate.extract(job.get("trace_context", {}))

        r = aioredis.from_url(REDIS_URL, decode_responses=True)

        with tracer.start_as_current_span(
            f"worker-{ENGINE_NAME}", context=ctx
        ) as span:
            span.set_attribute("ocr.engine",  ENGINE_NAME)
            span.set_attribute("ocr.job_id",  job_id)
            span.set_attribute("ocr.lang",    lang)
            span.set_attribute("ocr.filename", job.get("filename", ""))

            # Mark job as processing in Redis
            await r.setex(f"job:{job_id}", JOB_TTL, json.dumps({
                **job, "status": "processing", "image_b64": ""  # don't store image bytes
            }))

            # ── OCR step ──────────────────────────────────────
            try:
                with OCR_DURATION.labels(engine=ENGINE_NAME).time():
                    with tracer.start_as_current_span("ocr-processing"):
                        image_bytes = base64.b64decode(job["image_b64"])
                        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                        text = pytesseract.image_to_string(image, lang=tess_lang).strip()

                logger.info(f"OCR_SUCCESS job_id={job_id} engine={ENGINE_NAME} text_length={len(text)}")
                JOBS_PROCESSED.labels(engine=ENGINE_NAME, status="ocr_success").inc()

            except Exception as e:
                # Bad image or tesseract crash — do NOT requeue, it will always fail
                logger.error(f"OCR_FAILED job_id={job_id} error={e}")
                JOBS_PROCESSED.labels(engine=ENGINE_NAME, status="ocr_error").inc()
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                await r.setex(f"job:{job_id}", JOB_TTL, json.dumps({
                    "job_id": job_id, "status": "failed",
                    "engine": ENGINE_NAME, "error": str(e)
                }))
                return

            # ── .NET API step ─────────────────────────────────
            try:
                with JOB_DURATION.labels(engine=ENGINE_NAME).time():
                    with tracer.start_as_current_span("dotnet-upload"):
                        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                            api_response = await client.post(
                                DOTNET_API_URL,
                                files={
                                    "file":      (job["filename"], image_bytes, job["content_type"]),
                                    "ocrText":   (None, text),
                                    "ocrEngine": (None, ENGINE_NAME),
                                }
                            )
                            api_response.raise_for_status()

                JOBS_PROCESSED.labels(engine=ENGINE_NAME, status="success").inc()
                await r.setex(f"job:{job_id}", JOB_TTL, json.dumps({
                    "job_id":      job_id,
                    "status":      "done",
                    "engine":      ENGINE_NAME,
                    "filename":    job["filename"],
                    "text_length": len(text),
                }))
                logger.info(f"DOTNET_SUCCESS job_id={job_id} engine={ENGINE_NAME}")
                logger.info(f"JOB_DONE job_id={job_id} engine={ENGINE_NAME}")

            except Exception as e:
                # .NET failure — requeue so it can be retried
                logger.error(f"DOTNET_FAILED job_id={job_id} error={e}")
                JOBS_PROCESSED.labels(engine=ENGINE_NAME, status="dotnet_error").inc()
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))
                await r.setex(f"job:{job_id}", JOB_TTL, json.dumps({
                    "job_id": job_id, "status": "failed",
                    "engine": ENGINE_NAME, "error": str(e)
                }))
                # Raise to trigger requeue
                await message.ack()

        await r.aclose()


async def start_worker():
    """Connects to RabbitMQ and starts consuming jobs indefinitely."""
    # Retry loop — RabbitMQ may not be ready exactly when the pod starts
    while True:
        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            channel    = await connection.channel()
            # One job at a time — OCR is CPU heavy
            await channel.set_qos(prefetch_count=1)
            queue = await channel.declare_queue(f"ocr.{ENGINE_NAME}", durable=True)
            await queue.consume(process_job)
            logger.info(f"Worker listening on ocr.{ENGINE_NAME}")
            # Keep alive
            await asyncio.Future()
        except Exception as e:
            logger.error(f"Worker connection failed: {e} — retrying in 5s")
            await asyncio.sleep(5)


@app.on_event("startup")
async def startup():
    asyncio.create_task(start_worker())
