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


def test_metrics(client):
    # Make a request first to populate metrics
    client.get("/api")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "http_request_duration_seconds" in body
    assert "http_requests_total" in body
