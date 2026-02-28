import logging
import os
from pathlib import Path

import yaml
from fastapi import FastAPI, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-agent")

OPENSLO_DIR = Path(os.environ.get("OPENSLO_DIR", "./openslo"))

app = FastAPI(title="AI Agent Webhook Receiver")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/alert")
async def receive_alert(request: Request):
    payload = await request.json()
    logger.info("Received alert payload: %s", payload)

    # Extract slo_name from commonLabels first, then individual alerts
    slo_name = payload.get("commonLabels", {}).get("slo_name")

    if not slo_name:
        for alert in payload.get("alerts", []):
            slo_name = alert.get("labels", {}).get("slo_name")
            if slo_name:
                break

    if not slo_name:
        logger.warning("No slo_name found in alert payload")
        return {"status": "received", "enriched": False, "reason": "no slo_name label found"}

    # Load OpenSLO definition
    slo_file = OPENSLO_DIR / f"{slo_name}.yaml"
    slo_definition = None

    if slo_file.exists():
        with open(slo_file) as f:
            slo_definition = yaml.safe_load(f)
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
