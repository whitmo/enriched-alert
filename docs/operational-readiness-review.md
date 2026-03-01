# Operational Readiness Review

**Date:** 2026-03-01
**Reviewer:** swift-raccoon (automated, with Gemini CLI assist)
**Scope:** Deployment pipeline — Makefile, Dockerfiles, K8s manifests, monitoring

---

## Critical Issues (will cause deployment failure)

### 1. Makefile references non-existent deployment manifests

**Severity:** CRITICAL — `make deploy` fails

The `agent-deploy` and `service-deploy` targets reference paths that don't exist:

```makefile
# Makefile:119 — path does not exist
kubectl apply -n $(TEST_NS) -f ./kubernetes/agent-deployment.yaml

# Makefile:124 — path does not exist
kubectl apply -n $(TEST_NS) -f ./kubernetes/service-deployment.yaml
```

Actual file locations:
- `ai-agent/kubernetes/deployment.yaml`
- `example-service/kubernetes/deployment.yaml`

The Service manifests (`ai-agent/kubernetes/service.yaml`, `example-service/kubernetes/service.yaml`) are also not applied by any Makefile target.

### 2. Prometheus rules never deployed

**Severity:** CRITICAL — no SLO alerting

`rules-deploy` (Makefile:137) checks for `./kubernetes/rules/` directory, which doesn't exist. The actual rules file is `kubernetes/monitoring/prometheus-rules.yaml`. No alerts will ever fire.

### 3. ServiceMonitor never deployed

**Severity:** CRITICAL — Prometheus can't scrape metrics

The ServiceMonitor at `kubernetes/monitoring/service-monitor.yaml` is not referenced by any Makefile target. Without it, Prometheus won't discover the example-service, so metrics are never collected and rules can't evaluate.

### 4. ServiceMonitor hardcoded to `default` namespace

**Severity:** CRITICAL (when using namespace isolation)

```yaml
# kubernetes/monitoring/service-monitor.yaml:9-10
namespaceSelector:
  matchNames:
    - default
```

This breaks namespace-isolated deploys (`TEST_NS != default`). Should be dynamically set or use `any: true`.

---

## High Issues (will cause runtime failures)

### 5. Alertmanager webhook port mismatch

**Severity:** HIGH — alerts won't reach AI agent

```yaml
# kubernetes/helm-values/alertmanager-values.yaml.tpl:15
url: 'http://ai-agent.DEPLOY_NAMESPACE.svc.cluster.local:8080/alert'
```

The ai-agent Service exposes port **80** (targetPort 8080). K8s Service DNS resolves to the ClusterIP, which only listens on the Service port (80). Using `:8080` will fail with connection refused.

**Fix:** Use port 80 or omit the port entirely.

### 6. Exercise targets use wrong port

**Severity:** HIGH — exerciser traffic fails

```makefile
# Makefile:148
curl -s http://example-service.$(TEST_NS).svc.cluster.local:8080/health
```

The example-service Service exposes port **80** (targetPort 8080). Same issue as #5 — should use port 80 or omit port.

### 7. Exercise breach uses wrong query parameter

**Severity:** HIGH — latency breach won't trigger

```makefile
# Makefile:155
curl -s http://example-service....:8080/latency?delay=2000
```

The FastAPI endpoint uses `delay_ms` as the parameter name:
```python
# example-service/app.py:66
async def latency(delay_ms: int = 0):
```

`?delay=2000` is an unrecognized parameter and will be ignored. The request completes instantly (0ms), never breaching the 500ms SLO threshold. Should be `?delay_ms=2000`.

---

## Medium Issues (reliability / reproducibility)

### 8. kind-config.yaml not used by Makefile

**Severity:** MEDIUM

The `kind-up` target creates a cluster without `--config kind-config.yaml`:
```makefile
# Makefile:60
KIND_CONTAINER_RUNTIME=$(KIND_RUNTIME) kind create cluster --name $(KIND_CLUSTER_NAME) || true
```

The extra port mappings (30080, 30090, 30093) in `kind-config.yaml` are never applied. If NodePort access to Prometheus/Alertmanager is intended, the cluster won't have the port mappings.

### 9. No version pinning in requirements.txt

**Severity:** MEDIUM — non-reproducible builds

Neither `ai-agent/requirements.txt` nor `example-service/requirements.txt` pin dependency versions. Builds may break silently when upstream packages update.

### 10. `uv` not version-pinned in Dockerfiles

**Severity:** MEDIUM

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
```

Using `:latest` tag means builds aren't reproducible.

### 11. Hardcoded GEMINI_TMP_DIR path

**Severity:** MEDIUM — breaks for other developers

```makefile
# Makefile:16
GEMINI_TMP_DIR ?= /Users/whit/.gemini/tmp/1a93520244d34034b85edcaf49363e36b9daf386fab35bdd7158f71fa937dd9e
```

This hardcodes a user-specific path. The kubeconfig is stored here, so other developers can't use the Makefile without overriding this variable.

---

## Low Issues (best practices)

### 12. ai-agent deployment missing readiness probe

The ai-agent has a `livenessProbe` but no `readinessProbe`. The example-service has both. Without a readiness probe, the Service may route traffic to the agent before it's ready.

### 13. ai-agent deployment missing resource requests

```yaml
# ai-agent/kubernetes/deployment.yaml:33-35 — only limits, no requests
resources:
  limits:
    memory: "128Mi"
    cpu: "250m"
```

The example-service has both `requests` and `limits`. Without requests, the scheduler makes suboptimal placement decisions.

### 14. `kind create cluster` failure suppressed

```makefile
# Makefile:60
kind create cluster --name $(KIND_CLUSTER_NAME) || true
```

The `|| true` swallows all errors, including genuine failures (not just "cluster already exists"). Consider checking if the cluster exists first.

---

## Summary

| Severity | Count | Deploy Impact |
|----------|-------|---------------|
| CRITICAL | 4 | `make deploy` fails, no monitoring |
| HIGH | 3 | Alerts don't route, exercises don't work |
| MEDIUM | 4 | Reproducibility, portability |
| LOW | 3 | Best practices |

**Bottom line:** `make all` / `make deploy` will fail at the `agent-deploy` step due to missing manifest paths. Even if those were fixed, the monitoring pipeline is broken end-to-end: ServiceMonitor and PrometheusRules are never deployed, and the Alertmanager webhook uses the wrong port. The exercise targets also use wrong ports and query parameters, so even manual testing won't produce the expected SLO breaches.
