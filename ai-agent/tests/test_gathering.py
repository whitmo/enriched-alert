"""Tests for gather_k8s_events and gather_burn_rate functions."""

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def openslo_dir(tmp_path):
    slo_def = {
        "apiVersion": "openslo/v1",
        "kind": "SLO",
        "metadata": {"name": "my-service-latency"},
        "spec": {
            "description": "Latency SLO for my-service",
            "service": "my-service",
            "budgetingMethod": "Occurrences",
        },
    }
    slo_file = tmp_path / "my-service-latency.yaml"
    with open(slo_file, "w") as f:
        yaml.dump(slo_def, f)
    return tmp_path


@pytest.fixture
def app_module(openslo_dir, monkeypatch):
    monkeypatch.setenv("OPENSLO_DIR", str(openslo_dir))
    monkeypatch.setenv("K8S_API_URL", "https://k8s-test.local")
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom-test.local:9090")
    import app as mod
    importlib.reload(mod)
    return mod


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


# --- gather_k8s_events tests ---


@pytest.mark.anyio
async def test_gather_k8s_events_success(app_module):
    """Should parse K8s event items into simplified dicts."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "items": [
            {
                "reason": "Pulled",
                "message": "Successfully pulled image",
                "type": "Normal",
                "lastTimestamp": "2026-03-01T00:00:00Z",
            },
            {
                "reason": "BackOff",
                "message": "Back-off restarting failed container",
                "type": "Warning",
                "lastTimestamp": "2026-03-01T00:01:00Z",
            },
        ]
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.httpx.AsyncClient", return_value=mock_client):
        events = await app_module.gather_k8s_events("my-deploy", "default")

    assert len(events) == 2
    assert events[0]["reason"] == "Pulled"
    assert events[0]["message"] == "Successfully pulled image"
    assert events[0]["type"] == "Normal"
    assert events[1]["reason"] == "BackOff"
    assert events[1]["type"] == "Warning"


@pytest.mark.anyio
async def test_gather_k8s_events_empty(app_module):
    """Should return empty list when no events found."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"items": []}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.httpx.AsyncClient", return_value=mock_client):
        events = await app_module.gather_k8s_events("nonexistent")

    assert events == []


@pytest.mark.anyio
async def test_gather_k8s_events_http_error(app_module):
    """Should return empty list on HTTP error."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.httpx.AsyncClient", return_value=mock_client):
        events = await app_module.gather_k8s_events("my-deploy")

    assert events == []


# --- gather_burn_rate tests ---


@pytest.mark.anyio
async def test_gather_burn_rate_success(app_module):
    """Should parse Prometheus response and return burn rate value."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {"slo_name": "my-service-latency"},
                    "value": [1709251200, "2.5"],
                }
            ],
        },
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.httpx.AsyncClient", return_value=mock_client):
        result = await app_module.gather_burn_rate("my-service-latency")

    assert result is not None
    assert result["slo_name"] == "my-service-latency"
    assert result["value"] == 2.5
    assert result["timestamp"] == 1709251200


@pytest.mark.anyio
async def test_gather_burn_rate_no_results(app_module):
    """Should return value=None when Prometheus has no data for the SLO."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "status": "success",
        "data": {"resultType": "vector", "result": []},
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.httpx.AsyncClient", return_value=mock_client):
        result = await app_module.gather_burn_rate("unknown-slo")

    assert result is not None
    assert result["slo_name"] == "unknown-slo"
    assert result["value"] is None


@pytest.mark.anyio
async def test_gather_burn_rate_http_error(app_module):
    """Should return None on HTTP error."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.httpx.AsyncClient", return_value=mock_client):
        result = await app_module.gather_burn_rate("my-service-latency")

    assert result is None


# --- Integration: /alert endpoint with mocked gathering ---


def test_alert_response_includes_context(client):
    """The /alert endpoint should include context.k8s_events and context.burn_rate."""
    k8s_events = [{"reason": "Scaled", "message": "Scaled up", "type": "Normal", "last_timestamp": None}]
    burn_rate = {"slo_name": "my-service-latency", "query": "test", "value": 1.8, "timestamp": 1709251200}

    with (
        patch("app.gather_k8s_events", new_callable=AsyncMock, return_value=k8s_events),
        patch("app.gather_burn_rate", new_callable=AsyncMock, return_value=burn_rate),
    ):
        payload = {
            "commonLabels": {"slo_name": "my-service-latency"},
            "alerts": [],
        }
        response = client.post("/alert", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["context"]["k8s_events"] == k8s_events
    assert data["context"]["burn_rate"] == burn_rate
    assert data["context"]["burn_rate"]["value"] == 1.8


def test_alert_context_with_deployment_label(client):
    """Should use deployment label from commonLabels for k8s events gathering."""
    with (
        patch("app.gather_k8s_events", new_callable=AsyncMock, return_value=[]) as mock_k8s,
        patch("app.gather_burn_rate", new_callable=AsyncMock, return_value=None),
    ):
        payload = {
            "commonLabels": {
                "slo_name": "my-service-latency",
                "deployment": "my-deploy",
                "namespace": "production",
            },
            "alerts": [],
        }
        client.post("/alert", json=payload)

    mock_k8s.assert_called_once_with("my-deploy", "production")


def test_alert_context_defaults_deployment_to_slo_name(client):
    """Without deployment label, should use slo_name as deployment name."""
    with (
        patch("app.gather_k8s_events", new_callable=AsyncMock, return_value=[]) as mock_k8s,
        patch("app.gather_burn_rate", new_callable=AsyncMock, return_value=None),
    ):
        payload = {
            "commonLabels": {"slo_name": "my-service-latency"},
            "alerts": [],
        }
        client.post("/alert", json=payload)

    mock_k8s.assert_called_once_with("my-service-latency", "default")


def test_alert_context_graceful_on_gather_failure(client):
    """Gathering failures should not prevent the alert response."""
    with (
        patch("app.gather_k8s_events", new_callable=AsyncMock, return_value=[]),
        patch("app.gather_burn_rate", new_callable=AsyncMock, return_value=None),
    ):
        payload = {
            "commonLabels": {"slo_name": "my-service-latency"},
            "alerts": [],
        }
        response = client.post("/alert", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["context"]["k8s_events"] == []
    assert data["context"]["burn_rate"] is None
    assert data["enriched"] is True  # SLO definition still found
