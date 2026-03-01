# TASK-10: Integration Testing

## Objective
Build an end-to-end test that deploys the full Meridian Marketplace stack, runs an exerciser scenario, and verifies that an enriched alert appears in the Next.js dashboard with correct business context and recommended actions.

## Components
- Full-stack deployment automation (docker-compose or Kind)
- Test harness using pytest
- Exerciser scenario trigger
- GraphQL API assertions
- Dashboard verification (API-level or browser-level with Playwright)
- CI-compatible test runner

## Steps
1. Create `tests/e2e/` directory with test infrastructure.
2. Write a pytest fixture that:
   a. Starts the full stack via `docker compose up -d --build --wait`
   b. Waits for all services to be healthy (poll health endpoints)
   c. Runs database migrations and loads seed data
   d. Tears down the stack after tests complete
3. Write test: **Alert enrichment pipeline**
   a. Trigger a simulated Alertmanager webhook to the FastAPI agent (POST with a crafted alert payload matching the checkout-latency SLO)
   b. Wait for EnrichedAlert to appear in the database (poll GraphQL `enrichedAlerts` query)
   c. Assert the enriched alert contains:
      - Correct service reference
      - Correct SLO definition reference
      - Business context summary mentioning "Holiday revenue target"
      - Recommended actions from the operational response
      - Severity level matching the alert
4. Write test: **Full scenario end-to-end**
   a. Start the holiday traffic spike exerciser scenario (short duration, 1-2 minutes)
   b. Wait for Prometheus to detect SLO breach and fire alert to Alertmanager
   c. Wait for Alertmanager to deliver webhook to FastAPI agent
   d. Verify enriched alert appears in GraphQL API with business context
   e. (Optional) Verify alert card renders in Next.js dashboard via Playwright
5. Write test: **Acknowledge alert flow**
   a. Create an enriched alert via the pipeline
   b. Call `acknowledgeAlert` mutation
   c. Verify status changes to "acknowledged" and timestamp is set
   d. Verify the dashboard reflects the updated status
6. Add Makefile target: `make test-e2e` that runs the full integration test suite.
7. Document test prerequisites and expected runtime in a README.

## Acceptance Criteria
- [ ] `make test-e2e` runs the full integration test suite
- [ ] Alert enrichment pipeline test passes: webhook → enriched alert with business context
- [ ] Full scenario test passes: exerciser → Prometheus → Alertmanager → agent → enriched alert
- [ ] Acknowledge flow test passes: mutation updates alert status correctly
- [ ] Tests clean up after themselves (stack torn down, no orphaned containers)
- [ ] Tests complete within 10 minutes on a standard development machine
- [ ] Test failures produce clear, actionable error messages

## Dependencies
- TASK-01 (project scaffolding — docker-compose must work)
- TASK-02 (database models)
- TASK-03 (GraphQL API)
- TASK-04 (enrichment agent)
- TASK-05 (example services)
- TASK-06 (OpenSLO definitions)
- TASK-07 (Next.js dashboard — for optional browser-level verification)
- TASK-09 (exerciser scenarios — for full scenario test)

## Estimated Complexity
Large
