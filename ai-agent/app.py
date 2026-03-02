import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-agent")

OPENSLO_DIR = Path(os.environ.get("OPENSLO_DIR", "./openslo")).resolve()
K8S_API_URL = os.environ.get("K8S_API_URL", "https://kubernetes.default.svc")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus.monitoring.svc:9090")

# K8s in-cluster CA cert path; override with K8S_CA_CERT env var for dev
_K8S_CA_CERT_DEFAULT = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
K8S_CA_CERT = os.environ.get("K8S_CA_CERT", _K8S_CA_CERT_DEFAULT)

# Only allow alphanumeric, hyphens, and underscores in SLO names
SLO_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
# K8s label/name validation: lowercase alphanumeric with hyphens, must start with alnum
K8S_NAME_RE = re.compile(r"^[a-z0-9][-a-z0-9]*$")

# Shared HTTP client — set during lifespan, used by gathering functions
http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(
        timeout=5.0,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
    yield
    await http_client.aclose()
    http_client = None


app = FastAPI(title="AI Agent Webhook Receiver", lifespan=lifespan)


class Alert(BaseModel):
    labels: dict[str, Any] = {}

    model_config = {"extra": "allow"}


class AlertmanagerPayload(BaseModel):
    commonLabels: dict[str, Any] = {}
    alerts: list[Alert] = []

    model_config = {"extra": "allow"}


def _k8s_ssl_context() -> bool | str:
    """Return CA cert path for K8s TLS verification, or True for system defaults."""
    ca_path = Path(K8S_CA_CERT)
    if ca_path.exists():
        return str(ca_path)
    return True


async def gather_k8s_events(
    deployment: str, namespace: str = "default", client: httpx.AsyncClient | None = None
) -> list[dict]:
    """Fetch recent K8s events for a deployment from the K8s API."""
    if not K8S_NAME_RE.match(deployment):
        logger.warning("Rejected invalid deployment name: '%s'", deployment)
        return []
    if not K8S_NAME_RE.match(namespace):
        logger.warning("Rejected invalid namespace: '%s'", namespace)
        return []

    token_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
    headers = {}
    if token_path.exists():
        headers["Authorization"] = f"Bearer {token_path.read_text().strip()}"

    field_selector = f"involvedObject.name={deployment}"
    url = (
        f"{K8S_API_URL}/api/v1/namespaces/{namespace}/events"
        f"?fieldSelector={field_selector}&limit=20"
    )

    c = client or http_client
    if c is None:
        logger.warning("No HTTP client available for K8s events gathering")
        return []
    try:
        resp = await c.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "reason": item.get("reason"),
                "message": item.get("message"),
                "type": item.get("type"),
                "last_timestamp": item.get("lastTimestamp"),
            }
            for item in data.get("items", [])
        ]
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning("Failed to gather K8s events for '%s': %s", deployment, exc)
        return []


async def gather_burn_rate(
    slo_name: str, client: httpx.AsyncClient | None = None
) -> dict | None:
    """Query Prometheus for the current burn rate of an SLO."""
    query = f'slo:burn_rate:1h{{slo_name="{slo_name}"}}'
    url = f"{PROMETHEUS_URL}/api/v1/query"

    c = client or http_client
    if c is None:
        logger.warning("No HTTP client available for burn rate gathering")
        return None
    try:
        resp = await c.get(url, params={"query": query})
        resp.raise_for_status()
        data = resp.json()
        results = data.get("data", {}).get("result", [])
        if results:
            value = results[0].get("value", [None, None])
            return {
                "slo_name": slo_name,
                "query": query,
                "value": float(value[1]) if value[1] is not None else None,
                "timestamp": value[0],
            }
        return {"slo_name": slo_name, "query": query, "value": None, "timestamp": None}
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning("Failed to gather burn rate for '%s': %s", slo_name, exc)
        return None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/alert")
async def receive_alert(payload: AlertmanagerPayload):
    logger.info("Received alert payload: %s", payload.model_dump())

    # Extract slo_name from commonLabels first, then individual alerts
    slo_name = payload.commonLabels.get("slo_name")

    if not slo_name:
        for alert in payload.alerts:
            slo_name = alert.labels.get("slo_name")
            if slo_name:
                break

    if not slo_name:
        logger.warning("No slo_name found in alert payload")
        return {"status": "received", "enriched": False, "reason": "no slo_name label found"}

    # Validate slo_name against allowlist pattern
    if not SLO_NAME_RE.match(slo_name):
        logger.warning("Rejected invalid slo_name: '%s'", slo_name)
        return JSONResponse(
            status_code=400,
            content={"status": "rejected", "reason": "invalid slo_name format"},
        )

    # Load OpenSLO definition
    slo_file = (OPENSLO_DIR / f"{slo_name}.yaml").resolve()
    if not str(slo_file).startswith(str(OPENSLO_DIR)):
        logger.warning("Resolved path outside OPENSLO_DIR: '%s'", slo_file)
        return JSONResponse(
            status_code=400,
            content={"status": "rejected", "reason": "invalid slo_name"},
        )

    slo_definition = None

    if slo_file.exists():
        with open(slo_file) as f:
            try:
                slo_definition = yaml.safe_load(f)
            except yaml.YAMLError:
                logger.warning("Malformed YAML in SLO file for '%s'", slo_name)
                return {"status": "received", "enriched": False, "reason": "malformed SLO definition"}
        logger.info("Loaded SLO definition for '%s': %s", slo_name, slo_definition)
    else:
        logger.warning("No OpenSLO definition found for '%s' at %s", slo_name, slo_file)

    # Gather structured context concurrently
    deployment = payload.commonLabels.get("deployment", slo_name)
    namespace = payload.commonLabels.get("namespace", "default")
    k8s_events, burn_rate = await asyncio.gather(
        gather_k8s_events(deployment, namespace),
        gather_burn_rate(slo_name),
    )

    logger.info(
        "Enriched alert context - SLO: '%s', Definition found: %s, Events: %d, Burn rate: %s",
        slo_name,
        slo_definition is not None,
        len(k8s_events),
        burn_rate,
    )

    return {
        "status": "received",
        "enriched": slo_definition is not None,
        "slo_name": slo_name,
        "slo_definition": slo_definition,
        "context": {
            "k8s_events": k8s_events,
            "burn_rate": burn_rate,
        },
    }
