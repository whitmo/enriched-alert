# End-to-End Integration Test Report

**Date:** 2026-02-28
**Branch:** integration-test (PRs #2, #3, #4, #12 merged)
**Environment:** macOS Darwin 25.1.0 (Apple Silicon)

## Tool Versions

| Tool    | Version |
|---------|---------|
| podman  | 5.8.0   |
| kind    | 0.31.0  |
| kubectl | 1.27.2  |
| helm    | 4.1.1   |

## Integration Branch

All four PRs merged cleanly with no conflicts:
- PR #2 (`work/zealous-eagle`) — Infrastructure configs (Kind, Helm, Prometheus rules)
- PR #12 (`work/calm-fox`) — Podman container runtime fix
- PR #3 (`work/silly-deer`) — AI agent webhook receiver
- PR #4 (`work/cool-deer`) — Example service, exerciser, OpenSLO definitions

## Infrastructure (PR #2 + #12)

### Kind Cluster
- **Result:** PASS
- Cluster `enriched-alert` created with Kubernetes v1.35.0
- Single control-plane node, Ready

### Monitoring Stack
- **Result:** PASS
- All 5 pods Running:
  - `prometheus-kube-prometheus-operator` (1/1)
  - `prometheus-kube-state-metrics` (1/1)
  - `prometheus-prometheus-node-exporter` (1/1)
  - `alertmanager-prometheus-kube-prometheus-alertmanager-0` (2/2)
  - `prometheus-prometheus-kube-prometheus-prometheus-0` (2/2)

## AI Agent (PR #3)

- **Build:** PASS — Image built with podman (python:3.12-slim base)
- **Load into Kind:** PASS (required re-tagging — see bugs below)
- **Deploy:** PASS — Pod Running 1/1
- **Health check:** PASS — `/health` returns 200

## Example Service (PR #4)

- **Build:** PASS — Image built with podman
- **Load into Kind:** PASS (required re-tagging)
- **Deploy:** PASS — Pod Running 1/1
- **Endpoints tested:**
  - `GET /api` → `{"message":"hello","service":"example-service"}` (200)
  - `GET /health` → `{"status":"ok"}` (200)
  - `GET /metrics` → Prometheus metrics (200)
  - `GET /latency?delay_ms=2000` → `{"delay_ms":2000}` (200, 2s delay)
  - `GET /error?code=500` → `{"error":"simulated","code":500}` (500)

## Prometheus Rules

- **Recording rules:** PASS
  - `slo:example_service_latency:ratio_rate5m` — Loaded
  - `slo:example_service_error_rate:ratio_rate5m` — Loaded, computed value=1 (100% error rate on /error endpoint)
- **Alerting rules:** PASS
  - `SLOLatencyBreach` — Loaded (inactive during test — see notes)
  - `SLOErrorRateBreach` — Loaded and **FIRED**

## End-to-End Alert Flow

**Result:** PASS

Full pipeline verified:
1. Example service exposes `http_requests_total` and `http_request_duration_seconds` metrics
2. Prometheus scrapes metrics via ServiceMonitor (15s interval)
3. Recording rules compute SLO ratios over 5m window
4. `SLOErrorRateBreach` alert fires (error rate 100% >> 1% threshold)
5. Alertmanager receives alert, routes to `ai-agent` receiver (via `alerttype=slo` matcher)
6. AI agent receives webhook POST at `/alert`, returns 200
7. AI agent loads matching OpenSLO definition (`example-service-error-rate`)
8. AI agent enriches alert context with SLO metadata

### Alert Payload (received by AI agent)

```
alertname: SLOErrorRateBreach
severity: warning
alerttype: slo
slo_name: example-service-error-rate
status: firing
```

## Bugs Found and Fixed

### 1. ServiceMonitor missing `namespaceSelector`

**File:** `kubernetes/monitoring/service-monitor.yaml`
**Issue:** ServiceMonitor in `monitoring` namespace couldn't discover example-service in `default` namespace.
**Fix:** Added `namespaceSelector.matchNames: [default]`

### 2. Prometheus rule label mismatch

**File:** `kubernetes/monitoring/prometheus-rules.yaml`
**Issue:** Error rate recording rule used `status=~"5.."` but example-service metric uses `status_code` label.
**Fix:** Changed to `status_code=~"5.."`

### 3. Kind image tag mismatch (podman)

**Issue:** `kind load docker-image` with podman loaded images but didn't tag them correctly (`localhost/` prefix vs `docker.io/library/` expected by Kind). Required re-running load command which triggered re-tagging.
**Fix:** Running `kind load docker-image` a second time resolves via re-tagging.

## Notes

- `SLOLatencyBreach` remained inactive during testing. The latency endpoint returns status 200 (even with delays), so the latency recording rule `rate(bucket{le="0.5"}) / rate(count)` produces per-label results that don't aggregate across endpoints. The rule may need `sum()` aggregation to fire reliably.
- Several kube-system targets (kube-controller-manager, kube-scheduler, kube-etcd, kube-proxy) show as down — this is normal for Kind clusters.
- Grafana was intentionally disabled in helm values.
