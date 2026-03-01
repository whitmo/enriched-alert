# Pipeline Contract Correctness Review

Functional review of cross-component contracts in the enriched-alert pipeline.
Analyzed with Gemini CLI + manual review on 2026-03-01.

## Summary

| Group | Components | Verdict |
|-------|-----------|---------|
| 1. Label Selectors | example-service/app.py, ServiceMonitor, Service, Deployment | PASS |
| 2. Metrics & Thresholds | prometheus-rules.yaml, openslo/*.yaml | 3 ISSUES |
| 3. Webhook URL | helm-values.yaml, ai-agent Service/Deployment | PASS |
| 4. Alert Payload | ai-agent/app.py, prometheus-rules, openslo definitions | PASS |

**3 contract issues found, 0 blocking for PoC.**

---

## Group 1: Label Selectors (PASS)

**Files**: `example-service/app.py`, `kubernetes/monitoring/service-monitor.yaml`, `example-service/kubernetes/deployment.yaml`, `example-service/kubernetes/service.yaml`

No mismatches found:
- ServiceMonitor `selector.matchLabels: app: example-service` matches Service label `app: example-service`
- ServiceMonitor `endpoints[0].port: http` matches Service port name `http`
- ServiceMonitor `namespaceSelector.matchNames: [default]` matches where Service is deployed (no namespace = default)
- Metrics path `/metrics` consistent across app.py, Deployment annotations, and ServiceMonitor

---

## Group 2: Metrics & Thresholds (3 ISSUES)

**Files**: `kubernetes/monitoring/prometheus-rules.yaml`, `openslo/example-service-latency.yaml`, `openslo/example-service-error-rate.yaml`

### ISSUE 1: Missing `sum()` aggregation in Prometheus recording rules

**Prometheus rules** (`prometheus-rules.yaml:12-15`):
```promql
rate(http_request_duration_seconds_bucket{le="0.5"}[5m])
/
rate(http_request_duration_seconds_count[5m])
```

**OpenSLO latency definition** (`example-service-latency.yaml:19,24`):
```promql
sum(rate(http_request_duration_seconds_bucket{le="0.5"}[5m]))
sum(rate(http_request_duration_seconds_count[5m]))
```

**Mismatch**: Prometheus rules omit `sum()`. With multiple label dimensions (method, endpoint, status_code), the rule produces multiple ratio series instead of a single aggregated value. The OpenSLO definitions explicitly use `sum()`.

**Same issue** in the error rate recording rule (`prometheus-rules.yaml:17-20` vs `example-service-error-rate.yaml:19,24`).

**Impact**: In practice, with the PoC's single endpoint pattern, this may not cause visible breakage, but it deviates from the OpenSLO contract and would break with multiple endpoints.

### ISSUE 2: Semantic inversion in error rate calculation

**Prometheus rule** (`prometheus-rules.yaml:17-20`):
```promql
rate(http_requests_total{status_code=~"5.."}[5m])
/
rate(http_requests_total[5m])
```
This computes **error rate** (bad / total).

**OpenSLO definition** (`example-service-error-rate.yaml:18-19`):
```promql
sum(rate(http_requests_total{status_code!~"5.."}[5m]))
```
This defines the **good** metric (`status_code!~"5.."`), meaning the ratio is **success rate** (good / total).

**Mismatch**: The Prometheus rule calculates error rate (0.01 = 1% errors) while OpenSLO defines a success rate ratio (0.99 = 99% success). The alert threshold `> 0.01` is correct for the Prometheus rule, but semantically inverted from the OpenSLO target of `0.99`.

**Impact**: The alerting works correctly in practice (both fire at the same point), but the recorded metric `slo:example_service_error_rate:ratio_rate5m` is actually an error rate, not the "good/total" ratio the OpenSLO spec defines. Any downstream consumer expecting the OpenSLO-defined ratio would get inverted values.

### ISSUE 3: Missing alertPolicies in error rate OpenSLO definition

**Latency OpenSLO** (`example-service-latency.yaml:29-48`): Has a full `alertPolicies` section with burn rate condition.

**Error rate OpenSLO** (`example-service-error-rate.yaml`): **No `alertPolicies` section at all.**

**Impact**: The Prometheus alert `SLOErrorRateBreach` exists and works, but the OpenSLO definition is incomplete — it doesn't specify how the SLO should be alerted on. This is an incomplete spec, not a runtime issue.

### Alignments confirmed:
- `slo_name` labels match: `example-service-latency` and `example-service-error-rate` match OpenSLO `metadata.name` fields
- Threshold equivalence: 0.99 latency target and 0.01 error rate threshold are numerically aligned
- Metric names `http_request_duration_seconds` and `http_requests_total` match across all files
- Bucket boundary `le="0.5"` (500ms) is consistent

---

## Group 3: Webhook URL (PASS)

**Files**: `kubernetes/monitoring/helm-values.yaml`, `ai-agent/kubernetes/service.yaml`, `ai-agent/kubernetes/deployment.yaml`

No mismatches found:
- Alertmanager webhook URL: `http://ai-agent.default.svc.cluster.local/alert`
- ai-agent Service: `name: ai-agent`, `port: 80`, `targetPort: 8080`
- ai-agent Deployment: `containerPort: 8080`, labels `app: ai-agent`
- URL uses implicit port 80, which maps to container port 8080 via Service — correct

**Note**: `WORKER-PLAN.md` line 45 documents the URL as `http://ai-agent.default.svc.cluster.local:8080/alert` (with explicit port 8080), but `helm-values.yaml` correctly omits the port (defaulting to 80, which the Service maps to 8080). The plan doc is slightly inaccurate but the implementation is correct.

---

## Group 4: Alert Payload Handling (PASS)

**Files**: `ai-agent/app.py`, `kubernetes/monitoring/prometheus-rules.yaml`, `openslo/*.yaml`

No mismatches found:
- Agent extracts `slo_name` from `payload.commonLabels.slo_name` (primary) or `alerts[].labels.slo_name` (fallback) — matches Alertmanager webhook format
- Alert rules define `slo_name: example-service-latency` and `slo_name: example-service-error-rate`
- OpenSLO files are named `example-service-latency.yaml` and `example-service-error-rate.yaml` — exact match
- Agent constructs path `OPENSLO_DIR/<slo_name>.yaml` — resolves correctly
- Path traversal protection is in place

---

## Recommendations

1. **Add `sum()` to Prometheus recording rules** — aligns with OpenSLO spec and prevents per-label-combination series proliferation
2. **Harmonize error rate semantics** — either change the recording rule to compute good/total (matching OpenSLO) or document the inversion clearly
3. **Add `alertPolicies` to error rate OpenSLO** — complete the spec to match the latency definition
4. **Update WORKER-PLAN.md** — fix the documented webhook URL to match implementation (remove `:8080`)
