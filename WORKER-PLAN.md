# Multi-Worker Implementation Plan

AI-driven SLO anomaly detection and response PoC.

```
data => detection boundary => agent => response
```

## Architecture Overview

```
┌─────────────┐    ┌─────────────┐    ┌──────────────┐    ┌───────────┐
│  Example     │    │ Prometheus  │    │ Alertmanager │    │ AI Agent  │
│  Service     │───>│ (scrape +   │───>│ (route       │───>│ (webhook  │
│  + Exerciser │    │  SLO rules) │    │  alerts)     │    │  receiver)│
└─────────────┘    └─────────────┘    └──────────────┘    └───────────┘
      TASK-4            TASK-2             TASK-2             TASK-3
```

## Dependency Graph

```
TASK-1 (Kind/Podman cluster)
  ├── TASK-2 (Monitoring: Prometheus + Alertmanager)  [needs cluster]
  │     └── TASK-3 (AI Agent webhook)                 [needs alertmanager]
  └── TASK-4 (Example service + SLOs + exerciser)     [needs cluster + prometheus]
```

## Worker Assignments

### Worker 1: Infrastructure (TASK-1 + TASK-2)

**Scope**: Local K8s cluster + monitoring stack

**Deliverables**:
1. `kind-config.yaml` — Kind cluster configuration
2. Helm values override for kube-prometheus-stack (slim for PoC)
3. Alertmanager config with webhook receiver pointing to the agent service
4. Makefile targets verified working (`kind-up`, `kind-down`, `monitoring-up`)

**Acceptance test**: `kubectl get pods -n monitoring` shows Prometheus + Alertmanager running.

**Key decisions**:
- Use kube-prometheus-stack Helm chart (not manual manifests)
- Alertmanager webhook receiver URL: `http://ai-agent.default.svc.cluster.local:8080/alert`
- Single-node Kind cluster (sufficient for PoC)

---

### Worker 2: Example Service + OpenSLO (TASK-4)

**Scope**: Targetable service, SLO definitions, exerciser script

**Deliverables**:
1. `example-service/` — Python FastAPI app with:
   - `/health` endpoint (200 OK)
   - `/api` endpoint with configurable latency (`?delay_ms=N`) and error rate (`?error_rate=0.5`)
   - Prometheus metrics: `http_request_duration_seconds` histogram, `http_requests_total` counter by status
   - `Dockerfile`
2. `openslo/` — OpenSLO YAML definitions:
   - `latency-slo.yaml` — p99 latency < 500ms over 5min window
   - `error-rate-slo.yaml` — error rate < 1% over 5min window
3. `prometheus-rules/` — Generated PrometheusRule CRDs from OpenSLO defs
   - Recording rules for SLI calculation
   - Alerting rules with `slo_name` label
4. `exerciser/` — Python script to drive traffic:
   - Normal mode (healthy requests)
   - Latency breach mode
   - Error breach mode
5. `kubernetes/service-deployment.yaml` — K8s manifests for the example service

**Acceptance test**: Exerciser triggers SLO breach → Prometheus fires alert → Alertmanager routes it.

**Key decisions**:
- Python + FastAPI for the service (matches agent stack, keeps PoC simple)
- OpenSLO → Prometheus rules: generate manually for PoC (avoid dependency on openslo CLI tooling)
- Short SLO windows (5min) so breaches fire quickly during demo

---

### Worker 3: AI Agent Webhook (TASK-3)

**Scope**: Alert-receiving agent that enriches with SLO context

**Deliverables**:
1. `ai-agent/` — Python FastAPI app with:
   - `POST /alert` — receives Alertmanager webhook payload
   - Alert parser: extracts `slo_name` from `commonLabels`
   - OpenSLO loader: reads matching YAML from mounted ConfigMap
   - Structured logging: alert + SLO definition context
   - `GET /health` — liveness probe
   - `Dockerfile`
2. `kubernetes/agent-deployment.yaml` — K8s Deployment + Service + ConfigMap mount
3. `openslo/` ConfigMap generation in Makefile

**Acceptance test**: Send mock Alertmanager JSON to `/alert` → agent logs enriched context with SLO definition.

**Key decisions**:
- FastAPI (async, lightweight, good logging)
- OpenSLO defs mounted via ConfigMap (not baked into image — easy to update)
- Structured JSON logging for easy inspection

---

## Execution Order

```
Phase 1 (parallel):
  Worker 1: TASK-1 (Kind cluster) + TASK-2 (monitoring)
  Worker 2: TASK-4 code only (service, SLOs, exerciser — no cluster needed to write)
  Worker 3: TASK-3 code only (agent app — no cluster needed to write)

Phase 2 (sequential, after Phase 1):
  Worker 2: Deploy example service, load rules into Prometheus
  Worker 3: Deploy agent, configure Alertmanager webhook

Phase 3 (integration):
  Any worker: Run exerciser → verify full pipeline fires
```

Phase 1 is fully parallel — all 3 workers write code independently.
Phase 2 needs the cluster from Worker 1.
Phase 3 is the integration smoke test.

## Shared Conventions

- **Language**: Python 3.12+ everywhere
- **Framework**: FastAPI for both services
- **Container**: Podman builds, Kind loads
- **Namespace**: monitoring services in `monitoring`, app services in `default`
- **Makefile**: All operations have make targets
- **Testing**: Each worker writes a local test (curl/pytest) before k8s deploy

## Risk / Notes

- Kind + Podman can have networking quirks — Worker 1 should verify pod-to-pod communication works before handing off
- kube-prometheus-stack is heavy — may need resource limits on Kind node or `--set` overrides to slim it down
- OpenSLO tooling maturity is uneven — generating Prometheus rules manually is safer for the PoC
- Exerciser timing matters: SLO windows need to be short enough that breaches fire within a demo timeframe
