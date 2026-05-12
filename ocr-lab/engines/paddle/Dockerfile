FROM python:3.10

# System deps required by PaddleOCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Disable MKLDNN (prevents oneDNN crash)
ENV FLAGS_use_mkldnn=false

WORKDIR /app

RUN pip install --no-cache-dir \
   
    fastapi \
    uvicorn \
    pillow \
    numpy==1.26.4 \
    python-multipart \
    paddlepaddle==2.6.2 \
    paddleocr==2.7.0.3



COPY main.py .

EXPOSE 8003

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]