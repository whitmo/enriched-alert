import logging
import os
import re
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

# Only allow alphanumeric, hyphens, and underscores in SLO names
SLO_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

app = FastAPI(title="AI Agent Webhook Receiver")


class Alert(BaseModel):
    labels: dict[str, Any] = {}

    model_config = {"extra": "allow"}


class AlertmanagerPayload(BaseModel):
    commonLabels: dict[str, Any] = {}
    alerts: list[Alert] = []

    model_config = {"extra": "allow"}


async def gather_k8s_events(deployment: str, namespace: str = "default") -> list[dict]:
    """Fetch recent K8s events for a deployment from the K8s API."""
    token_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
    headers = {}
    if token_path.exists():
        headers["Authorization"] = f"Bearer {token_path.read_text().strip()}"

    field_selector = f"involvedObject.name={deployment}"
    url = (
        f"{K8S_API_URL}/api/v1/namespaces/{namespace}/events"
        f"?fieldSelector={field_selector}&limit=20"
    )

    try:
        async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
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
    except httpx.HTTPError as exc:
        logger.warning("Failed to gather K8s events for '%s': %s", deployment, exc)
        return []


async def gather_burn_rate(slo_name: str) -> dict | None:
    """Query Prometheus for the current burn rate of an SLO."""
    query = f'slo:burn_rate:1h{{slo_name="{slo_name}"}}'
    url = f"{PROMETHEUS_URL}/api/v1/query"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params={"query": query})
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
    except httpx.HTTPError as exc:
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

    # Gather structured context: K8s events and burn rate
    deployment = payload.commonLabels.get("deployment", slo_name)
    namespace = payload.commonLabels.get("namespace", "default")
    k8s_events = await gather_k8s_events(deployment, namespace)
    burn_rate = await gather_burn_rate(slo_name)

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
