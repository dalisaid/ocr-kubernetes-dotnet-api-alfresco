# OCR Lab — Kubernetes Multi-Engine OCR Platform

A Kubernetes-based OCR solution that routes image OCR requests through a **FastAPI Gateway** to one of three pluggable OCR engines (**Tesseract**, **EasyOCR**, **PaddleOCR**), processes results through a **.NET API**, and archives them in **Alfresco**. Includes integrated observability with **Prometheus**, **Grafana**, **Loki**, and **Tempo**.

```
                    ┌──────────────────────────────────────────────────────────┐
                    │              ocr-lab namespace (Kubernetes)               │
                    │                                                           │
  POST /ocr         │  ┌─────────┐    http   ┌──────────────────────────────┐  │
  + image + engine  ├─►│ Gateway ├─────────►│  OCR Engines                  │  │
                    │  │ :8000   │          │  ├─ Tesseract   (:8001)      │  │
                    │  └────┬────┘          │  ├─ EasyOCR     (:8002)      │  │
                    │       │               │  └─ PaddleOCR   (:8003)      │  │
                    │       │               └──────────────────────────────┘  │
                    │       │                                                  │
                    └───────┼──────────────────────────────────────────────────┘
                            │
                    ┌───────▼──────────────────────────────────┐
                    │  .NET API (dotnet-api)                  │
                    │  POST /ocrdata                          │
                    │  (Receives OCR text + metadata)         │
                    │                                         │
                    │                                         │
                    │  └─ Alfresco: File & metadata archive   │
                    └───────┬──────────────────────────────────┘
                            │
                    ┌───────▼──────────────────────────────────┐
                    │  Alfresco (Content Repository)          │
                    │  ├─ OCR Results                         │
                    │  ├─ Original Images                     │
                    │  └─ CMIS Access                         │
                    └────────────────────────────────────────┘

    ┌─────────────────────── Observability Stack ───────────────────────────┐
    │  Prometheus (:30090) → Grafana (:30000) ← Loki + Tempo (Traces)      │
    │  Metrics: requests, errors, latency, k8s health, .NET API metrics     │
    └────────────────────────────────────────────────────────────────────────┘
```

---

## Architecture Overview

### OCR Gateway + Engines (Kubernetes)
FastAPI gateway routes `/ocr` POST requests to one of three OCR engines running in separate pods. Each engine loads large ML models (especially EasyOCR and PaddleOCR) 

### .NET API Integration
The **dotnet-api**  receives OCR results via the `/ocrdata` endpoint. It:
- Accepts multipart form data: `file` (original image), `ocrText` (OCR result), `ocrEngine` (which engine processed it)
- Uploads processed files to **Alfresco** via a REST api with metadata


### Observability (Monitoring Stack)
- **Prometheus**: Scrapes metrics from gateway, engines, .NET API, and Kubernetes
- **Grafana**: Unified dashboard with request rates, error rates, latency (p50/p95/p99), engine performance, pod health, CPU/memory usage
- **Loki**: Aggregates container logs, allows filtering by component (gateway, engines, .NET API)
- **Tempo**: Distributed tracing for request flows from gateway → engines → .NET API
- **OpenTelemetry Collector**: Ingests and forwards traces

---

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| Docker | 20.x |
| minikube **or** any local k8s (kind, k3s) | latest |
| kubectl | matching your cluster |
| Helm | 3.x |

---

## Project Structure

```
ocr-lab/
├── k8s/
│   ├── namespace.yaml          # ocr-lab namespace
│   ├── models-pv.yaml          # PersistentVolume + PVC for model storage
│   ├── gateway.yaml            # Gateway Deployment + NodePort Service
│   ├── engine-tesseract.yaml   # Tesseract Deployment + ClusterIP Service
│   ├── engine-easyocr.yaml     # EasyOCR Deployment + ClusterIP Service
│   └── engine-paddle.yaml      # PaddleOCR Deployment + ClusterIP Service
├── gateway/
│   ├── main.py                 # FastAPI router
│   └── Dockerfile
└── engines/
    ├── tesseract/
    │   ├── main.py             # Tesseract wrapper
    │   └── Dockerfile
    ├── easyocr/
    │   ├── main.py             # EasyOCR wrapper
    │   └── Dockerfile
    └── paddle/
        ├── main.py             # PaddleOCR wrapper
        └── Dockerfile
```

---




build:

```bash
# Gateway
docker build -t ocr-lab/gateway:latest ./gateway

# Engines
docker build -t ocr-lab/engine-tesseract:latest ./engines/tesseract
docker build -t ocr-lab/engine-easyocr:latest   ./engines/easyocr
docker build -t ocr-lab/engine-paddle:latest    ./engines/paddle
```



---

### · Apply Kubernetes manifests

```bash
# Apply in order — namespace first, then storage, then workloads
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/models-pv.yaml
kubectl apply -f k8s/gateway.yaml
kubectl apply -f k8s/engine-tesseract.yaml
kubectl apply -f k8s/engine-easyocr.yaml
kubectl apply -f k8s/engine-paddle.yaml
```

---

### · Wait for all pods to become Ready

```bash
kubectl get pods -n ocr-lab -w
```

Expected output (EasyOCR/Paddle take longer on first start due to model downloads):

```
NAME                                READY   STATUS    RESTARTS   AGE
gateway-7d9f6b-xxxx                 1/1     Running   0          30s
engine-tesseract-5c8b4d-xxxx        1/1     Running   0          30s
engine-easyocr-6f7a2c-xxxx          0/1     Running   0          45s   ← startup probe running
engine-paddle-8e3d1b-xxxx           0/1     Running   0          45s   ← startup probe running
```

Once all show `1/1 Running`, the startup probes have passed and the gateway will
begin routing traffic to them.

---

---

### · Deploy Monitoring Stack (Optional but Recommended)

The monitoring stack uses **Helm** charts to deploy Prometheus, Grafana, Loki, and Tempo.

First, add the Helm repositories:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update
```

Then deploy each component:

```bash
# Prometheus (metrics collection, NodePort 30090)
helm install prometheus prometheus-community/prometheus \
  -n ocr-lab -f ocr-lab/monitoring/prometheus-values.yaml

# Loki (log aggregation)
helm install loki grafana/loki-stack -n ocr-lab

# Tempo (distributed tracing)
helm install tempo grafana/tempo -n ocr-lab

# OpenTelemetry Collector (telemetry ingestion)
helm install otel-collector open-telemetry/opentelemetry-collector \
  -n ocr-lab -f ocr-lab/monitoring/otel-values.yaml

# Grafana (dashboard, NodePort 30000, credentials: admin/admin)
helm install grafana grafana/grafana \
  -n ocr-lab -f ocr-lab/monitoring/grafana-values.yaml
```

Apply Grafana dashboards and RBAC:

```bash
kubectl apply -f ocr-lab/monitoring/dashboard.yaml -n ocr-lab #or just import it inside grafana ui
kubectl apply -f ocr-lab/monitoring/rbac.yaml -n ocr-lab
```

Access Grafana:


Login with **admin/admin** and navigate to the **"OCR Observability Platform"** dashboard. It includes:

- **Request Overview**: Total requests, errors, error rate, p95 OCR latency, p95 .NET latency, gateway status
- **Request Throughput**: Request rate by engine, success vs error rate
- **Processing Latency**: p50/p95/p99 latency for each OCR engine and .NET API
- **Error Tracking**: Error counts by engine, error rate percentage
- **Kubernetes Health**: Running pods, failed pods, pod restarts, CPU/memory usage, pod-level metrics
- **Distributed Traces**: Recent gateway traces from Tempo, correlated with logs
- **Logs**: Success logs, error logs, .NET API upload activity via Loki

#### Prometheus Metrics Collected

| Job | Target | Port | Metrics |
|-----|--------|------|---------|
| ocr-gateway | gateway:8000 | 8000 | ocr_requests_total, ocr_errors_total, ocr_processing_seconds_bucket |
| engine-tesseract | engine-tesseract:8001 | 8001 | engine_requests_total, engine_processing_seconds_bucket |
| engine-easyocr | engine-easyocr:8002 | 8002 | engine_requests_total, engine_processing_seconds_bucket |
| engine-paddle | engine-paddle:8003 | 8003 | engine_requests_total, engine_processing_seconds_bucket |
| dotnet-api | host.docker.internal:5122 | 5122 | dotnet_processing_seconds_bucket, http_requests_total |
| kubernetes-cadvisor | kubernetes.default.svc:443 | — | container_cpu_usage, container_memory_working_set |
| kube-state-metrics | prometheus-kube-state-metrics:8080 | 8080 | kube_pod_status_phase, kube_pod_container_status_restarts_total |



## Ports Reference

| Service          | Internal port | NodePort |
|------------------|---------------|----------|
| Gateway          | 8000          | 30080    |
| Engine Tesseract | 8001          | —        |
| Engine EasyOCR   | 8002          | —        |
| Engine PaddleOCR | 8003          | —        |

Engine services are `ClusterIP` — they are only reachable from inside the cluster (i.e. from the gateway pod).

---

## End-to-End OCR + Storage Workflow

### Step 1: Send an OCR Request to the Gateway

Get the gateway URL:

```bash
minikube service gateway -n ocr-lab --url
# e.g. http://192.168.49.2:30080
```

Send an OCR request with an image file:

```bash
# Example with Tesseract
curl -s -X POST http://192.168.49.2:30080/ocr \
  -F "engine=tesseract" \
  -F "file=@/path/to/your/image.png" | python3 -m json.tool

# Example with EasyOCR
curl -s -X POST http://192.168.49.2:30080/ocr \
  -F "engine=easyocr" \
  -F "file=@/path/to/your/image.png" | python3 -m json.tool

# Example with PaddleOCR
curl -s -X POST http://192.168.49.2:30080/ocr \
  -F "engine=paddle" \
  -F "file=@/path/to/your/image.png" | python3 -m json.tool
```

Example gateway response:

```json
{
  "engine": "tesseract",
  "text": "Hello, World!"
}
```

### Step 2: Upload OCR Result to .NET API → Alfresco

The **dotnet-api** runs on `localhost:5122` and receives OCR results via the `/ocrdata` endpoint.

```bash
# Send OCR result to .NET API for archival
curl -s -X POST http://localhost:5122/ocrdata \
  -F "file=@/path/to/your/image.png" \
  -F "ocrText=Hello, World!" \
  -F "ocrEngine=tesseract"
```

The .NET API will:
1. Upload the image to Alfresco with OCR text as metadata
2. Return the Alfresco node ID

Example response:

```json
{
  "message": "Uploaded to Alfresco",
  "nodeId": "workspace://SpacesStore/uuid-1234",
  "engine": "tesseract"
}
```

## .NET API Configuration

The **dotnet-api** requires configuration for Alfresco. Set these environment variables or in `appsettings.Development.json`:

```json
{
  "Alfresco": {
    "BaseUrl": "http://alfresco-server:8080",
    "Username": "admin",
    "Password": "admin",
    "FolderNodeId": "workspace://SpacesStore/folder-uuid"
  },

}
```

### .NET API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ocrdata` | POST | **Archive OCR results** (receives image + OCR text + engine info) |
| `/api/files/{nodeId}` | GET | Download a file from Alfresco | (legacy code)

The `.NET API` integrates with the OCR pipeline:
- Receives results from the gateway via the `/ocrdata` endpoint
- Stores original image + OCR text in Alfresco with metadata
- Allows retrieval of archived documents via CMIS browse and file download endpoints (legacy code)

---


# ═════════════════════════════════════════════════════════════════
# TROUBLESHOOTING
# ═════════════════════════════════════════════════════════════════

# Watch all pods in real-time
kubectl get pods -n ocr-lab -w

# Check why a pod is not starting
kubectl describe pod -n ocr-lab <pod-name>

# View pod logs (including previous if crashed)
kubectl logs -n ocr-lab <pod-name> --previous

# Exec into a pod for debugging
kubectl exec -it -n ocr-lab <pod-name> -- bash


# Check resource requests/limits
kubectl describe nodes

# ═════════════════════════════════════════════════════════════════
# CLEANUP & RESET
# ═════════════════════════════════════════════════════════════════

# Delete entire OCR Lab namespace
kubectl delete namespace ocr-lab

# Remove Helm releases individually
helm uninstall prometheus -n ocr-lab
helm uninstall grafana -n ocr-lab
helm uninstall loki -n ocr-lab
helm uninstall tempo -n ocr-lab
helm uninstall otel-collector -n ocr-lab

```

---

## Tear Down

```bash
# Delete Kubernetes manifests
kubectl delete -f ocr-lab/k8s/

# Uninstall Helm charts
helm uninstall prometheus grafana loki tempo otel-collector -n ocr-lab

# Delete namespace
kubectl delete namespace ocr-lab

