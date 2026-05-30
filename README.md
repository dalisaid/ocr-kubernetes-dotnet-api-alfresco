# OCR Lab — Kubernetes Multi-Engine OCR Platform

A Kubernetes-based OCR solution featuring a **microservice architecture** with:
- **FastAPI Gateway** receiving OCR requests and submitting jobs to RabbitMQ
- **RabbitMQ** for asynchronous task queuing and distribution to worker engines
- **OCR Engine Workers** (**Tesseract**, **EasyOCR**, **PaddleOCR**) consuming jobs from the queue
- **Redis** for caching, session management, and distributed state
- **.NET API** for processing OCR results and archival
- **Alfresco** for content repository and file archival
- **Integrated observability** with **Prometheus**, **Grafana**, **Loki**, and **Tempo**

```
                    ┌──────────────────────────────────────────────────────────────┐
                    │              ocr-lab namespace (Kubernetes)                   │
                    │                                                               │
  POST /ocr         │  ┌─────────────┐                                              │
  + image + engine  ├─►│  Gateway    │                                              │
                    │  │  :8000      │                                              │
                    │  └──────┬──────┘                                              │
                    │         │ (Job Submission)                                    │
                    │  ┌──────▼──────────────┐                                      │
                    │  │    RabbitMQ        │ (Job Queue)                           │
                    │  │    :5672           │                                       │
                    │  └──────┬─────────────┘                                       │
                    │         │ (Job Distribution)                                 │
                    │         │                                                    │
                    │  ┌──────▼────────────────────────────────────────┐            │
                    │  │  OCR Engine Workers (Consumers)              │            │
                    │  │  ├─ Tesseract   (:8001)                      │            │
                    │  │  ├─ EasyOCR     (:8002)                      │            │
                    │  │  └─ PaddleOCR   (:8003)                      │            │
                    │  └──────────────────────────────────────────────┘            │
                    │                                                               │
                    │  ┌──────────────┐                                             │
                    │  │    Redis     │ (Cache/State)                              │
                    │  │    :6379     │                                             │
                    │  └──────────────┘                                             │
                    │                                                               │
                    └───────────────────────────────────────────────────────────────┘
                            │
                    ┌───────▼─────────────────────────────────┐
                    │  .NET API (dotnet-api)                 │
                    │  POST /ocrdata                         │
                    │  (Receives OCR text + metadata)        │
                    │                                        │
                    │  └─ Alfresco: File & metadata archive  │
                    └───────┬─────────────────────────────────┘
                            │
                    ┌───────▼─────────────────────────────────┐
                    │  Alfresco (Content Repository)         │
                    │  ├─ OCR Results                        │
                    │  ├─ Original Images                    │
                    │  └─ CMIS Access                        │
                    └────────────────────────────────────────┘

    ┌──────────────────────── Observability Stack ───────────────────────────┐
    │  Prometheus (:30090) → Grafana (:30000) ← Loki + Tempo (Traces)       │
    │  Metrics: requests, errors, latency, k8s health, .NET API metrics      │
    └────────────────────────────────────────────────────────────────────────┘
```

---

## Architecture Overview

### Microservice Components

#### OCR Gateway (Kubernetes)
FastAPI gateway receives `/ocr` POST requests and submits OCR jobs to RabbitMQ instead of routing directly to engines. This decoupling enables:
- Asynchronous job processing and resilience
- Load balancing across multiple engine workers
- Job persistence and retry mechanisms

#### RabbitMQ (Message Queue)
- **Async Job Processing**: Decouples OCR requests from immediate processing
- **Job Queue Management**: Manages OCR tasks, engine load balancing, and retry logic
- **Service Communication**: Enables asynchronous communication between microservices

#### Redis (Caching & State)
- **Request Caching**: Caches OCR results to avoid redundant processing
- **Session Management**: Stores gateway session state and distributed cache
- **Performance Optimization**: Reduces latency for repeated OCR requests on same content

### .NET API Integration
The **dotnet-api** receives OCR results via the `/ocrdata` endpoint. It:
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
│   ├── engine-paddle.yaml      # PaddleOCR Deployment + ClusterIP Service
│   ├── rabbitmq.yaml           # RabbitMQ Deployment + Service (async job queue)
│   └── helm/
│       └── redis-values.yaml   # Redis Helm chart values (caching & state)
├── gateway/
│   ├── main.py                 # FastAPI router with RabbitMQ integration
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
# Apply in order — namespace first, then storage, then message queue, cache, then workloads
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/rabbitmq.yaml
kubectl apply -f k8s/gateway.yaml
kubectl apply -f k8s/engine-tesseract.yaml
kubectl apply -f k8s/engine-easyocr.yaml
kubectl apply -f k8s/engine-paddle.yaml
```

### · Deploy Redis (via Helm)

```bash
# Add Helm repository if not already added
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Deploy Redis for caching and distributed state
helm install redis bitnami/redis \
  -n ocr-lab -f ocr-lab/k8s/helm/redis-values.yaml
```

---

### · Wait for all pods to become Ready

```bash
kubectl get pods -n ocr-lab -w
```

Expected output (EasyOCR/Paddle take longer on first start due to model downloads):

```
NAME                                READY   STATUS    RESTARTS   AGE
rabbitmq-0                          1/1     Running   0          15s
redis-master-0                      1/1     Running   0          15s
redis-replica-0                     1/1     Running   0          15s
gateway-7d9f6b-xxxx                 1/1     Running   0          30s
engine-tesseract-5c8b4d-xxxx        1/1     Running   0          30s
engine-easyocr-6f7a2c-xxxx          0/1     Running   0          45s   ← startup probe running
engine-paddle-8e3d1b-xxxx           0/1     Running   0          45s   ← startup probe running
```

Once all show `1/1 Running`, RabbitMQ, Redis, and OCR services are ready.

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

Snapshot:

<img width="1542" height="799" alt="image" src="https://github.com/user-attachments/assets/33710102-443b-45bc-a4c4-0311495ea28f" />

Link:https://snapshots.raintank.io/dashboard/snapshot/NyUAzLPmHNzlqi3715z45vPKE9hvhgkI?orgId=0&from=2026-05-30T19:04:21.969Z&to=2026-05-30T19:34:21.969Z&timezone=browser&refresh=10s



## Ports Reference

| Service          | Internal port | NodePort | Purpose |
|------------------|---------------|----------|---------|
| Gateway          | 8000          | 30080    | OCR request ingestion |
| Engine Tesseract | 8001          | —        | OCR processing (ClusterIP only) |
| Engine EasyOCR   | 8002          | —        | OCR processing (ClusterIP only) |
| Engine PaddleOCR | 8003          | —        | OCR processing (ClusterIP only) |
| RabbitMQ         | 5672          | —        | AMQP message queue (ClusterIP only) |
| Redis            | 6379          | —        | Cache & distributed state (ClusterIP only) |

Engine, RabbitMQ, and Redis services are `ClusterIP` — they are only reachable from inside the cluster.

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
helm uninstall redis -n ocr-lab

```

---

## Tear Down

```bash
# Delete Kubernetes manifests
kubectl delete -f ocr-lab/k8s/

# Uninstall Helm charts
helm uninstall prometheus grafana loki tempo otel-collector redis -n ocr-lab

# Delete namespace
kubectl delete namespace ocr-lab

