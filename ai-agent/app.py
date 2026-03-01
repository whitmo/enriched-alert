import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-agent")

OPENSLO_DIR = Path(os.environ.get("OPENSLO_DIR", "./openslo")).resolve()

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

    logger.info(
        "Enriched alert context - SLO: '%s', Definition found: %s",
        slo_name,
        slo_definition is not None,
    )

    return {
        "status": "received",
        "enriched": slo_definition is not None,
        "slo_name": slo_name,
        "slo_definition": slo_definition,
    }
