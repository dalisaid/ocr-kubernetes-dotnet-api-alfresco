# OCR Lab — Kubernetes Multi-Engine OCR Platform

A Kubernetes-based OCR solution featuring a **microservice architecture** with:
- **FastAPI Gateway** receiving OCR requests and submitting jobs to RabbitMQ
- **RabbitMQ** for asynchronous task queuing and distribution to worker engines
- **OCR Engine Workers** (**Tesseract**, **EasyOCR**, **PaddleOCR**) consuming jobs from the queue
- **Redis** for caching, session management, and distributed state
- **.NET API** for processing OCR results and archival
- **Alfresco** for content repository and file archival
- **Integrated observability** with **Prometheus**, **Grafana**, **Loki**, and **Tempo**
- **CI/CD pipeline** with **Jenkins** + **Docker Hub** + **GitHub webhooks** via **ngrok**

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
                    │  ├─ OCR Results (ocr:text property)    │
                    │  ├─ Original Images                    │
                    │  └─ Searchable via Solr                │
                    └────────────────────────────────────────┘

    ┌──────────────────────── Observability Stack ───────────────────────────┐
    │  Prometheus (:30090) → Grafana (:30000) ← Loki + Tempo (Traces)       │
    │  Metrics: requests, errors, latency, k8s health, .NET API metrics      │
    └────────────────────────────────────────────────────────────────────────┘

    ┌──────────────────────── CI/CD Pipeline ────────────────────────────────┐
    │  git push → GitHub webhook → ngrok → Jenkins → Docker Hub → kubectl   │
    │  Automated build, push, and rolling deploy on every commit             │
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
- Uploads processed files to **Alfresco** via a REST API with metadata
- Stores OCR text as a custom `ocr:text` property on the `ocr:ocrData` aspect, making documents searchable via Solr

### Observability (Monitoring Stack)
- **Prometheus**: Scrapes metrics from gateway, engines, .NET API, and Kubernetes
- **Grafana**: Unified dashboard with request rates, error rates, latency (p50/p95/p99), engine performance, pod health, CPU/memory usage
- **Loki**: Aggregates container logs, allows filtering by component (gateway, engines, .NET API)
- **Tempo**: Distributed tracing for request flows from gateway → engines → .NET API
- **OpenTelemetry Collector**: Ingests and forwards traces

### CI/CD Pipeline
Automated pipeline triggered on every `git push` to `main`:
- **Jenkins** runs as a standalone Docker container (port 9090), outside the Kubernetes cluster
- **ngrok** exposes Jenkins to the internet so GitHub webhooks can reach it
- Pipeline stages: **Build** (docker build) → **Push** (docker push to Docker Hub) → **Deploy** (kubectl apply + rolling restart)
- Only custom-built images are managed by the pipeline (gateway, tesseract). Infrastructure components (RabbitMQ, Redis, monitoring) are excluded.

---

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| Docker Desktop | latest (kind provisioner) |
| kubectl | matching your cluster |
| Helm | 3.x |
| ngrok | 3.x |

> **Note:** This project runs on Docker Desktop with the **kind** provisioner (v1.36.1). kind does not expose NodePort services to the host — use `kubectl port-forward` instead. See `start-ports.ps1`.

---

## Project Structure

```
Projet-PFE-Master/
├── Jenkinsfile                    # CI/CD pipeline definition
├── setup-jenkins.ps1              # Restore Jenkins Docker CLI + kubectl after container recreate
├── start-ports.ps1                # Start all port-forwards for local access
├── cluster-setup-guide.txt        # Full cluster setup and troubleshooting guide
├── ocr-lab/
│   ├── k8s/
│   │   ├── namespace.yaml          # ocr-lab namespace
│   │   ├── gateway.yaml            # Gateway Deployment + NodePort Service
│   │   ├── engine-tesseract.yaml   # Tesseract Deployment + ClusterIP Service
│   │   ├── engine-easyocr.yaml     # EasyOCR Deployment + ClusterIP Service
│   │   ├── engine-paddle.yaml      # PaddleOCR Deployment + ClusterIP Service
│   │   ├── rabbitmq.yaml           # RabbitMQ StatefulSet + Service
│   │   └── helm/
│   │       └── redis-values.yaml   # Redis Helm chart values
│   ├── gateway/
│   │   ├── main.py                 # FastAPI router with RabbitMQ integration
│   │   └── Dockerfile
│   ├── engines/
│   │   ├── tesseract/
│   │   │   ├── main.py
│   │   │   └── Dockerfile
│   │   ├── easyocr/
│   │   │   ├── main.py
│   │   │   └── Dockerfile
│   │   └── paddle/
│   │       ├── main.py
│   │       └── Dockerfile
│   └── monitoring/
│       ├── prometheus-values.yaml
│       ├── grafana-values.yaml
│       ├── loki-values.yaml
│       ├── tempo-values.yaml
│       ├── otel-values.yaml
│       ├── dashboard.yaml          # Grafana dashboard ConfigMap
│       └── rbac.yaml
├── dotnet-api/                    # .NET API (runs outside Kubernetes on localhost:5122)
└── alfresco-extension/            # Alfresco custom content model and Share config
```

---

## Quick Start

### Build images

```bash
docker build -t dalisaid/ocr-gateway:latest ./ocr-lab/gateway
docker build -t dalisaid/ocr-tesseract:latest ./ocr-lab/engines/tesseract
# docker build -t dalisaid/ocr-easyocr:latest ./ocr-lab/engines/easyocr    # optional (heavy)
# docker build -t dalisaid/ocr-paddle:latest ./ocr-lab/engines/paddle       # optional (heavy)
```

### Deploy core services

```bash
# Namespace first
kubectl apply -f ocr-lab/k8s/namespace.yaml

# Install ServiceMonitor CRD (required by Redis)
kubectl apply -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/example/prometheus-operator-crd/monitoring.coreos.com_servicemonitors.yaml

# RabbitMQ first (engines depend on it)
kubectl apply -f ocr-lab/k8s/rabbitmq.yaml -n ocr-lab

# Then the rest
kubectl apply -f ocr-lab/k8s/gateway.yaml -n ocr-lab
kubectl apply -f ocr-lab/k8s/engine-tesseract.yaml -n ocr-lab

# Redis via Helm
helm install redis bitnami/redis -n ocr-lab -f ocr-lab/k8s/helm/redis-values.yaml
```

### Deploy monitoring stack

```bash
helm install prometheus prometheus-community/prometheus -n ocr-lab -f ocr-lab/monitoring/prometheus-values.yaml
helm install loki grafana/loki-stack -n ocr-lab -f ocr-lab/monitoring/loki-values.yaml
helm install tempo grafana/tempo -n ocr-lab -f ocr-lab/monitoring/tempo-values.yaml
helm install otel-collector open-telemetry/opentelemetry-collector -n ocr-lab -f ocr-lab/monitoring/otel-values.yaml
helm install grafana grafana/grafana -n ocr-lab -f ocr-lab/monitoring/grafana-values.yaml

# Apply dashboards and RBAC (one time only)
kubectl apply -f ocr-lab/monitoring/dashboard.yaml -n ocr-lab
kubectl apply -f ocr-lab/monitoring/rbac.yaml -n ocr-lab
```

### Start port-forwards (every session)

```powershell
.\start-ports.ps1
```

| Service     | URL                          | Credentials  |
|-------------|------------------------------|--------------|
| Gateway API | http://localhost:30010/docs  | —            |
| Grafana     | http://localhost:30000       | admin / admin|
| Prometheus  | http://localhost:30090       | —            |
| RabbitMQ UI | http://localhost:15672       | guest / guest|

---

## CI/CD Pipeline

The pipeline is defined in `Jenkinsfile` at the project root and runs automatically on every push to `main`.

### Setup (one time)

```powershell
# Start Jenkins container
docker run -d `
  --name jenkins `
  -p 9090:8080 `
  -p 50000:50000 `
  -v jenkins_home:/var/jenkins_home `
  -v //var/run/docker.sock:/var/run/docker.sock `
  jenkins/jenkins:lts

# Configure Docker CLI + kubectl inside Jenkins
.\setup-jenkins.ps1

# Start ngrok tunnel
ngrok http 9090
```

Set the ngrok URL as the GitHub webhook payload URL:
```
https://<ngrok-url>/github-webhook/
```

### Pipeline stages

| Stage | What it does |
|-------|-------------|
| Build Images | `docker build` for gateway and tesseract |
| Push Images | `docker push` to Docker Hub (`dalisaid/`) |
| Deploy to Kubernetes | `kubectl apply` + `kubectl rollout restart` + waits for rollout |

> **Note:** The ngrok URL changes on every restart (free plan). Update the GitHub webhook when this happens.

---

## End-to-End OCR + Storage Workflow

### Step 1: Send an OCR Request to the Gateway

```bash
# Example with Tesseract
curl -s -X POST http://localhost:30010/ocr \
  -F "engine=tesseract" \
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
curl -s -X POST http://localhost:5122/ocrdata \
  -F "file=@/path/to/your/image.png" \
  -F "ocrText=Hello, World!" \
  -F "ocrEngine=tesseract"
```

The .NET API will:
1. Upload the image to Alfresco with OCR text stored as `ocr:text` metadata
2. Return the Alfresco node ID

### Step 3: Search in Alfresco

Once archived, documents are searchable in Alfresco Share via explicit field search:
```
ocr:text:"your search term"
```

---

## .NET API Configuration

```json
{
  "Alfresco": {
    "BaseUrl": "http://alfresco-server:8080",
    "Username": "admin",
    "Password": "admin",
    "FolderNodeId": "workspace://SpacesStore/folder-uuid"
  }
}
```

### .NET API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ocrdata` | POST | Archive OCR results (image + OCR text + engine info) |
| `/api/files/{nodeId}` | GET | Download a file from Alfresco (legacy) |

---

## Observability

Login to Grafana at `http://localhost:30000` with **admin/admin** and navigate to the **"OCR Observability Platform"** dashboard. It includes:

- **Request Overview**: Total requests, errors, error rate, p95 OCR latency, p95 .NET latency, gateway status
- **Request Throughput**: Request rate by engine, success vs error rate
- **Processing Latency**: p50/p95/p99 latency for each OCR engine and .NET API
- **Error Tracking**: Error counts by engine, error rate percentage
- **Kubernetes Health**: Running pods, failed pods, pod restarts, CPU/memory usage
- **Distributed Traces**: Recent gateway traces from Tempo, correlated with logs
- **Logs**: Success logs, error logs, .NET API upload activity via Loki

<img width="1542" height="799" alt="image" src="https://github.com/user-attachments/assets/33710102-443b-45bc-a4c4-0311495ea28f" />

Link: https://snapshots.raintank.io/dashboard/snapshot/NyUAzLPmHNzlqi3715z45vPKE9hvhgkI?orgId=0&from=2026-05-30T19:04:21.969Z&to=2026-05-30T19:34:21.969Z&timezone=browser&refresh=10s

---

## Ports Reference

| Service          | Internal port | Access (port-forward) | Purpose |
|------------------|---------------|-----------------------|---------|
| Gateway          | 8000          | localhost:30010       | OCR request ingestion |
| Engine Tesseract | 8001          | —                     | OCR processing (ClusterIP only) |
| Engine EasyOCR   | 8002          | —                     | OCR processing (ClusterIP only) |
| Engine PaddleOCR | 8003          | —                     | OCR processing (ClusterIP only) |
| RabbitMQ         | 5672          | localhost:15672 (UI)  | AMQP message queue |
| Redis            | 6379          | —                     | Cache & distributed state |
| Prometheus       | 80            | localhost:30090       | Metrics |
| Grafana          | 80            | localhost:30000       | Dashboards |

> Engine, RabbitMQ, and Redis services are `ClusterIP` — only reachable from inside the cluster.

---

## Troubleshooting

```bash
# Watch all pods in real-time
kubectl get pods -n ocr-lab -w

# Check why a pod is not starting
kubectl describe pod -n ocr-lab <pod-name>

# View pod logs
kubectl logs -n ocr-lab <pod-name> -f

# View previous logs (if crashed)
kubectl logs -n ocr-lab <pod-name> --previous

# Exec into a pod for debugging
kubectl exec -it -n ocr-lab <pod-name> -- bash
```

For full troubleshooting, common issues and fixes, see `cluster-setup-guide.txt`.

---

## Tear Down

```bash
# Delete namespace (removes all pods, services, configmaps)
kubectl delete namespace ocr-lab

# Uninstall Helm releases
helm uninstall prometheus grafana loki tempo otel-collector redis -n ocr-lab

# Stop Jenkins
docker stop jenkins

# Stop ngrok (Ctrl+C in the ngrok terminal)
```
