# TASK-04: Alert Enrichment Agent

## Objective
Build a FastAPI service that receives Alertmanager webhooks, enriches alerts with business context from the Django API and OpenSLO definitions, creates EnrichedAlert records, pushes updates to the GraphQL subscription, and exposes its own Prometheus metrics.

## Components
- FastAPI webhook endpoint (`POST /webhook/alertmanager`)
- Alertmanager payload parser
- Django GraphQL client for fetching SLO definitions, business goals, and operational responses
- OpenSLO YAML file reader (from shared volume/directory)
- EnrichedAlert creation via Django GraphQL mutation or direct DB write
- GraphQL subscription push (notify new alert)
- Prometheus metrics endpoint (`GET /metrics`)

## Steps
1. Create FastAPI app in `fastapi-agent/` with health check endpoint.
2. Define Pydantic models for the Alertmanager webhook payload (alerts, labels, annotations, status).
3. Implement `POST /webhook/alertmanager` endpoint:
   a. Parse incoming alert payload.
   b. Extract `slo_name` and `service` labels from the alert.
   c. Query Django GraphQL API for matching SLODefinition, linked BusinessGoals, and OperationalResponses.
   d. Load corresponding OpenSLO YAML from `shared/openslo/` for additional context.
   e. Compose enriched alert with: business context summary, recommended actions, severity mapping.
   f. Create EnrichedAlert record via Django GraphQL mutation (or direct API call).
   g. Push notification to GraphQL subscription channel.
4. Implement Prometheus metrics using `prometheus-fastapi-instrumentator` or `prometheus_client`:
   - `alerts_received_total` (counter, labels: service, slo_name)
   - `alerts_enriched_total` (counter, labels: service, severity)
   - `enrichment_duration_seconds` (histogram)
5. Expose `GET /metrics` for Prometheus scraping.
6. Configure Alertmanager webhook receiver to point to this service.
7. Write tests: unit tests for payload parsing and enrichment logic, integration test for the full webhook flow.

## Acceptance Criteria
- [ ] `POST /webhook/alertmanager` accepts valid Alertmanager payloads and returns 200
- [ ] Agent queries Django API and retrieves correct business context for each alert
- [ ] EnrichedAlert records are created with correct business context and recommended actions
- [ ] GraphQL subscription receives notification of new enriched alerts
- [ ] `/metrics` endpoint returns valid Prometheus metrics
- [ ] Invalid or malformed payloads return appropriate error responses
- [ ] Unit and integration tests pass

## Dependencies
- TASK-01 (project scaffolding)
- TASK-02 (database models — needed for EnrichedAlert schema)
- TASK-03 (GraphQL API — needed for querying context and creating alerts)
- TASK-06 (OpenSLO definitions — needed for YAML context loading)

## Estimated Complexity
Large
