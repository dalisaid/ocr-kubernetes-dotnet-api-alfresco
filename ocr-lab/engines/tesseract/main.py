import io
import logging
import pytesseract
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engine-tesseract")

app = FastAPI(title="Tesseract OCR Engine", version="1.0.0")

LANG_MAP = {
    "en": "eng",
    "fr": "fra",
    "ar": "ara",
    "de": "deu",
    "es": "spa",
    "zh": "chi_sim",
}


@app.get("/healthz")
def healthz():
    try:
        pytesseract.get_tesseract_version()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

# OCR endpoint with language support (default is English)
@app.post("/ocr")
async def ocr(file: UploadFile = File(...), lang: str = Query("en")):
    try:
        tess_lang = LANG_MAP.get(lang, "eng")

        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        text = pytesseract.image_to_string(image, lang=tess_lang)

        return {
            "engine": "tesseract",
            "text": text.strip()
        }

    except Exception as e:
        logger.exception("OCR failed")
        raise HTTPException(status_code=500, detail=str(e))