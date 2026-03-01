# Deployment & Ops Readiness Review

**Date:** 2026-03-01
**Reviewer:** wise-tiger (with Gemini CLI assist)
**Scope:** Docker builds, K8s manifests, Helm values, CI/CD pipelines, Makefile targets
**Context:** PoC — findings scaled accordingly. CRITICAL = blocks deployment or causes runtime failure. WARNING = degrades reliability or security. SUGGESTION = improvement for production path.

---

## Summary

| Severity | Count | Category |
|----------|-------|----------|
| CRITICAL | 6 | Broken paths, missing probes, security contexts, port mismatches |
| WARNING | 8 | Reproducibility, observability gaps, config inconsistencies |
| SUGGESTION | 9 | Production hardening, best practices |

---

## CRITICAL

### C1. Makefile deploy targets reference non-existent paths

**Files:** `Makefile:119`, `Makefile:124`

```makefile
kubectl apply -n $(TEST_NS) -f ./kubernetes/agent-deployment.yaml    # does not exist
kubectl apply -n $(TEST_NS) -f ./kubernetes/service-deployment.yaml  # does not exist
```

Actual locations: `ai-agent/kubernetes/deployment.yaml` and `example-service/kubernetes/deployment.yaml`. The corresponding Service manifests (`*/kubernetes/service.yaml`) are also never applied by any Makefile target.

**Impact:** `make deploy` fails. No services come up.

### C2. Prometheus rules and ServiceMonitor never deployed

**Files:** `Makefile:137-141`, `Makefile` (no target for ServiceMonitor)

- `rules-deploy` checks `./kubernetes/rules/` — doesn't exist. Rules are at `kubernetes/monitoring/prometheus-rules.yaml`.
- `kubernetes/monitoring/service-monitor.yaml` has no Makefile target at all.

**Impact:** Prometheus has no recording/alerting rules, can't discover the example-service for scraping. The entire monitoring pipeline is inert.

### C3. Alertmanager webhook template uses wrong port

**File:** `kubernetes/helm-values/alertmanager-values.yaml.tpl:15`

```yaml
url: 'http://ai-agent.DEPLOY_NAMESPACE.svc.cluster.local:8080/alert'
```

The ai-agent Service exposes port **80** → targetPort 8080. Hitting `:8080` on the Service ClusterIP produces connection refused. The static `helm-values.yaml` correctly omits the port (implicit 80), but the template used by namespace-isolated deploys breaks.

**Impact:** Alerts never reach the AI agent in namespace-isolated deployments.

### C4. Containers run as root

**Files:** `ai-agent/Dockerfile`, `example-service/Dockerfile`

Neither Dockerfile creates a non-root user. Both K8s deployments lack `securityContext` fields (`runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`).

**Impact:** Container compromise grants root access. Violates K8s security baselines (Restricted, Baseline).

### C5. ai-agent deployment missing readinessProbe

**File:** `ai-agent/kubernetes/deployment.yaml`

Has a `livenessProbe` but no `readinessProbe`. The example-service has both. Without readiness, the Service routes traffic to the pod before FastAPI is accepting connections.

**Impact:** Alert webhooks sent during startup are dropped silently.

### C6. Exerciser targets use wrong port and query parameter

**File:** `Makefile:148, 155`

```makefile
# exercise-normal: port 8080 should be 80 (Service port)
curl -s http://example-service.$(TEST_NS).svc.cluster.local:8080/health

# exercise-breach: wrong port AND wrong param name
curl -s http://example-service....:8080/latency?delay=2000
#                                                ^^^^^ should be delay_ms
```

The example-service endpoint is `async def latency(delay_ms: int = 0)`. Using `?delay=2000` is ignored — request returns instantly, never breaching the 500ms SLO.

**Impact:** Manual exerciser testing produces no SLO breaches and no alerts.

---

## WARNING

### W1. ServiceMonitor hardcoded to `default` namespace

**File:** `kubernetes/monitoring/service-monitor.yaml:9-10`

```yaml
namespaceSelector:
  matchNames:
    - default
```

Breaks namespace-isolated deploys (`TEST_NS != default`). Should use `any: true` or be parameterized.

### W2. Conflicting Alertmanager configs

**Files:** `kubernetes/monitoring/helm-values.yaml`, `kubernetes/helm-values/alertmanager-values.yaml.tpl`

Two separate Alertmanager configurations exist with different structures:
- `helm-values.yaml`: receiver `ai-agent`, matchers `alerttype = slo`, hardcodes `default` namespace
- `alertmanager-values.yaml.tpl`: receiver `ai-agent-webhook`, no matchers, uses `DEPLOY_NAMESPACE` placeholder

The Makefile's `monitoring-up` target uses the template if it exists, otherwise falls back. Both can't be correct. The static one has proper alert routing matchers but wrong namespace handling; the template has namespace handling but no matchers.

### W3. No version pinning in requirements.txt

**Files:** `ai-agent/requirements.txt`, `example-service/requirements.txt`

```
fastapi
uvicorn[standard]
pyyaml
```

No version constraints. A breaking upstream release silently breaks builds.

### W4. `uv` not version-pinned in Dockerfiles

**Files:** Both Dockerfiles

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
```

`:latest` makes builds non-reproducible.

### W5. No `.dockerignore` files

**Files:** `ai-agent/`, `example-service/`

Missing `.dockerignore` means `tests/`, `__pycache__/`, `.git/` and other unnecessary files are included in the build context. Currently mitigated by specific `COPY` instructions, but fragile.

### W6. ai-agent missing resource requests

**File:** `ai-agent/kubernetes/deployment.yaml:33-35`

```yaml
resources:
  limits:
    memory: "128Mi"
    cpu: "250m"
# no requests — scheduler defaults requests to limits (in some environments)
```

The example-service sets both `requests` and `limits`. Without explicit requests, scheduling is unpredictable.

### W7. ai-agent has no Prometheus metrics endpoint

**File:** `ai-agent/app.py`

The example-service exposes `/metrics` with `prometheus_client`. The ai-agent has no metrics at all — no request counts, no alert processing latency, no error rates. Observable only through logs.

### W8. Hardcoded user-specific path in Makefile

**File:** `Makefile:16`

```makefile
GEMINI_TMP_DIR ?= /Users/whit/.gemini/tmp/1a93520244d...
```

This kubeconfig path is user-specific. Other developers must override this variable to use the Makefile.

---

## SUGGESTION

### S1. kind-config.yaml not used by Makefile

**File:** `Makefile:60`

The `kind-up` target doesn't pass `--config kind-config.yaml`. The NodePort mappings (30080, 30090, 30093) defined in `kind-config.yaml` are never applied, making the Prometheus and Alertmanager NodePort services in `helm-values.yaml` inaccessible from the host.

### S2. `kind create cluster` error suppressed

**File:** `Makefile:60`

```makefile
kind create cluster --name $(KIND_CLUSTER_NAME) || true
```

`|| true` swallows genuine failures (disk full, network errors), not just "cluster already exists". Consider checking cluster existence first with `kind get clusters | grep -q`.

### S3. No CI dependency caching

**File:** `.github/workflows/integration-tests.yaml`

The integration test workflow downloads Kind, kubectl, Helm, and all Python dependencies on every run. Adding `actions/cache` for pip/uv and tool binaries would cut CI time significantly.

### S4. No container image vulnerability scanning in CI

**File:** `.github/workflows/smoke-tests.yaml`

Hadolint catches Dockerfile style issues but not CVEs in base images or dependencies. Consider adding Trivy or Grype scanning.

### S5. No dependency vulnerability scanning

**Files:** CI workflows

No `pip-audit` or equivalent to catch known-vulnerable Python packages.

### S6. Add Pod Disruption Budgets for production

**Files:** K8s deployment manifests

Neither service defines a PDB. Acceptable for single-replica PoC, but needed if replicas increase.

### S7. Add Network Policies

**Files:** K8s manifests

No NetworkPolicy resources. The ai-agent should only accept traffic from Alertmanager; the example-service should only accept traffic from within the cluster.

### S8. Use `imagePullPolicy: IfNotPresent` for portability

**Files:** Both K8s deployments

`imagePullPolicy: Never` is Kind-specific. `IfNotPresent` works for both Kind (pre-loaded images) and registry-backed deployments.

### S9. Verify graceful shutdown handling

**Files:** `ai-agent/app.py`, `example-service/app.py`

Uvicorn handles SIGTERM by default, but neither app registers shutdown hooks. If the ai-agent is mid-processing an alert webhook when terminated, the response is lost. FastAPI's `@app.on_event("shutdown")` or lifespan context could handle graceful drain.

---

## Cross-references

- **`docs/operational-readiness-review.md`** — Previous review by swift-raccoon covering many of the same Makefile path issues (C1, C2, C6). Findings here are independently verified and consistent.
- **`docs/pipeline-contract-review.md`** — Covers metric/threshold contract issues (missing `sum()` in recording rules, semantic inversion in error rate). Those are pipeline correctness issues, not deployment/ops issues, and are not duplicated here.

---

## Recommended Fix Priority

1. **Fix Makefile paths** (C1, C2) — nothing works without this
2. **Add readinessProbe to ai-agent** (C5) — one-line fix, high impact
3. **Fix webhook template port** (C3) — remove `:8080`
4. **Fix exerciser port and param** (C6) — port 80, `delay_ms`
5. **Add non-root user and securityContext** (C4) — Dockerfile + manifest change
6. **Pin dependency versions** (W3, W4) — generate lockfile
7. **Resolve Alertmanager config conflict** (W2) — pick one source of truth
