import io
import logging
import numpy as np

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engine-paddle")

app = FastAPI(title="PaddleOCR Engine", version="1.0.0")

_ocr_instance = None

# PaddleOCR factory with caching 
def get_ocr(lang="en"):
    global _ocr_instance

    if _ocr_instance is None:
        from paddleocr import PaddleOCR

        logger.info(f"Initializing PaddleOCR ({lang})")

        _ocr_instance = PaddleOCR(
            use_angle_cls=True,
            lang=lang
            
            
        )

    return _ocr_instance

# Preload English reader on startup for faster health checks ,get_ocr("languages here example: en,fr,ar")
@app.on_event("startup")
def preload():
    try:
        get_ocr("en")
        logger.info("PaddleOCR ready")
    except Exception as e:
        logger.error(f"Startup failed: {e}")


@app.get("/healthz")
def healthz():
    if _ocr_instance is None:
        raise HTTPException(status_code=503, detail="Not ready")
    return {"status": "ok"}


@app.post("/ocr")
async def ocr(file: UploadFile = File(...), lang: str = Query("en")):
    try:
        ocr_engine = get_ocr(lang)

        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image = np.array(image)

        result = ocr_engine.ocr(image)

        lines = []
        if result and result[0]:
            for line in result[0]:
                lines.append(line[1][0])

        return {
            "engine": "paddle",
            "text": "\n".join(lines)
        }

    except Exception as e:
        logger.exception("OCR failed")
        raise HTTPException(status_code=500, detail=str(e))