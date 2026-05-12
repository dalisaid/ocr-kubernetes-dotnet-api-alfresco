import io
import logging
import numpy as np
import easyocr
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engine-easyocr")

app = FastAPI(title="EasyOCR Engine", version="1.0.0")

_reader_cache = {}

 # EasyOCR reader factory with caching  
def get_reader(lang: str):
    langs = [l.strip() for l in lang.split(",")]
    key = ",".join(sorted(langs))

    if key not in _reader_cache:
        logger.info(f"Loading EasyOCR reader for {langs}")

        _reader_cache[key] = easyocr.Reader(
            langs,
            download_enabled=True,   # ✅ IMPORTANT FIX
            gpu=False
        )

    return _reader_cache[key]

# Preload English reader on startup for faster health checks ,get_reader("languages here example: en,fr,ar")
@app.on_event("startup")
def preload():
    try:
        get_reader("en")
        logger.info("EasyOCR ready")
    except Exception as e:
        logger.error(f"Startup failed: {e}")


@app.get("/healthz")
def healthz():
    if not _reader_cache:
        raise HTTPException(status_code=503, detail="Not ready")
    return {"status": "ok"}


@app.post("/ocr")
async def ocr(file: UploadFile = File(...), lang: str = Query("en")):
    try:
        reader = get_reader(lang)

        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image = np.array(image)

        results = reader.readtext(image, detail=0)
        return {
            "engine": "easyocr",
            "text": "\n".join(results)
        }

    except Exception as e:
        logger.exception("OCR failed")
        raise HTTPException(status_code=500, detail=str(e))