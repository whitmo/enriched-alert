# PoC Plan: Task 3 - AI Agent/Webhook Development

## Objective
Develop a basic AI agent (implemented as a webhook receiver) that can receive alerts from Alertmanager, parse them, and access corresponding OpenSLO definitions to provide context. For this first pass, the response will be a simple, verifiable action (e.g., logging).

## Components
*   **Webhook Receiver**: A lightweight application capable of receiving HTTP POST requests from Alertmanager.
*   **OpenSLO Definition Access**: Mechanism for the agent to read OpenSLO YAML files.
*   **Basic Alert Parsing**: Logic to extract key information (e.g., SLO name) from the Alertmanager payload.
*   **Contextual Logging/Output**: Initial "response" mechanism for the PoC.

## Technologies (Recommended)
*   **Language**: Python (highly suitable for AI/ML, good ecosystem for web frameworks).
*   **Framework**: FastAPI or Flask (lightweight, easy to set up for webhooks).
*   **YAML Parser**: `PyYAML` (for reading OpenSLO definitions).

## Steps

### 1. Setup Project Structure
*   Create a new Python project for the agent.
*   Define a directory for OpenSLO definition YAML files that will be mounted/copied to the agent's environment.

### 2. Implement Webhook Endpoint
*   Create an HTTP POST endpoint (e.g., `/alert`) that will listen for Alertmanager webhooks.
*   The endpoint should:
    *   Receive the JSON payload from Alertmanager.
    *   Log the raw payload for inspection.

### 3. Parse Alert Payload
*   Extract relevant information from the Alertmanager JSON, specifically:
    *   The `groupKey` or `commonLabels` to identify the alert.
    *   Crucially, identify a label that uniquely points to the breached SLO (e.g., `slo_name`).

### 4. Access OpenSLO Definitions for Context
*   Based on the `slo_name` extracted from the alert, load the corresponding OpenSLO definition YAML file from the designated directory.
*   Parse the YAML content.

### 5. Initial "Response" - Contextual Logging
*   For the PoC, the agent's first action should be to log the received alert *along with* the loaded OpenSLO definition. This demonstrates that the agent can retrieve the context.
*   Example log entry: "Received alert for SLO 'my-service-latency'. SLO Definition: <full YAML content>".

### 6. Containerization
*   Create a `Dockerfile` for the agent to containerize it for deployment to Kubernetes.

### 7. Kubernetes Deployment Manifests
*   Create Kubernetes Deployment and Service manifests for the agent.
*   Ensure the Service is accessible within the cluster (e.g., via ClusterIP).
*   Configure a Persistent Volume Claim (PVC) or `ConfigMap` if OpenSLO definitions are stored locally and need to be easily updated without rebuilding the image. A `ConfigMap` for the YAML files would be simpler for a PoC.

## Acceptance Criteria
*   The agent successfully starts and exposes a webhook endpoint.
*   Alertmanager can send alerts to the agent's webhook.
*   The agent can parse Alertmanager payloads and identify the breached SLO.
*   The agent can load the correct OpenSLO definition YAML based on the alert.
*   The agent logs the alert payload and the associated OpenSLO definition content.
*   The agent can be deployed to the Kind cluster and communicate with Alertmanager.