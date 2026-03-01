"""Example service with Prometheus metrics for SLO demonstration."""

import asyncio
import time

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

app = FastAPI(title="Example Service")

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


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    # Skip metrics endpoint itself to avoid recursion in counts
    if request.url.path == "/metrics":
        return await call_next(request)

    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    endpoint = request.url.path
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
async def latency(delay_ms: int = 0):
    if delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000.0)
    return {"delay_ms": delay_ms}


@app.get("/error")
async def error(code: int = 500):
    return Response(
        content=f'{{"error": "simulated", "code": {code}}}',
        status_code=code,
        media_type="application/json",
    )


@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
