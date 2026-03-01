# OpenSLO Spec Completeness & Observability Architecture Review

**Date:** 2026-03-01
**Reviewer:** lively-platypus (automated, Gemini-assisted)
**Scope:** OpenSLO YAML definitions, Prometheus metric alignment, alert routing, end-to-end observability gaps, AI agent enrichment value

---

## Summary

| Severity   | Count |
|------------|-------|
| CRITICAL   |   5   |
| WARNING    |   6   |
| SUGGESTION |   5   |

---

## 1. OpenSLO Spec Compliance

### CRITICAL-1: Error rate recording rule inverts good/error semantics

**Files:** `kubernetes/monitoring/prometheus-rules.yaml:12-15`, `openslo/example-service-error-rate.yaml:13-21`

The OpenSLO definition defines `good` as `sum(rate(http_requests_total{status_code!~"5.."}[5m]))` (success rate). The Prometheus recording rule `slo:example_service_error_rate:ratio_rate5m` computes the inverse — error rate: `rate(http_requests_total{status_code=~"5.."}[5m]) / rate(http_requests_total[5m])`.

While the alerting threshold `> 0.01` compensates for the inversion, the recording rule name contains "error_rate" but doesn't match what OpenSLO defines as the SLO metric. This divergence between spec and implementation creates confusion and makes the recording rule not directly comparable to the SLO `target: 0.99`.

### CRITICAL-2: Missing `sum()` aggregation in recording rules

**Files:** `kubernetes/monitoring/prometheus-rules.yaml:8-15`

Both recording rules use bare `rate(...)` without `sum()`, while the OpenSLO definitions specify `sum(rate(...))`. With multiple service replicas (or even multiple label dimensions from method/endpoint/status_code), each label combination produces a separate time series. The ratio is computed per-series, not globally, so the SLO cannot be evaluated correctly across replicas.

- Latency rule (line 9): `rate(http_request_duration_seconds_bucket{le="0.5"}[5m])` — needs `sum()`
- Error rate rule (line 13): `rate(http_requests_total{status_code=~"5.."}[5m])` — needs `sum()`

### WARNING-1: Error rate SLO has no alertPolicy defined

**File:** `openslo/example-service-error-rate.yaml`

The error rate SLO definition has no `alertPolicies` section, unlike the latency SLO. While a corresponding Prometheus alert rule exists (`SLOErrorRateBreach`), the OpenSLO definition is incomplete — anyone reading the spec alone would not know this SLO is alertable.

### WARNING-2: 5-minute rolling window is extremely short for production SLOs

**Files:** `openslo/example-service-latency.yaml:27`, `openslo/example-service-error-rate.yaml:23`

Both SLOs use `duration: 5m` rolling windows. This is fine for a demo/PoC but would cause excessive alert flapping in production. Typical SLO windows are 30d rolling or calendar-month. The short window also means the burn rate alert condition (`lookbackWindow: 5m` in the latency alert policy) is essentially redundant with the raw SLO evaluation.

### SUGGESTION-1: Missing `Service` object reference in OpenSLO

**Files:** `openslo/example-service-latency.yaml:7`, `openslo/example-service-error-rate.yaml:7`

Both SLOs reference `service: example-service` as a plain string. The OpenSLO spec supports defining `Service` as a standalone object. For a small PoC this is fine, but a separate `Service` kind would be more spec-complete.

### SUGGESTION-2: Missing `op` field on objectives

**Files:** `openslo/example-service-latency.yaml:11`, `openslo/example-service-error-rate.yaml:11`

The `op` field (e.g., `gte`) is absent from objectives. While implied by the target + ratioMetrics combination, making it explicit improves readability.

### SUGGESTION-3: No `metadata.labels` on SLO objects

Both SLO definitions lack `metadata.labels`. Adding labels like `team`, `tier`, or `environment` would improve filtering and management at scale.

---

## 2. Prometheus Metric Alignment

### Metric name alignment: PASS

The app (`example-service/app.py:17-28`) exports:
- `http_request_duration_seconds` (Histogram) with buckets including `0.5`
- `http_requests_total` (Counter)
- Labels: `method`, `endpoint`, `status_code`

The OpenSLO queries and Prometheus rules correctly reference these metric names and the `le="0.5"` bucket.

### Histogram bucket alignment: PASS

The app's bucket list `(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)` includes the `0.5` boundary used by the latency SLO. The SLO threshold aligns with a real bucket boundary.

### Alerting threshold alignment: PASS (with caveat)

- Latency alert: `slo:...:ratio_rate5m < 0.99` matches target `0.99`
- Error rate alert: `slo:...:ratio_rate5m > 0.01` correctly compensates for the inverted recording rule (see CRITICAL-1)

---

## 3. Alert Routing Logic

### CRITICAL-3: Two conflicting Alertmanager configurations

**Files:** `kubernetes/monitoring/helm-values.yaml:7-18`, `kubernetes/helm-values/alertmanager-values.yaml.tpl:4-16`

Two separate Alertmanager configs exist with different behaviors:

| Aspect | helm-values.yaml | alertmanager-values.yaml.tpl |
|--------|-------------------|------------------------------|
| Receiver name | `ai-agent` | `ai-agent-webhook` |
| URL | `http://ai-agent.default.svc.cluster.local/alert` | `http://ai-agent.DEPLOY_NAMESPACE.svc.cluster.local:8080/alert` |
| Port | 80 (implicit) | 8080 (explicit) |
| Route | `alerttype = slo` matcher on sub-route | Root route (catches all) |
| Grouping | Default | `group_by: ['alertname', 'slo_name']` |
| Default receiver | `default` (null) | None |

The template version sends to port 8080 directly, but the ai-agent Kubernetes Service (`ai-agent/kubernetes/service.yaml`) maps port 80 → 8080. If the template is used, Alertmanager would bypass the Service and hit the pod port directly, which only works if the URL resolves to a pod IP (it won't via DNS).

Which config takes precedence depends on deployment order (Makefile `monitoring-up` uses the template if it exists, falling back to nothing).

### WARNING-3: alertmanager-values.yaml.tpl routes ALL alerts to ai-agent

**File:** `kubernetes/helm-values/alertmanager-values.yaml.tpl:6`

The template config makes `ai-agent-webhook` the root receiver with no sub-routes. This means every Prometheus alert (including kube-prometheus-stack's built-in alerts for node health, kubelet, etc.) would be sent to the ai-agent, not just SLO alerts.

### WARNING-4: No `alerttype` label filtering in template config

**File:** `kubernetes/helm-values/alertmanager-values.yaml.tpl`

Unlike `helm-values.yaml` which filters on `alerttype = slo`, the template has no matchers. The ai-agent only knows how to handle alerts with `slo_name` labels — all other alerts would produce `"enriched": false, "reason": "no slo_name label found"` responses.

---

## 4. End-to-End Observability Gaps

### CRITICAL-4: Makefile deploy targets reference non-existent paths

**File:** `Makefile:119-141`

The Makefile targets reference paths that don't exist:
- `agent-deploy` references `./kubernetes/agent-deployment.yaml` — actual file is `./ai-agent/kubernetes/deployment.yaml`
- `service-deploy` references `./kubernetes/service-deployment.yaml` — actual file is `./example-service/kubernetes/deployment.yaml`
- `openslo-deploy` references `./kubernetes/openslo/` — directory doesn't exist
- `rules-deploy` references `./kubernetes/rules/` — directory doesn't exist; actual rules are in `./kubernetes/monitoring/prometheus-rules.yaml`

The `openslo-deploy` and `rules-deploy` targets silently skip with informational messages, meaning PrometheusRules and OpenSLO ConfigMaps are never deployed via `make deploy`.

### WARNING-5: No observability on the ai-agent itself

**Files:** `ai-agent/app.py`, `kubernetes/monitoring/service-monitor.yaml`

The ai-agent exposes no `/metrics` endpoint and has no Prometheus instrumentation. The ServiceMonitor only scrapes `example-service`. If the ai-agent fails, crashes, or falls behind on alert processing, there is no automated detection. Key missing metrics:
- Alert processing latency
- Alert receive count (by slo_name, by enrichment success/failure)
- OpenSLO definition load errors

### WARNING-6: Grafana disabled, no dashboards

**File:** `kubernetes/monitoring/helm-values.yaml:1-2`

`grafana: enabled: false` means there are no dashboards for SLO burn rate visualization, alert history, or error budget remaining. The only observability surface is Prometheus queries and ai-agent logs.

### SUGGESTION-4: No readiness probe on ai-agent

**File:** `ai-agent/kubernetes/deployment.yaml`

The ai-agent deployment has a `livenessProbe` but no `readinessProbe`. If it starts but isn't ready to accept alerts (e.g., OpenSLO ConfigMap not yet mounted), Alertmanager requests could fail.

---

## 5. AI Agent Enrichment: Value Assessment

### CRITICAL-5: Enrichment is read-only logging with no downstream action

**File:** `ai-agent/app.py:63-74`

The ai-agent's entire enrichment pipeline is:
1. Receive Alertmanager webhook
2. Extract `slo_name` from labels
3. Load OpenSLO YAML from local filesystem
4. Log the definition
5. Return JSON response (to Alertmanager, which ignores it)

There is no:
- Notification to external systems (Slack, PagerDuty, etc.)
- Automated remediation or runbook execution
- Ticket/incident creation
- Error budget tracking or state persistence
- AI/LLM analysis of the SLO context (despite the name "ai-agent")

The enrichment adds the full SLO YAML to the log line, which provides slightly more context than the raw alert's `slo_name` label alone. However, the same information is available by looking up the SLO file directly. The marginal value is low without a downstream consumer of the enriched data.

### SUGGESTION-5: Enrichment could add computed context not available in raw alerts

The ai-agent could add genuine value by computing derived information:
- Current error budget remaining (query Prometheus for burn rate)
- Historical breach frequency
- Correlated alerts (other SLOs breaching simultaneously)
- Recommended runbook links based on SLO type

Without these, the enrichment is a pass-through of static YAML that could be achieved with a simple Alertmanager template annotation.

---

## Appendix: File Cross-Reference

| Component | File | Status |
|-----------|------|--------|
| Latency SLO | `openslo/example-service-latency.yaml` | Spec-valid, minor omissions |
| Error Rate SLO | `openslo/example-service-error-rate.yaml` | Missing alertPolicy |
| Recording Rules | `kubernetes/monitoring/prometheus-rules.yaml` | Missing sum(), inverted semantics |
| Alert Routing (static) | `kubernetes/monitoring/helm-values.yaml` | Correct but conflicts with template |
| Alert Routing (template) | `kubernetes/helm-values/alertmanager-values.yaml.tpl` | Port mismatch, overly broad |
| AI Agent | `ai-agent/app.py` | Functional but limited value |
| Service Monitor | `kubernetes/monitoring/service-monitor.yaml` | Only scrapes example-service |
| Makefile | `Makefile` | Deploy targets reference wrong paths |
