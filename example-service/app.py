"""Example service with Prometheus metrics for SLO demonstration."""

import asyncio
import json
import random
import time

from fastapi import FastAPI, Query, Request, Response
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

app = FastAPI(title="Example Service")

# Known routes for metric label normalization (prevents cardinality explosion)
KNOWN_ROUTES = frozenset(
    {"/health", "/api", "/latency", "/error", "/cascade-failure", "/resource-exhaustion"}
)

# Prometheus metrics
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "endpoint", "status_code"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "endpoint", "status_code"],
)

CASCADE_FAILURES = Counter(
    "cascade_failure_total",
    "Total cascade failure events (where at least one hop failed)",
    labelnames=["depth"],
)

MEMORY_PRESSURE_BYTES = Gauge(
    "memory_pressure_bytes",
    "Current bytes held by resource-exhaustion simulation",
)


def _normalize_endpoint(path: str) -> str:
    """Map request paths to known routes; unknown paths become '/other'."""
    return path if path in KNOWN_ROUTES else "/other"


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    # Skip metrics endpoint itself to avoid recursion in counts
    if request.url.path == "/metrics":
        return await call_next(request)

    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    endpoint = _normalize_endpoint(request.url.path)
    method = request.method
    status_code = str(response.status_code)

    REQUEST_DURATION.labels(
        method=method, endpoint=endpoint, status_code=status_code
    ).observe(duration)
    REQUEST_COUNT.labels(
        method=method, endpoint=endpoint, status_code=status_code
    ).inc()

    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api")
async def api():
    return {"message": "hello", "service": "example-service"}


@app.get("/latency")
async def latency(delay_ms: int = Query(0, ge=0, le=10000)):
    if delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000.0)
    return {"delay_ms": delay_ms}


@app.get("/error")
async def error(code: int = Query(500, ge=400, le=599)):
    return Response(
        content=f'{{"error": "simulated", "code": {code}}}',
        status_code=code,
        media_type="application/json",
    )


# Module-level store for resource-exhaustion allocations (prevents GC)
_memory_store: list[bytes] = []
MEMORY_CAP_BYTES = 512 * 1024 * 1024  # 512 MB aggregate cap
_memory_allocated = 0  # current aggregate bytes held


@app.get("/cascade-failure")
async def cascade_failure(
    depth: int = Query(3, ge=1, le=10),
    failure_prob: float = Query(0.5, ge=0.0, le=1.0),
):
    """Simulate a chain of upstream calls; each hop fails with failure_prob."""
    failed_hops = [hop for hop in range(depth) if random.random() < failure_prob]

    if failed_hops:
        CASCADE_FAILURES.labels(depth=depth).inc()
        return Response(
            content=json.dumps(
                {
                    "error": "cascade_failure",
                    "depth": depth,
                    "failure_prob": failure_prob,
                    "failed_hops": failed_hops,
                }
            ),
            status_code=502,
            media_type="application/json",
        )
    return {"depth": depth, "failure_prob": failure_prob, "failed_hops": []}


@app.get("/resource-exhaustion")
async def resource_exhaustion(
    mb: int = Query(10, ge=1, le=512),
    hold_seconds: int = Query(30, ge=1, le=300),
):
    """Allocate memory to simulate resource pressure, release after hold_seconds."""
    global _memory_allocated
    requested = mb * 1024 * 1024
    if _memory_allocated + requested > MEMORY_CAP_BYTES:
        return Response(
            content=json.dumps({
                "error": "memory_cap_exceeded",
                "allocated_bytes": _memory_allocated,
                "cap_bytes": MEMORY_CAP_BYTES,
            }),
            status_code=429,
            media_type="application/json",
        )

    chunk = b"\x00" * requested
    _memory_store.append(chunk)
    _memory_allocated += requested
    MEMORY_PRESSURE_BYTES.inc(requested)

    async def _release():
        global _memory_allocated
        await asyncio.sleep(hold_seconds)
        try:
            _memory_store.remove(chunk)
            _memory_allocated -= requested
            MEMORY_PRESSURE_BYTES.dec(requested)
        except ValueError:
            pass

    asyncio.create_task(_release())
    return {"allocated_mb": mb, "hold_seconds": hold_seconds}


@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
