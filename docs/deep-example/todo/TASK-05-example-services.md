# TASK-05: Example Services

## Objective
Build Django-based microservices representing the Meridian Marketplace (catalog, order, seller services) with Prometheus instrumentation and endpoints that can simulate latency and errors on demand.

## Components
- `catalog-service` — product listing, search proxy, category browsing
- `order-service` — checkout flow, order status, payment initiation
- `seller-service` — seller onboarding, inventory management, payout status
- Prometheus client instrumentation on each service
- Configurable fault injection (latency, errors) via query parameters or headers
- ServiceMonitor CRDs for Prometheus scraping

## Steps
1. Create three lightweight Django apps (or a single Django project with three apps), each runnable as an independent service via separate Docker containers.
2. For each service, implement:
   - A health check endpoint (`GET /healthz`)
   - 2-3 representative business endpoints (e.g., catalog: `/products`, `/products/<id>`, `/search`; order: `/checkout`, `/orders/<id>`; seller: `/sellers/<id>`, `/payouts`)
   - Prometheus instrumentation using `django-prometheus` or `prometheus_client`:
     - `http_request_duration_seconds` histogram (labels: method, endpoint, status)
     - `http_requests_total` counter (labels: method, endpoint, status)
   - A `/metrics` endpoint for Prometheus scraping
3. Implement fault injection mechanism:
   - Query parameter `?inject_latency_ms=500` adds artificial delay
   - Query parameter `?inject_error_rate=0.3` returns 500 errors at the specified rate
   - Header `X-Fault-Latency-Ms` and `X-Fault-Error-Rate` as alternatives
4. Create Dockerfiles for each service.
5. Add services to `docker-compose.yaml` with appropriate networking.
6. Create Kubernetes ServiceMonitor CRDs for each service so Prometheus auto-discovers their `/metrics` endpoints.
7. Write basic smoke tests for each service endpoint.

## Acceptance Criteria
- [ ] All three services start and respond on their respective ports
- [ ] Each service exposes `/metrics` with request duration and count metrics
- [ ] Fault injection via query params produces measurable latency increases and error rates
- [ ] Prometheus scrapes metrics from all services successfully
- [ ] ServiceMonitor CRDs are valid and discoverable by Prometheus Operator
- [ ] Smoke tests pass for all endpoints in normal mode

## Dependencies
- TASK-01 (project scaffolding)

## Estimated Complexity
Medium
