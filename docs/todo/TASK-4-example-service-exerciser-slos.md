# PoC Plan: Task 4 - Example Service, Exerciser, and OpenSLO Definitions

## Objective
Develop a simple example service that exposes Prometheus metrics, define latency and error rate SLOs for it using OpenSLO, and create an exerciser script to deterministically trigger SLO breaches.

## Components
*   **Example Service**: A lightweight HTTP microservice capable of emitting Prometheus metrics for latency and error rate, and configurable to simulate performance issues.
*   **OpenSLO Definitions**: YAML files defining the latency and error rate SLOs for the example service.
*   **Exerciser Script**: A script to interact with the example service to induce desired latency and error conditions.

## Technologies (Recommended)
*   **Example Service**: Python (Flask/FastAPI) or Node.js (Express) with a Prometheus client library.
*   **Exerciser Script**: Python (`requests` library).
*   **OpenSLO Definitions**: YAML.

## Steps

### 1. Develop Example Service
*   Create a simple HTTP service (e.g., `/health`, `/latency`, `/error`).
*   Integrate a Prometheus client library (e.g., `prometheus_client` for Python) to expose:
    *   **HTTP request duration histogram**: To measure latency.
    *   **HTTP request counter (by status code)**: To measure error rate.
*   Implement endpoints or internal logic that can be triggered (e.g., via query parameters or specific HTTP headers) to:
    *   Introduce artificial latency (e.g., `time.sleep()`).
    *   Return HTTP 5xx error codes.
*   Containerize the service using a `Dockerfile`.
*   Create Kubernetes Deployment and Service manifests for the example service, ensuring the Prometheus metrics endpoint is exposed and scrapeable by Prometheus.

### 2. Define OpenSLO for the Example Service
*   Create two `OpenSLO` YAML files for the example service:
    *   **Latency SLO**: Define an SLO targeting request duration (e.g., "99th percentile latency must be less than 500ms over a 5-minute rolling window").
    *   **Error Rate SLO**: Define an SLO targeting HTTP 5xx errors (e.g., "Error rate must be less than 1% over a 1-hour rolling window").
*   Ensure these SLOs reference the Prometheus metrics exposed by the example service.
*   Store these YAML files in a designated directory accessible by the OpenSLO integration mechanism (e.g., the directory that will be processed to generate Prometheus rules).

### 3. Generate Prometheus Recording and Alerting Rules
*   Use the chosen OpenSLO integration method (e.g., an OpenSLO CLI tool) to generate Prometheus recording rules (for SLIs and error budgets) and alerting rules (for SLO breaches) based on the OpenSLO definitions.
*   These generated rules will be deployed to Prometheus in the monitoring infrastructure (Task 2).
*   Ensure the alerting rules include a `slo_name` label that corresponds to the OpenSLO definition filename or identifier, which the AI agent (Task 3) will use to retrieve context.

### 4. Develop Exerciser Script
*   Create a Python script that makes HTTP requests to the example service.
*   The script should be able to:
    *   Make normal requests to keep the service healthy.
    *   Trigger latency simulation (e.g., by hitting a specific `/latency` endpoint or passing a query parameter).
    *   Trigger error simulation (e.g., by hitting a specific `/error` endpoint).
    *   Control the duration and intensity of these simulations to deterministically breach the defined SLOs.
*   The script can be run manually or as a Kubernetes Job.

## Acceptance Criteria
*   The example service is deployed and exposing Prometheus metrics for latency and error rate.
*   Prometheus is successfully scraping metrics from the example service.
*   OpenSLO definitions for latency and error rate are created and are valid.
*   Prometheus recording and alerting rules are successfully generated from OpenSLO definitions and loaded into Prometheus.
*   The exerciser script can deterministically induce latency and error conditions in the example service, leading to SLO breaches.
*   Alertmanager receives alerts when SLOs are breached.