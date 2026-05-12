

This is an extensible microservice platform for running OCR using 3 interchangeable backends:
- `tesseract` (pytesseract)
- `easyocr` (EasyOCR)
- `paddle` (PaddleOCR)

A central `gateway` routes image upload requests to one of the engines via a uniform `/ocr` API.

## Project Structure

- `gateway/`
  - `main.py`: FastAPI proxy for engine routing, health checks, engine list
  - `Dockerfile`
- `engines/tesseract/`, `engines/easyocr/`, `engines/paddle/`
  - `main.py`: engine-specific OCR service exposing `/healthz` and `/ocr`
  - `Dockerfile`
- `k8s/`
  - Kubernetes manifests for gateway and engines

## Features

- Single unified OCR endpoint exposed at `gateway`:
  - `POST /ocr` with `file` (image), `engine` (tesseract|easyocr|paddle), `lang`
- Engine health checks via `/healthz`
- Engine discovery via `GET /engines`
- Language hint support

## API

### Gateway

- `GET /healthz`
  - returns `{ "status": "ok" }`

- `GET /engines`
  - returns `{ "engines": ["tesseract","easyocr","paddle"] }`

- `POST /ocr`
  - form-data fields:
    - `file`: image file (PNG, JPG, TIFF, BMP, etc.)
    - `engine`: `tesseract` | `easyocr` | `paddle` (default: `tesseract`)
    - `lang`: language code (`en`, `fr`, `ar`, ...)
  - success response:
    - `{ "engine": "<name>", "text": "..." }`

### Engine (all)

- `GET /healthz`
- `POST /ocr` (same input as gateway, but only one engine)

## Local Development (Docker + Kubernetes)

### Kubernetes

Use manifests under `k8s/`:
- `namespace.yaml`
- `engine-tesseract.yaml`
- `engine-easyocr.yaml`
- `engine-paddle.yaml`
- `gateway.yaml`

Example:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/engine-tesseract.yaml
kubectl apply -f k8s/engine-easyocr.yaml
kubectl apply -f k8s/engine-paddle.yaml
kubectl apply -f k8s/gateway.yaml
```

Then verify:

```bash
kubectl -n ocr-lab get pods
```

### Direct docker (manual)

Build each image:

```bash
docker build -t ocr-gateway ./gateway
docker build -t ocr-engine-tesseract ./engines/tesseract
docker build -t ocr-engine-easyocr ./engines/easyocr
docker build -t ocr-engine-paddle ./engines/paddle
```


## Example Request

```bash
curl -X POST "http://localhost:8000/ocr?engine=tesseract&lang=en" \
  -F "file=@/path/to/document.png" \
  -H "Content-Type: multipart/form-data"
```

## Dependencies

Each subproject has its own dependencies. Inspect Dockerfiles for exact versions and requirements.

- `gateway` uses `fastapi`, `uvicorn`, `httpx`
- `engine/tesseract` uses `fastapi`, `uvicorn`, `pytesseract`, `Pillow`
- `engine/easyocr` uses `easyocr`, `numpy`, `Pillow`
- `engine/paddle` uses `paddleocr`, `numpy`, `Pillow`

## Notes

- `easyocr` downloads models at runtime (`download_enabled=True`)
- `paddleocr` may download weights on first run
- `tesseract` requires `tesseract` binary installed in environment




