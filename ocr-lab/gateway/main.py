import os
import httpx
from prometheus_client import Counter, generate_latest,Histogram
import logging
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import JSONResponse,Response


from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor





logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway")

app = FastAPI(title="OCR Gateway", version="1.0.0")

# Engine service URLs — resolved via Kubernetes DNS
ENGINE_URLS = {
    "tesseract": os.getenv("TESSERACT_URL", "http://engine-tesseract:8001"),
    "easyocr":   os.getenv("EASYOCR_URL",   "http://engine-easyocr:8002"),
    "paddle":    os.getenv("PADDLE_URL",     "http://engine-paddle:8003"),
}

DOTNET_API_URL = "http://host.docker.internal:5122/ocrdata"  # Placeholder for .NET API URL


TIMEOUT = httpx.Timeout(60.0)

REQUEST_COUNT = Counter(
    'ocr_requests_total',
    'Total OCR requests',
    ['engine', 'status']
)

OCR_LATENCY = Histogram(
    'ocr_processing_seconds',
    'OCR processing time',
    ['engine']
)
DOTNET_LATENCY = Histogram(
    'dotnet_processing_seconds',
    'Time to send data to .NET API'
)

ERROR_COUNT = Counter(
    'ocr_errors_total',
    'Total OCR errors',
    ['engine']
)


resource = Resource.create({
    "service.name": "ocr-gateway"
})

provider = TracerProvider(resource=resource)

otlp_exporter = OTLPSpanExporter(
    endpoint="otel-collector-opentelemetry-collector:4317",
    insecure=True
)

provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(provider)

FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
tracer = trace.get_tracer(__name__)

@app.get("/healthz", tags=["health"])
def healthz():
    return {"status": "ok"}


@app.get("/engines", tags=["info"])
def list_engines():
    """Return the list of available OCR engines."""
    return {"engines": list(ENGINE_URLS.keys())}


import json
@app.post("/ocr", tags=["ocr"])
async def run_ocr(
    file: UploadFile = File(...),
    engine: str = Query("tesseract", enum=["tesseract", "easyocr", "paddle"]),
    lang: str = Query("en"),
):
    REQUEST_COUNT.labels(engine=engine, status="received").inc()    

    target = ENGINE_URLS.get(engine)
    if not target:
        REQUEST_COUNT.labels(engine=engine, status="error").inc()
        raise HTTPException(status_code=400, detail=f"Unknown engine '{engine}'")

    image_bytes = await file.read()
    if not image_bytes:
        REQUEST_COUNT.labels(engine=engine, status="error").inc()
        raise HTTPException(status_code=400, detail="Empty file")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        
        # 🔹 OCR STEP (STRICT)
        try:
            
            with tracer.start_as_current_span(f"ocr-{engine}") as span:
                span.set_attribute("ocr.engine", engine)
                with OCR_LATENCY.labels(engine=engine).time():
                    response = await client.post(
                        f"{target}/ocr",
                        files={"file": (file.filename, image_bytes, file.content_type)},
                        params={"lang": lang},
                    )

            response.raise_for_status()

            ocr_data = response.json()
            text = ocr_data.get("text", "")
            logger.info( 
            f"OCR_SUCCESS engine={engine} "
            f"filename={file.filename} "
            f"text_length={len(text)}"
            )

            

            REQUEST_COUNT.labels(engine=engine, status="success").inc()


        except httpx.ConnectError as exc:
            ERROR_COUNT.labels(engine=engine).inc()
            REQUEST_COUNT.labels(engine=engine, status="error").inc()
            logger.error(
            f"OCR_ERROR engine={engine} error={str(exc)}"
            )
            raise HTTPException(status_code=503, detail=f"Engine '{engine}' unreachable")

        except httpx.HTTPStatusError as exc:
            ERROR_COUNT.labels(engine=engine).inc()
            REQUEST_COUNT.labels(engine=engine, status="error").inc()
            logger.error(
            f"OCR_ERROR engine={engine} error={str(exc)}"
            )
            raise HTTPException(status_code=502, detail=exc.response.text)

        except Exception as exc:
            ERROR_COUNT.labels(engine=engine).inc()
            REQUEST_COUNT.labels(engine=engine, status="error").inc()
            logger.error(
            f"OCR_ERROR engine={engine} error={str(exc)}"
            )
            raise HTTPException(status_code=500, detail=str(exc))
        
     
               
        

        # 🔹 .NET STEP 
        dotnet_result = None

        try:
            files = {
                "file": (file.filename, image_bytes, file.content_type),
                "ocrText": (None, text),
                "ocrEngine": (None, engine)
            }
            with tracer.start_as_current_span("dotnet-send") as span:
                span.set_attribute("component", "dotnet")
                with DOTNET_LATENCY.time():
                    apiresponse = await client.post(DOTNET_API_URL, files=files)

            logger.info(
            f"DOTNET_UPLOAD engine={engine} "
            f"status={apiresponse.status_code}"
            )
            if apiresponse.status_code == 200:
                dotnet_result = {
                    "success": True,
                    "data": apiresponse.json()
                }
            else:
                dotnet_result = {
                    "success": False,
                    "status": apiresponse.status_code,
                    "error": apiresponse.text
                }

        except Exception as e:
            dotnet_result = {
                "success": False,
                "error": str(e)
            }
            logger.error(
            f"DOTNET_ERROR engine={engine} error={str(e)}"
            )

    # 🔹 Final response (outside client block)
    return JSONResponse(content={
        "ocr": ocr_data,
        "dotnet": dotnet_result
    })
@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")

@app.get("/debug-trace")
def debug_trace():
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("manual-test-span"):
        return {"ok": "trace created"}