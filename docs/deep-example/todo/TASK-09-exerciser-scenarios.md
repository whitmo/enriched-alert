# TASK-09: Exerciser Scenarios

## Objective
Create scenario scripts that simulate realistic Meridian Marketplace business conditions, driving the example services into SLO breaches that produce enriched alerts with meaningful business context.

## Components
- Scenario runner framework (Python script with scenario registry)
- Individual scenario scripts:
  - Holiday traffic spike (checkout latency)
  - Payment provider degradation (payout SLO)
  - Search index corruption (search latency)
  - Cascading failure across services
- CLI interface for selecting and running scenarios
- Configurable intensity and duration parameters

## Steps
1. Create `exerciser/` directory in the repo root with `uv init`.
2. Build a scenario runner framework:
   - Base `Scenario` class with `setup()`, `run()`, `teardown()` methods
   - Scenario registry for discovery and listing
   - CLI using `click` or `argparse`: `python -m exerciser run <scenario-name> --duration 5m --intensity high`
3. Implement **Holiday Traffic Spike** scenario:
   - Gradually ramp up request volume to checkout endpoint (10x normal)
   - Inject 200-500ms additional latency via fault injection parameters
   - Expected result: checkout-latency and checkout-error-rate SLOs breach
   - Business context: "Holiday revenue target at risk"
4. Implement **Payment Provider Degradation** scenario:
   - Inject high latency (2-5s) and elevated error rate (5-10%) on payment endpoints
   - Simulate intermittent timeouts
   - Expected result: payment-processing-latency and payout-success-rate SLOs breach
   - Business context: "Payment processing reliability compromised, seller payouts delayed"
5. Implement **Search Index Corruption** scenario:
   - Inject high latency on search endpoints (1-3s)
   - Return degraded results (simulated via error rate)
   - Expected result: catalog-search-latency and search-relevance-latency SLOs breach
   - Business context: "Search conversion rate dropping, catalog discovery impaired"
6. Implement **Cascading Failure** scenario:
   - Start with catalog-service degradation
   - Propagate to order-service (depends on catalog for product validation)
   - Then payment-service (depends on order-service)
   - Expected result: multiple SLOs breach in sequence, demonstrating cross-service impact
   - Business context: "Multiple business goals at risk due to cascading infrastructure failure"
7. Add `--dry-run` flag that logs what would happen without making requests.
8. Add scenario documentation in each scenario file's docstring.

## Acceptance Criteria
- [ ] `python -m exerciser list` shows all available scenarios
- [ ] Each scenario runs for the specified duration and produces measurable metric changes
- [ ] Holiday traffic spike scenario causes checkout SLO breaches within 5 minutes
- [ ] Payment degradation scenario causes payment SLO breaches within 5 minutes
- [ ] Search corruption scenario causes search SLO breaches within 5 minutes
- [ ] Cascading failure scenario triggers alerts across multiple services in sequence
- [ ] `--dry-run` flag works without making actual requests
- [ ] Scenarios clean up after themselves (fault injection removed on teardown)

## Dependencies
- TASK-05 (example services — must be running with fault injection support)
- TASK-06 (OpenSLO definitions — SLOs must exist for alerts to fire)

## Estimated Complexity
Medium
