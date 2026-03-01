# TASK-06: OpenSLO Definitions

## Objective
Create OpenSLO YAML files defining all 8 SLOs for the Meridian Marketplace, generate corresponding PrometheusRule CRDs, and author flat-file YAML for business goals and operational responses.

## Components
- 8 OpenSLO YAML files in `shared/openslo/slos/`
- Generated PrometheusRule CRDs in `shared/openslo/prometheus-rules/`
- Business goal YAML files in `shared/openslo/business-goals/`
- Operational response YAML files in `shared/openslo/operational-responses/`
- Generation script or Makefile target for OpenSLO → PrometheusRule conversion

## Steps
1. Create directory structure:
   - `shared/openslo/slos/`
   - `shared/openslo/prometheus-rules/`
   - `shared/openslo/business-goals/`
   - `shared/openslo/operational-responses/`
2. Author 8 OpenSLO SLO definitions:
   - `catalog-search-latency.yaml` — p99 search latency < 200ms
   - `catalog-availability.yaml` — catalog service availability > 99.9%
   - `checkout-latency.yaml` — p95 checkout latency < 1s
   - `checkout-error-rate.yaml` — checkout error rate < 0.1%
   - `payment-processing-latency.yaml` — p99 payment processing < 2s
   - `payout-success-rate.yaml` — seller payout success rate > 99.5%
   - `seller-onboarding-latency.yaml` — p95 onboarding flow < 3s
   - `search-relevance-latency.yaml` — p99 search relevance scoring < 500ms
3. For each SLO, specify: `apiVersion`, `kind: SLO`, `metadata`, `spec.service`, `spec.indicator` (referencing Prometheus metric), `spec.objectives` with target and time window.
4. Author business goal YAML files linking SLOs to business outcomes:
   - `holiday-revenue.yaml` — links checkout and payment SLOs
   - `seller-onboarding-velocity.yaml` — links seller onboarding and payout SLOs
   - `payment-reliability.yaml` — links payment and payout SLOs
   - `search-conversion.yaml` — links search and catalog SLOs
5. Author operational response YAML files for each SLO at warning and critical severity:
   - Each includes: recommended actions, escalation path, runbook URL, auto-remediation hints.
6. Create a script or Makefile target that converts OpenSLO YAML to PrometheusRule CRDs (using `oslo` CLI or a custom script with `pyyaml`).
7. Validate all YAML files parse correctly.
8. Validate generated PrometheusRule CRDs against the Kubernetes API schema.

## Acceptance Criteria
- [ ] 8 OpenSLO YAML files exist and are valid OpenSLO spec
- [ ] Each SLO references a real Prometheus metric emitted by the example services
- [ ] PrometheusRule CRDs are generated and valid Kubernetes resources
- [ ] Business goal YAML files link SLOs to business outcomes with impact descriptions
- [ ] Operational response YAML files provide actionable guidance at each severity level
- [ ] `make generate-rules` (or equivalent) produces all PrometheusRule CRDs from OpenSLO definitions
- [ ] All YAML files pass lint/validation

## Dependencies
- TASK-05 (example services — need to know the exact metric names to reference)

## Estimated Complexity
Medium
