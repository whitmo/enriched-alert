import os
import tempfile

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def openslo_dir(tmp_path):
    """Create a temporary openslo directory with a sample SLO definition."""
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
def client(openslo_dir, monkeypatch):
    """Create a test client with OPENSLO_DIR pointing to temp directory."""
    monkeypatch.setenv("OPENSLO_DIR", str(openslo_dir))
    # Re-import to pick up new env var
    import importlib
    import app as app_module
    importlib.reload(app_module)
    return TestClient(app_module.app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_alert_valid_payload(client):
    payload = {
        "status": "firing",
        "commonLabels": {
            "alertname": "SLOBreach",
            "slo_name": "my-service-latency",
        },
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "SLOBreach",
                    "slo_name": "my-service-latency",
                },
                "annotations": {"summary": "SLO breach detected"},
            }
        ],
    }
    response = client.post("/alert", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "received"
    assert data["enriched"] is True
    assert data["slo_name"] == "my-service-latency"
    assert data["slo_definition"] is not None
    assert data["slo_definition"]["kind"] == "SLO"


def test_alert_missing_slo_name(client):
    payload = {
        "status": "firing",
        "commonLabels": {"alertname": "SomeOtherAlert"},
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "SomeOtherAlert"},
            }
        ],
    }
    response = client.post("/alert", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "received"
    assert data["enriched"] is False
    assert data["reason"] == "no slo_name label found"


def test_alert_path_traversal(client, openslo_dir):
    """slo_name with path traversal should be rejected, not read files outside OPENSLO_DIR."""
    # Create a file outside the openslo dir that should NOT be reachable
    outside_file = openslo_dir.parent / "secret.yaml"
    outside_file.write_text("secret: data")

    for malicious_name in ["../../etc/passwd", "../secret", "foo/../../etc/passwd"]:
        payload = {
            "status": "firing",
            "commonLabels": {"slo_name": malicious_name},
            "alerts": [],
        }
        response = client.post("/alert", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["enriched"] is False
        assert data["reason"] == "invalid slo_name", f"Failed for slo_name={malicious_name}"


def test_alert_malformed_yaml(client, openslo_dir):
    """Malformed YAML in SLO file should return enriched=False with reason."""
    bad_file = openslo_dir / "bad-slo.yaml"
    bad_file.write_text("not: valid: yaml:\n  - [unclosed")

    payload = {
        "status": "firing",
        "commonLabels": {"slo_name": "bad-slo"},
        "alerts": [],
    }
    response = client.post("/alert", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["enriched"] is False
    assert data["reason"] == "malformed SLO definition"
