"""Tests for the example service."""

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_api(client):
    resp = client.get("/api")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "example-service"
    assert "message" in data


def test_latency_no_delay(client):
    resp = client.get("/latency")
    assert resp.status_code == 200
    assert resp.json()["delay_ms"] == 0


def test_latency_with_delay(client):
    resp = client.get("/latency?delay_ms=50")
    assert resp.status_code == 200
    assert resp.json()["delay_ms"] == 50


def test_error_default(client):
    resp = client.get("/error")
    assert resp.status_code == 500
    assert resp.json()["code"] == 500


def test_error_custom_code(client):
    resp = client.get("/error?code=503")
    assert resp.status_code == 503
    assert resp.json()["code"] == 503


def test_cascade_failure_defaults(client):
    resp = client.get("/cascade-failure")
    # With default 50% failure_prob and depth=3, result is probabilistic
    assert resp.status_code in (200, 502)
    data = resp.json()
    assert "depth" in data
    assert "failure_prob" in data
    assert "failed_hops" in data


def test_cascade_failure_no_failures(client):
    resp = client.get("/cascade-failure?depth=5&failure_prob=0.0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["depth"] == 5
    assert data["failure_prob"] == 0.0
    assert data["failed_hops"] == []


def test_cascade_failure_all_fail(client):
    resp = client.get("/cascade-failure?depth=3&failure_prob=1.0")
    assert resp.status_code == 502
    data = resp.json()
    assert data["error"] == "cascade_failure"
    assert data["failed_hops"] == [0, 1, 2]


def test_cascade_failure_validation(client):
    resp = client.get("/cascade-failure?depth=0")
    assert resp.status_code == 422
    resp = client.get("/cascade-failure?depth=11")
    assert resp.status_code == 422
    resp = client.get("/cascade-failure?failure_prob=1.5")
    assert resp.status_code == 422


def test_resource_exhaustion_defaults(client):
    resp = client.get("/resource-exhaustion")
    assert resp.status_code == 200
    data = resp.json()
    assert data["allocated_mb"] == 10
    assert data["hold_seconds"] == 30


def test_resource_exhaustion_custom(client):
    resp = client.get("/resource-exhaustion?mb=1&hold_seconds=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["allocated_mb"] == 1
    assert data["hold_seconds"] == 1


def test_resource_exhaustion_validation(client):
    resp = client.get("/resource-exhaustion?mb=0")
    assert resp.status_code == 422
    resp = client.get("/resource-exhaustion?mb=513")
    assert resp.status_code == 422
    resp = client.get("/resource-exhaustion?hold_seconds=0")
    assert resp.status_code == 422


def test_metrics(client):
    # Make a request first to populate metrics
    client.get("/api")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "http_request_duration_seconds" in body
    assert "http_requests_total" in body


def test_metrics_cascade(client):
    client.get("/cascade-failure?depth=2&failure_prob=1.0")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "cascade_failure_total" in resp.text


def test_metrics_memory_pressure(client):
    client.get("/resource-exhaustion?mb=1&hold_seconds=1")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "memory_pressure_bytes" in resp.text
