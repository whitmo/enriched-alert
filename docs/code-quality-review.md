# Code Quality & Security Review

**Reviewer:** swift-fox (Claude)
**Date:** 2026-03-01
**Scope:** ai-agent/app.py, example-service/app.py, example-service/exerciser.py, and their test suites

---

## CRITICAL Issues

### C1. Unbounded `delay_ms` allows resource exhaustion (DoS)

**File:** `example-service/app.py:66-68`

```python
@app.get("/latency")
async def latency(delay_ms: int = 0):
    if delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000.0)
```

Any caller can pass `delay_ms=999999999`, tying up an asyncio worker for ~11.5 days. There is no upper bound. A handful of concurrent requests with extreme values can exhaust the uvicorn worker pool and deny service to legitimate traffic.

**Also note:** negative values silently pass (`delay_ms=-1` skips the sleep but is semantically wrong).

**Recommendation:** Clamp to a sane maximum (e.g., 10000ms) and reject negatives:
```python
delay_ms: int = Query(0, ge=0, le=10000)
```

---

### C2. Unbounded `code` parameter allows arbitrary HTTP status codes

**File:** `example-service/app.py:73-78`

```python
@app.get("/error")
async def error(code: int = 500):
    return Response(
        content=f'{{"error": "simulated", "code": {code}}}',
        status_code=code,
        media_type="application/json",
    )
```

No validation on `code`. A caller can set `code=200` (making the "error" endpoint return success, polluting metrics), `code=0` (likely crashes or sends malformed HTTP), or `code=99999` (undefined behavior in HTTP libraries). While this is a simulation endpoint, unvalidated status codes can confuse downstream monitoring, produce misleading SLO calculations, and create hard-to-debug Prometheus metric cardinality problems.

**Recommendation:** Restrict to valid HTTP error codes:
```python
code: int = Query(500, ge=400, le=599)
```

---

### C3. Unvalidated JSON body — malformed POST crashes the handler

**File:** `ai-agent/app.py:23`

```python
payload = await request.json()
```

If the POST body is not valid JSON (or has an unexpected Content-Type), `request.json()` raises a `JSONDecodeError` that propagates as an unhandled 500. The endpoint uses raw `Request` instead of a Pydantic model, so FastAPI's automatic validation doesn't apply.

**Recommendation:** Either wrap in try/except:
```python
try:
    payload = await request.json()
except Exception:
    return JSONResponse({"status": "error", "reason": "invalid JSON"}, status_code=400)
```
Or use a Pydantic model parameter instead of `Request`.

---

### C4. Metric label cardinality explosion via uncontrolled endpoint paths

**File:** `example-service/app.py:41`

```python
endpoint = request.url.path
```

The `endpoint` label is set to `request.url.path` verbatim. If anyone hits nonexistent paths (e.g., scanners hitting `/wp-admin`, `/.env`, `/api/v1/users/12345`), each unique path creates a new time series. In production, this leads to Prometheus cardinality explosion — memory bloat, slow queries, and potential OOM. Even in a PoC, scanners or fuzzing can trigger this.

**Recommendation:** Normalize paths to known routes or use a catch-all bucket:
```python
KNOWN_ENDPOINTS = {"/health", "/api", "/latency", "/error", "/metrics"}
endpoint = request.url.path if request.url.path in KNOWN_ENDPOINTS else "/other"
```

---

## WARNINGS

### W1. Path traversal check has a bypass via backslash or URL encoding

**File:** `ai-agent/app.py:40`

```python
if "/" in slo_name or ".." in slo_name:
```

The denylist approach checks for `/` and `..`, but:
- On certain filesystems/configurations, `\` (backslash) can act as a path separator
- Null bytes (`\x00`) can truncate filenames in some contexts
- The check doesn't account for unicode normalization tricks

The secondary `.resolve()` check on line 46 is a good defense-in-depth measure and catches most of these. However, the primary check gives a false sense of completeness.

**Note:** The `.resolve()` prefix check on line 45-48 is solid and is the real guard here. The denylist on line 40 is belt-and-suspenders but should be documented as such.

**Recommendation:** Consider using an allowlist pattern instead:
```python
import re
if not re.match(r'^[a-zA-Z0-9_-]+$', slo_name):
    # reject
```

---

### W2. `OPENSLO_DIR` is not resolved at module load time — TOCTOU risk

**File:** `ai-agent/app.py:11, 45-46`

```python
OPENSLO_DIR = Path(os.environ.get("OPENSLO_DIR", "./openslo"))
# ...
slo_file = (OPENSLO_DIR / f"{slo_name}.yaml").resolve()
if not str(slo_file).startswith(str(OPENSLO_DIR.resolve())):
```

`OPENSLO_DIR` is stored as a potentially relative `Path`. It's only `.resolve()`d at request time (line 46). If the process working directory changes between module load and request handling (unlikely but possible with some deployment tools), the resolved path could differ between the file lookup and the prefix check.

**Recommendation:** Resolve at module load:
```python
OPENSLO_DIR = Path(os.environ.get("OPENSLO_DIR", "./openslo")).resolve()
```

---

### W3. SLO definition content is returned verbatim to the caller

**File:** `ai-agent/app.py:69-74`

```python
return {
    "status": "received",
    "enriched": slo_definition is not None,
    "slo_name": slo_name,
    "slo_definition": slo_definition,
}
```

The full YAML content of the SLO file is returned in the response. If SLO definitions ever contain sensitive information (internal infrastructure details, metric queries exposing database names, etc.), this leaks to any caller who can POST to `/alert`. In a Kubernetes deployment, this endpoint is exposed as a Service.

**Recommendation:** Consider whether the full definition should be returned, or only specific fields. At minimum, document that this endpoint should not be exposed externally.

---

### W4. No request size limit on the webhook endpoint

**File:** `ai-agent/app.py:22-23`

```python
@app.post("/alert")
async def receive_alert(request: Request):
    payload = await request.json()
```

There is no limit on the request body size. An attacker could POST a multi-GB JSON payload, consuming memory. Uvicorn has a default limit (~16KB for headers) but not for body.

**Recommendation:** Add a body size check or configure uvicorn's `--limit-max-request-size`, or use FastAPI's dependency injection to enforce limits.

---

### W5. No readiness probe for ai-agent Kubernetes deployment

**File:** `ai-agent/kubernetes/deployment.yaml:26-31`

The ai-agent deployment has a `livenessProbe` but no `readinessProbe`. This means Kubernetes may route traffic to the pod before it's ready to serve. Compare with `example-service/kubernetes/deployment.yaml` which correctly has both probes.

**Recommendation:** Add a readinessProbe matching the livenessProbe configuration.

---

### W6. Dependencies not pinned in requirements.txt

**Files:** `ai-agent/requirements.txt`, `example-service/requirements.txt`

```
fastapi
uvicorn[standard]
pyyaml
```

No version pins. Builds are not reproducible. A new major release of any dependency could break the application without any code change. This is especially risky with `fastapi` which has had breaking changes between major versions.

**Recommendation:** Pin at least major versions:
```
fastapi>=0.115,<1.0
uvicorn[standard]>=0.34,<1.0
pyyaml>=6.0,<7.0
```

---

### W7. Exerciser `rps` timing drift under load

**File:** `example-service/exerciser.py:41-71`

```python
while time.time() < end_time:
    start = time.time()
    # ... build URL ...
    status = send_request(url)
    # ...
    elapsed = time.time() - start
    sleep_time = interval - elapsed
    if sleep_time > 0:
        time.sleep(sleep_time)
```

The exerciser uses synchronous `urlopen` with a 10-second timeout. In "latency" mode, requests can take 800-3000ms each. At `rps=10` (100ms interval), the exerciser will fall far behind its target rate because each request blocks for longer than the interval. The sleep compensation can't recover negative drift.

This isn't a bug per se (it's a load generator), but users expecting consistent RPS will get inconsistent results in latency/both modes.

**Recommendation:** Document this limitation, or consider using async/threaded requests for accurate RPS.

---

### W8. Exerciser treats 4xx responses as successful

**File:** `example-service/exerciser.py:65`

```python
if status >= 500 or status == 0:
    errors += 1
```

4xx responses (e.g., 400, 403, 404) are not counted as errors. While this may be intentional for the "errors" mode (which only generates 5xx), in "normal" mode a 4xx could indicate a real problem that goes unreported.

---

## SUGGESTIONS

### S1. Use Pydantic models for webhook payload validation

**File:** `ai-agent/app.py:22-23`

Instead of using raw `Request` and manual `.get()` chains, define Pydantic models:

```python
from pydantic import BaseModel
from typing import Optional

class AlertLabel(BaseModel):
    slo_name: Optional[str] = None
    alertname: Optional[str] = None

class Alert(BaseModel):
    status: str
    labels: AlertLabel = AlertLabel()

class AlertPayload(BaseModel):
    status: str
    commonLabels: AlertLabel = AlertLabel()
    alerts: list[Alert] = []
```

This gives automatic validation, documentation in the OpenAPI spec, and clearer error messages.

---

### S2. Test coverage gaps — ai-agent

**File:** `ai-agent/tests/test_app.py`

Missing test cases:
1. **Invalid JSON body** — POST with non-JSON content type or malformed body (relates to C3)
2. **slo_name from individual alert labels** — The code falls back to `alerts[].labels.slo_name` (lines 30-33) but no test covers this path
3. **Empty string slo_name** — `""` passes the `if not slo_name` check but is it handled correctly downstream?
4. **SLO file not found** — No test covers the `else` branch at line 61 where the YAML file doesn't exist
5. **Null bytes / special characters in slo_name** — The denylist only checks `/` and `..`
6. **Concurrent requests** — No async/stress tests

---

### S3. Test coverage gaps — example-service

**File:** `example-service/tests/test_app.py`

Missing test cases:
1. **Latency endpoint with negative delay** — `delay_ms=-100` (relates to C1)
2. **Error endpoint with non-error codes** — `code=200`, `code=0`, `code=99999` (relates to C2)
3. **Error endpoint with non-integer code** — `?code=abc`
4. **Metrics middleware with unknown paths** — Verify cardinality behavior (relates to C4)
5. **Metrics middleware timing accuracy** — Check that `http_request_duration_seconds` is approximately correct
6. **Concurrent request handling** — No async stress tests

---

### S4. Exerciser has no test coverage

**File:** `example-service/exerciser.py`

The exerciser script has zero tests. While it's a utility script, the `send_request` and `run` functions are testable units. Consider at minimum:
- `send_request` with a mock server
- `run` with a very short duration to verify loop logic
- Mode selection logic

---

### S5. No structured logging in ai-agent

**File:** `ai-agent/app.py:8`

```python
logging.basicConfig(level=logging.INFO)
```

The WORKER-PLAN.md specifies "Structured JSON logging for easy inspection" but the agent uses plain text logging. In a Kubernetes environment, structured JSON logs are much easier to search and aggregate.

**Recommendation:**
```python
import json
class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({"level": record.levelname, "msg": record.getMessage(), "ts": record.created})
```

---

### S6. Dockerfiles don't set a non-root user

**Files:** `ai-agent/Dockerfile`, `example-service/Dockerfile`

Both containers run as root. This is a defense-in-depth issue — if the application is compromised, the attacker has root inside the container.

**Recommendation:**
```dockerfile
RUN adduser --disabled-password --no-create-home appuser
USER appuser
```

---

### S7. No CORS configuration on either service

**Files:** `ai-agent/app.py`, `example-service/app.py`

Neither service configures CORS. If these endpoints are ever accessed from a browser (e.g., a future dashboard), this would need to be addressed. Not urgent for a PoC with service-to-service communication only.

---

### S8. Makefile references stale paths

**File:** `Makefile:119, 124`

```makefile
kubectl apply -n $(TEST_NS) -f ./kubernetes/agent-deployment.yaml
kubectl apply -n $(TEST_NS) -f ./kubernetes/service-deployment.yaml
```

The actual deployment files are at `ai-agent/kubernetes/deployment.yaml` and `example-service/kubernetes/deployment.yaml`, not `./kubernetes/agent-deployment.yaml` and `./kubernetes/service-deployment.yaml`. The integration test CI handles both paths (lines 92-110), but the Makefile would fail.

---

### S9. Integration test exerciser hits wrong endpoints

**File:** `.github/workflows/integration-tests.yaml:129`

```bash
curl -sf http://example-service/slow; curl -sf http://example-service/error
```

The example service has no `/slow` endpoint. It has `/latency?delay_ms=N`. This means the exerciser step in CI produces 404s instead of latency-inducing requests, and the SLO breach test may not trigger as intended.

**Recommendation:**
```bash
curl -sf "http://example-service/latency?delay_ms=2000"; curl -sf http://example-service/error
```

---

### S10. AI agent test fixture uses `importlib.reload` — fragile pattern

**File:** `ai-agent/tests/test_app.py:30-33`

```python
import importlib
import app as app_module
importlib.reload(app_module)
return TestClient(app_module.app)
```

The `importlib.reload` is needed because `OPENSLO_DIR` is set at module load time. This is fragile — it can cause issues with module-level state, duplicate registrations, etc. A cleaner approach would be to make `OPENSLO_DIR` configurable at request time or as a FastAPI dependency.

---

## Summary

| Severity | Count | Key Themes |
|----------|-------|------------|
| CRITICAL | 4 | Input validation (DoS via delay_ms, arbitrary status codes, unvalidated JSON, metric cardinality) |
| WARNING  | 8 | Path traversal edge cases, info leakage, missing K8s readiness probe, unpinned deps, exerciser drift |
| SUGGESTION | 10 | Pydantic models, test coverage gaps, structured logging, Dockerfile hardening, stale CI/Makefile paths |

**Overall Assessment:** The core pipeline logic is sound — alert reception, SLO lookup, and enrichment work correctly. The path traversal defense is well-layered (denylist + resolve check). Test coverage for happy paths is good. The main concerns are around input validation at system boundaries (C1-C4) and test coverage for edge cases and error paths (S2-S4). The integration CI has a concrete bug (S9) that likely prevents the breach test from working as intended.
