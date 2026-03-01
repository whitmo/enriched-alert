# Deep Example: Enriched Alert PoC Design

> **Note:** This file was assembled from existing research docs (`docs/anomaly-detection-problem.md`, `docs/cicd-group.md`, and task descriptions) because `docs/research/rich-example-app.md` was not found in the repo. Update this file if the original source is located.

## Overview

An AI-driven SLO monitoring and response system. The PoC demonstrates:

- SLI collection via Prometheus
- SLO definition via OpenSLO
- Alerting via Alertmanager
- AI agent webhook for enriched alert response

## Architecture

```
data (SLIs) => detection boundary (SLOs) => agent => response
```

### Proto Stack

| Layer | Technology |
|---|---|
| Metrics sink | Prometheus |
| Alerting | Alertmanager |
| Anomaly detection | Grafana |
| SLO management | OpenSLO |
| Incident analysis | k8sgpt |
| Local K8s | Kind + Podman |

## Components

### 1. Deployment Pipeline (Task 1)

Local Kubernetes via Kind with Podman as container runtime. Provides the environment for all other components.

### 2. Monitoring Infrastructure (Task 2)

Prometheus + Alertmanager + Grafana stack deployed to the Kind cluster.

### 3. AI Agent Webhook (Task 3)

A webhook receiver (Python/FastAPI) that:
- Receives alerts from Alertmanager
- Parses alert payload to identify breached SLO
- Loads corresponding OpenSLO definition for context
- Logs enriched alert (initial response action)

### 4. Example Service + Exerciser + SLOs (Task 4)

- Lightweight HTTP service exposing Prometheus metrics (latency histogram, error counter)
- OpenSLO YAML definitions for latency and error rate SLOs
- Exerciser script to deterministically trigger SLO breaches

## Conceptual Flow

1. **Metrics Collection**: Example service exposes SLIs via Prometheus client
2. **SLO Definition**: OpenSLO YAMLs define latency (<500ms p99) and error rate (<1%) targets
3. **Alert Generation**: Prometheus recording/alerting rules (generated from OpenSLO) fire on breach
4. **Alert Routing**: Alertmanager deduplicates, groups, and sends to AI agent webhook
5. **Enriched Response**: Agent loads OpenSLO context, enriches alert, takes action (log/notify/remediate)

## SRE Approach

- **Data input**: SLIs (request duration, error counts)
- **Operational boundaries**: SLOs (business-driven health definitions)
- **Operational response**: Error budget policies, automated remediation

## References

- [Anomaly Detection Problem](../anomaly-detection-problem.md)
- [CI/CD Group Notes](../cicd-group.md)
- [Task 1: Deployment Pipeline](../todo/TASK-1-deployment-pipeline.md)
- [Task 2: Monitoring Infrastructure](../todo/TASK-2-monitoring-infrastructure.md)
- [Task 3: AI Agent Webhook](../todo/TASK-3-ai-agent-webhook.md)
- [Task 4: Example Service](../todo/TASK-4-example-service-exerciser-slos.md)
